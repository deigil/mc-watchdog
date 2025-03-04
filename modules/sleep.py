from datetime import datetime, time, timedelta
import schedule
import os
from modules.logging import log
from modules.server import server_manager
from modules.discord import broadcast_discord_message, discord_bot
from modules.utils import is_maintenance_day, get_player_count
from config import SLEEP_TRIGGER_DIR, SLEEP_TRIGGER_FILE
import threading

class SleepManager:
    def __init__(self):
        self.is_sleeping = False
        self._empty_check_scheduled = False

    def is_sleep_time(self):
        """Check if current time is between 11:59 PM and 8:00 AM"""
        current_time = datetime.now().time()
        sleep_start = time(23, 59)  # 11:59 PM
        sleep_end = time(8, 0)      # 8:00 AM
        
        if (current_time >= sleep_start) or (current_time < sleep_end):
            log(f"Current time {current_time} is within sleep period")
            return True
        return False

    def check_and_sleep(self):
        """Check if it's time to sleep and handle the sleep process"""
        try:
            # First check if it's actually bedtime
            if not self.is_sleep_time():
                log("Not within sleep period, skipping sleep check")
                return False

            # Reset sleep state if server is running (manual restart)
            if server_manager.check_server() and self.is_sleeping:
                log("Server was manually restarted during sleep hours")
                self.is_sleeping = False
                self._empty_check_scheduled = False
            
            # Always announce bedtime status when checking (unless maintenance)
            if not is_maintenance_day():
                broadcast_discord_message("🌙 It's bedtime! Server will sleep when empty.")
                log("Starting bedtime checks")
            
            # Check for players
            if not server_manager.check_server_empty():
                if not self._empty_check_scheduled:
                    log("Players still online, will check again in 5 minutes")
                    schedule.every(5).minutes.do(self.periodic_empty_check)
                    self._empty_check_scheduled = True
                return False
            
            # Server is empty, announce and sleep
            if not is_maintenance_day():
                broadcast_discord_message("💤 All players have left. Server is going to sleep and will wake up at 8:00 AM!")
            return self.initiate_sleep("auto")
            
        except Exception as e:
            log(f"Error in sleep check: {e}")
            return False

    def periodic_empty_check(self):
        """Check if server is empty every 5 minutes"""
        try:
            # Reset sleep state if server was manually started
            if server_manager.check_server() and self.is_sleeping:
                log("Server was manually restarted during sleep period")
                self.is_sleeping = False
            
            # If server is running and it's sleep time, check for players
            if server_manager.check_server():
                if server_manager.check_server_empty():
                    if not is_maintenance_day():
                        broadcast_discord_message("💤 All players have left. Server is going to sleep and will wake up at 8:00 AM!")
                    self.initiate_sleep("auto")
                    schedule.clear(self.periodic_empty_check)
                    self._empty_check_scheduled = False
                    return schedule.CancelJob
                else:
                    log("Players still online, continuing periodic checks")
                    return None
            else:
                # If server is not running during sleep time, make sure it stays down
                if self.is_sleep_time():
                    server_manager.manual_stop = True
                    self.is_sleeping = True
                    return None
                else:
                    # If we're out of sleep time, cancel the periodic check
                    self._empty_check_scheduled = False
                    return schedule.CancelJob
                
        except Exception as e:
            log(f"Error in periodic empty check: {e}")
            return None

    def initiate_sleep(self, mode="auto"):
        """Initiate sleep mode"""
        try:
            # Double check server is empty before stopping
            if not server_manager.check_server_empty():
                log("Server not empty, aborting sleep")
                return False
            
            # First stop the server
            if server_manager.check_server():
                if not server_manager.stop_server():
                    log("Failed to stop server for sleep mode")
                    return False
                log("Server stopped successfully")
            
            # Then create sleep trigger file
            if not self.signal_windows_sleep():
                log("Failed to create sleep trigger file after server stop")
                return False
            
            # Set manual stop to prevent auto-start
            server_manager.manual_stop = True
            self.is_sleeping = True
            log(f"Sleep mode initiated ({mode})")
            return True
            
        except Exception as e:
            log(f"Error initiating sleep mode: {e}")
            return False

    def signal_windows_sleep(self):
        """Signal Windows to sleep by creating a trigger file"""
        try:
            log(f"Attempting to create sleep trigger in directory: {SLEEP_TRIGGER_DIR}")
            log(f"Full trigger file path: {SLEEP_TRIGGER_FILE}")
            
            # Test WSL to Windows path access
            if not os.path.exists("/mnt/c"):
                log("ERROR: Cannot access Windows filesystem through WSL")
                return False
                
            # Ensure directory exists
            if not os.path.exists(SLEEP_TRIGGER_DIR):
                log(f"Sleep trigger directory does not exist, creating it")
                os.makedirs(SLEEP_TRIGGER_DIR, exist_ok=True)
            
            # Remove any existing trigger file
            if os.path.exists(SLEEP_TRIGGER_FILE):
                os.remove(SLEEP_TRIGGER_FILE)
                log("Removed existing sleep trigger file")
            
            # Write the trigger file with current timestamp
            timestamp = datetime.now()
            log(f"Writing timestamp to trigger file: {timestamp}")
            
            with open(SLEEP_TRIGGER_FILE, 'w') as f:
                f.write(str(timestamp))
            
            # Verify file was created
            if os.path.exists(SLEEP_TRIGGER_FILE):
                # Read back the file to verify content
                with open(SLEEP_TRIGGER_FILE, 'r') as f:
                    content = f.read().strip()
                log(f"Verified trigger file creation. Content: {content}")
                return True
            else:
                log("Failed to verify sleep trigger file creation")
                return False
                
        except Exception as e:
            log(f"Error creating sleep trigger: {e}")
            log(f"Current working directory: {os.getcwd()}")
            log(f"Directory exists: {os.path.exists(SLEEP_TRIGGER_DIR)}")
            log(f"File path: {SLEEP_TRIGGER_FILE}")
            return False

    def schedule_sleep(self):
        """Schedule sleep checks"""
        schedule.every().day.at("23:59").do(self.check_and_sleep)
        log("Sleep checks scheduled for 11:59 PM")
        
        # Add morning wake-up reset
        schedule.every().day.at("08:00").do(self.morning_reset)
        log("Morning reset scheduled for 8:00 AM")
        
        if self.is_sleep_time():
            log("Watchdog started during sleep hours, initiating immediate sleep check")
            self.check_and_sleep()

    def morning_reset(self):
        """Reset sleep state and send good morning message"""
        try:
            log("Performing morning reset")
            
            # Reset sleep state
            self.is_sleeping = False
            
            # Reset server manager manual stop flag
            server_manager.manual_stop = False
            log("Reset manual_stop flag for morning wake-up")
            
            # Send good morning message
            broadcast_discord_message("🌞 Good morning! The server is ready to wake up on the first connection attempt.")
            log("Morning wake-up message sent")
            
            return True
        except Exception as e:
            log(f"Error in morning reset: {e}")
            return False

