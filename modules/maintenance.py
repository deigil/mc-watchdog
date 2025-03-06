from datetime import datetime
import schedule
import time
import os
from modules.logging import log
import asyncio
import discord

class MaintenanceManager:
    def __init__(self):
        self.is_in_maintenance = False

    def is_maintenance_day(self):
        """Check if it's a maintenance day (Tuesday or Thursday)"""
        return datetime.now().weekday() in [1, 3]

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
            from modules.sleep import sleep_manager
            from modules.discord import broadcast_discord_message
            
            # Check if server is empty, if not, wait until it is
            while not server_manager.check_server_empty():
                log("Server not empty, waiting 5 minutes...")
                time.sleep(300)
            
            log("Server is empty, proceeding with maintenance shutdown")
            
            # Use sleep manager to handle the shutdown process
            if sleep_manager.initiate_sleep("maintenance"):
                maintenance_msg = "🔧 **MAINTENANCE MODE**\n"
                maintenance_msg += f"Server will be down until {('Wednesday' if datetime.now().weekday() == 0 else 'Friday')} 8 AM"
                
                # Force send to all channels even during maintenance
                broadcast_discord_message(maintenance_msg, force=True)
                
                # Create a maintenance mode marker file
                maintenance_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "maintenance_mode")
                with open(maintenance_file, 'w') as f:
                    f.write(str(datetime.now()))
            
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

    def exit_maintenance(self):
        """Exit maintenance mode"""
        try:
            log("Exiting maintenance mode")
            self.is_in_maintenance = False
            
            # Remove the maintenance mode marker file if it exists
            maintenance_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "maintenance_mode")
            if os.path.exists(maintenance_file):
                os.remove(maintenance_file)
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
    """Check if the server is currently in maintenance mode"""
    try:
        maintenance_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "maintenance_mode")
        return os.path.exists(maintenance_file)
    except Exception as e:
        log(f"Error checking maintenance mode: {e}")
        return False