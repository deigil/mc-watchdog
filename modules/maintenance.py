from datetime import datetime
import schedule
import time
from modules.logging import log
from modules.server import server_manager
from modules.discord import broadcast_discord_message
from modules.sleep import sleep_manager
from modules.utils import is_maintenance_day, is_maintenance_time, is_restart_time
import os

class MaintenanceManager:
    def __init__(self):
        self.is_in_maintenance = False

    def initiate_maintenance(self):
        """Start maintenance mode"""
        try:
            log("Initiating maintenance mode")
            self.is_in_maintenance = True
            
            # Check if server is empty, if not, wait until it is
            while not server_manager.check_server_empty():
                log("Server not empty, waiting 5 minutes...")
                time.sleep(300)
            
            log("Server is empty, proceeding with maintenance shutdown")
            
            # Use sleep manager to handle the shutdown process
            if sleep_manager.initiate_sleep("maintenance"):
                maintenance_msg = "🔧 **MAINTENANCE MODE**\n"
                maintenance_msg += f"Server will be down until {('Wednesday' if datetime.now().weekday() == 0 else 'Friday')} 8 AM"
                broadcast_discord_message(maintenance_msg)
            
            # Create a maintenance mode marker file
            maintenance_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "maintenance_mode")
            with open(maintenance_file, 'w') as f:
                f.write(str(datetime.now()))
            
        except Exception as e:
            log(f"Error during maintenance: {e}")
            broadcast_discord_message(f"⚠️ Error during maintenance: {e}")

    def schedule_maintenance(self):
        """Schedule maintenance warnings and checks"""
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

# Create singleton instance
maintenance_manager = MaintenanceManager()

# Export convenience functions
def is_maintenance_time():
    return maintenance_manager.is_maintenance_time()

def is_maintenance_day():
    return maintenance_manager.is_maintenance_day()

def schedule_maintenance():
    maintenance_manager.schedule_maintenance()

def initiate_maintenance():
    maintenance_manager.initiate_maintenance()

# Add this function to check if we're in maintenance mode
def is_maintenance_mode():
    """Check if the server is currently in maintenance mode"""
    try:
        # You might need to adjust this based on how you track maintenance mode
        # This is a simple implementation that checks if a maintenance file exists
        maintenance_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "maintenance_mode")
        return os.path.exists(maintenance_file)
    except Exception as e:
        log(f"Error checking maintenance mode: {e}")
        return False