# Create singleton instance
sleep_manager = SleepManager()

# Export convenience functions
def schedule_sleep():
    sleep_manager.schedule_sleep()

def is_sleep_time():
    return sleep_manager.is_sleep_time()
def schedule_sleep_checks():
    """Schedule the sleep checks for 11:59 PM"""
    try:
        # Get the current time
        now = datetime.now()
        
        # Set the target time to 11:59 PM today
        target_time = now.replace(hour=23, minute=59, second=0, microsecond=0)
        
        # If it's already past the target time, schedule for tomorrow
        if now > target_time:
            target_time += timedelta(days=1)
        
        # Calculate the delay in seconds
        delay = (target_time - now).total_seconds()
        
        # Schedule the sleep check
        threading.Timer(delay, check_sleep_time).start()
        
        log(f"Sleep checks scheduled for 11:59 PM")
    except Exception as e:
        log(f"Error scheduling sleep checks: {e}")

def check_sleep_time():
    """Check if it's time to sleep and the server is empty"""
    try:
        # Check if we're in maintenance mode
        from modules.maintenance import is_maintenance_mode
        
        # Only send bedtime message if we're not in maintenance mode
        if not is_maintenance_mode():
            # Send the bedtime message
            broadcast_discord_message("🌙 It's bedtime! Server will sleep when empty.")
            log("Starting bedtime checks")
            
            # Check if the server is empty using the DiscordBot's get_player_count
            if discord_bot.get_player_count() == 0:
                broadcast_discord_message("💤 All players have left. Server is going to sleep and will wake up at 8:00 AM!")
                sleep_manager.initiate_sleep("auto")
        else:
            log("Skipping bedtime message during maintenance mode")
            
            # Still check if the server is empty for maintenance sleep
            if discord_bot.get_player_count() == 0:
                sleep_manager.initiate_sleep("auto")
                
    except Exception as e:
        log(f"Error checking sleep time: {e}")
