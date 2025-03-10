from datetime import datetime, time
import schedule
import os
import time as time_module
from modules.logging import log
import asyncio
import discord

class MaintenanceManager:
    def __init__(self):
        self.is_in_maintenance = False
        self.maintenance_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "maintenance_mode")

    def is_maintenance_day(self):
        """Check if it's a maintenance day (Tuesday or Thursday)"""
        return datetime.now().weekday() in [1, 3]
    
    def is_maintenance_mode(self):
        """
        Check if the server is currently in maintenance mode
        Also ensures maintenance mode is active on maintenance days (Tuesday and Thursday)
        """
        try:
            file_exists = os.path.exists(self.maintenance_file)
            
            # Check if today is a maintenance day (Tuesday or Thursday)
            current_day = datetime.now().weekday()
            is_maintenance_day = current_day in [1, 3]
            
            # If it's a maintenance day but the file doesn't exist, create it
            if is_maintenance_day and not file_exists:
                log(f"Today is a full maintenance day (day {current_day}: {'Tuesday' if current_day == 1 else 'Thursday'}) but maintenance file is missing")
                
                # Create the maintenance file
                with open(self.maintenance_file, 'w') as f:
                    f.write(str(datetime.now()))
                
                log("Created maintenance file for maintenance day")
                
                # Set maintenance flag on the manager
                self.is_in_maintenance = True
                
                # Send maintenance notification (only once per startup)
                if not hasattr(self, '_maintenance_notification_sent'):
                    try:
                        from modules.discord import broadcast_discord_message
                        maintenance_msg = "🔧 **MAINTENANCE MODE**\n"
                        maintenance_msg += f"Server will be down until {('Wednesday' if current_day == 1 else 'Friday')} 8 AM"
                        broadcast_discord_message(maintenance_msg, force=True)
                        self._maintenance_notification_sent = True
                    except Exception as e:
                        log(f"Error sending maintenance notification: {e}")
                
                return True
            
            # If it's not a maintenance day but the file exists, check if we should exit maintenance
            elif not is_maintenance_day and file_exists:
                # If it's Wednesday or Friday morning (after maintenance), we should have already exited
                # This is handled by the morning reset and on_ready handlers
                # This is just a fallback check
                if current_day in [2, 4] and datetime.now().time() >= time(8, 0):
                    log("It's after maintenance period but file still exists, removing it")
                    try:
                        os.remove(self.maintenance_file)
                        log("Removed maintenance file after maintenance period")
                        self.is_in_maintenance = False
                        return False
                    except Exception as e:
                        log(f"Error removing maintenance file: {e}")
            
            # Normal case - just check if the file exists
            return file_exists
            
        except Exception as e:
            log(f"Error checking maintenance mode: {e}")
            return False

    def is_maintenance_time(self):
        """Check if it's maintenance time (Monday or Wednesday 23:59)"""
        now = datetime.now()
        # Check if it's maintenance night (Monday or Wednesday)
        is_maintenance_night = now.weekday() in [0, 2]
        # If it's after 23:29 on maintenance night, consider it maintenance time
        return is_maintenance_night and (now.hour == 23 and now.minute >= 29)

    def is_restart_time(self):
        """Check if it's time to restart after maintenance (Wednesday or Friday 8:00)"""
        now = datetime.now()
        return (now.weekday() in [2, 4] and  # Wednesday or Friday
                now.hour == 8 and now.minute == 0)

    def initiate_maintenance(self):
        """Start maintenance mode"""
        try:
            log("Initiating maintenance mode")
            self.is_in_maintenance = True
            
            # Import here to avoid circular dependency
            from modules.server import server_manager
            from modules.discord import broadcast_discord_message
            
            # Check if server is empty, if not, wait until it is
            while not server_manager.check_server_empty():
                log("Server not empty, waiting 5 minutes...")
                broadcast_discord_message("⚠️ Server entering maintenance mode soon. Please log off.")
                time_module.sleep(300)  # Wait 5 minutes
            
            # Stop the server
            if server_manager.check_server():
                if server_manager.stop_server():
                    log("Server stopped for maintenance")
                    
                    # Create a maintenance mode marker file
                    with open(self.maintenance_file, 'w') as f:
                        f.write(str(datetime.now()))
                    
                    maintenance_msg = "🔧 **MAINTENANCE MODE**\n"
                    maintenance_msg += f"Server will be down until {('Wednesday' if datetime.now().weekday() == 0 else 'Friday')} 8 AM"
                    broadcast_discord_message(maintenance_msg, force=True)
                else:
                    log("Failed to stop server for maintenance")
                    broadcast_discord_message("⚠️ Failed to stop server for maintenance!")
            
        except Exception as e:
            log(f"Error during maintenance: {e}")
            # Import here to avoid circular dependency
            from modules.discord import broadcast_discord_message
            broadcast_discord_message(f"⚠️ Error during maintenance: {e}", force=True)

    def schedule_maintenance(self):
        """Schedule maintenance warnings and checks"""
        # Import here to avoid circular dependency
        from modules.discord import broadcast_discord_message
        
        # Maintenance warning 30 minutes before (23:29)
        schedule.every().monday.at("23:29").do(
            lambda: broadcast_discord_message("⚠️ Server entering maintenance mode in 30 minutes!")
        )
        schedule.every().wednesday.at("23:29").do(
            lambda: broadcast_discord_message("⚠️ Server entering maintenance mode in 30 minutes!")
        )
        
        # Add actual maintenance initiation at 23:59
        schedule.every().monday.at("23:59").do(self.initiate_maintenance)
        schedule.every().wednesday.at("23:59").do(self.initiate_maintenance)
        
        log("✓ Maintenance scheduled")

    def exit_maintenance(self):
        """Exit maintenance mode"""
        try:
            # First check if we should actually exit maintenance
            current_day = datetime.now().weekday()
            
            # If it's Tuesday (1) or Thursday (3), we should stay in maintenance mode
            if current_day in [1, 3]:
                log("Today is a full maintenance day (Tuesday or Thursday), staying in maintenance mode")
                return False
            
            log("Exiting maintenance mode")
            self.is_in_maintenance = False
            
            # Remove the maintenance mode marker file if it exists
            if os.path.exists(self.maintenance_file):
                os.remove(self.maintenance_file)
                log("Removed maintenance mode marker file")
            
            # Update Discord bot status
            from modules.discord import discord_bot
            if discord_bot and discord_bot.client and discord_bot.client.is_ready():
                asyncio.run_coroutine_threadsafe(
                    discord_bot.client.change_presence(
                        status=discord.Status.online, 
                        activity=discord.Activity(type=discord.ActivityType.watching, name="a POG Vault 🎁")
                    ),
                    discord_bot.client.loop
                )
                log("Updated bot status to normal mode")
            
            # Send maintenance ended message
            from modules.discord import broadcast_discord_message
            broadcast_discord_message("✅ **MAINTENANCE COMPLETED**\nServer is now available!", force=True)
            
            return True
        except Exception as e:
            log(f"Error exiting maintenance mode: {e}")
            return False

# Create singleton instance
maintenance_manager = MaintenanceManager()

# Export convenience functions
def is_maintenance_time():
    return maintenance_manager.is_maintenance_time()

def is_maintenance_day():
    return maintenance_manager.is_maintenance_day()

def is_restart_time():
    return maintenance_manager.is_restart_time()

def schedule_maintenance():
    maintenance_manager.schedule_maintenance()

def initiate_maintenance():
    maintenance_manager.initiate_maintenance()

def is_maintenance_mode():
    return maintenance_manager.is_maintenance_mode()