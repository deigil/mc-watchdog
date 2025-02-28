from datetime import datetime
import os
import time
from modules.logging import log
from modules.server import server_manager
from modules.discord import broadcast_discord_message
from config import SLEEP_TRIGGER_DIR, SLEEP_TRIGGER_FILE

class SleepManager:
    def __init__(self):
        self.is_sleeping = False

    def signal_windows_sleep(self):
        """Signal Windows to sleep by creating a trigger file"""
        try:
            log(f"Attempting to create sleep trigger in: {SLEEP_TRIGGER_DIR}")
            
            if not os.path.exists(SLEEP_TRIGGER_DIR):
                log(f"Directory doesn't exist, creating: {SLEEP_TRIGGER_DIR}")
                os.makedirs(SLEEP_TRIGGER_DIR, exist_ok=True)
            
            log(f"Creating trigger file: {SLEEP_TRIGGER_FILE}")
            with open(SLEEP_TRIGGER_FILE, 'w') as f:
                timestamp = str(datetime.now())
                f.write(timestamp)
            log(f"Sleep trigger file created with timestamp: {timestamp}")
            
            if os.path.exists(SLEEP_TRIGGER_FILE):
                log("Verified: Sleep trigger file exists")
                return True
            else:
                log("Warning: Sleep trigger file was not created!")
                return False
                
        except Exception as e:
            log(f"Error creating sleep trigger: {e}")
            log(f"Current working directory: {os.getcwd()}")
            log(f"Directory exists: {os.path.exists(SLEEP_TRIGGER_DIR)}")
            log(f"Directory writable: {os.access(SLEEP_TRIGGER_DIR, os.W_OK)}")
            return False

    def is_nightly_sleep_time(self):
        """Check if it's time for nightly sleep (23:59)"""
        now = datetime.now()
        # Sleep at 23:59 every night, including maintenance nights
        return now.hour == 23 and now.minute == 59

    def is_morning_wake_time(self):
        """Check if it's time to wake up (8:00)"""
        from modules.maintenance import is_maintenance_day
        now = datetime.now()
        # Don't wake up on maintenance days (Tue/Thu)
        return (now.hour == 8 and now.minute == 0 and 
                not is_maintenance_day())

    def initiate_sleep(self, reason="nightly"):
        """Start sleep mode"""
        try:
            log(f"Initiating {reason} sleep mode")
            
            # Only sleep if server is empty
            if server_manager.check_server_empty():
                log("Server is empty, proceeding with sleep")
                
                # Stop the Minecraft container
                server_manager.stop_server()
                
                # Send sleep message
                if reason == "nightly":
                    broadcast_discord_message("💤 Server entering night mode - Will wake up at 8 AM!")
                
                # Signal Windows to sleep
                if self.signal_windows_sleep():
                    self.is_sleeping = True
                    return True
            else:
                log("Server not empty, skipping sleep")
                
            return False
                
        except Exception as e:
            log(f"Error during {reason} sleep: {e}")
            broadcast_discord_message(f"⚠️ Error during {reason} sleep: {e}")
            return False

    def schedule_sleep(self):
        """Schedule nightly sleep checks"""
        import schedule
        from datetime import datetime

        def should_send_sleep_warning():
            """Check if we should send sleep warning based on time"""
            current_hour = datetime.now().hour
            # Only send sleep warning if it's between 00:00 (midnight) and 07:30 (7:30 AM)
            if current_hour < 7 or (current_hour == 7 and datetime.now().minute < 30):
                return not self.is_nightly_sleep_time() and broadcast_discord_message("💤 Server will sleep in 30 minutes if no players are online!")
            return False

        # Add sleep warning at 23:30 (only on non-maintenance nights)
        schedule.every().day.at("23:30").do(should_send_sleep_warning)
        
        # Add nightly sleep check at 23:59
        schedule.every().day.at("23:59").do(
            lambda: self.is_nightly_sleep_time() and self.initiate_sleep("nightly")
        )
        
        # Morning wake should only start server, no sleep messages
        schedule.every().day.at("08:00").do(
            lambda: self.is_morning_wake_time() and server_manager.start_server()
        )

# Create singleton instance
sleep_manager = SleepManager()

# Export convenience functions
def signal_windows_sleep():
    return sleep_manager.signal_windows_sleep()

def schedule_sleep():
    sleep_manager.schedule_sleep()

def initiate_sleep(reason="nightly"):
    return sleep_manager.initiate_sleep(reason)