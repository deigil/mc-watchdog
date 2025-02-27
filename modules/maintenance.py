from datetime import datetime
import time
from modules.logging import log
from modules.server import server_manager
from modules.discord import broadcast_discord_message
from modules.sleep import signal_windows_sleep

class MaintenanceManager:
    def __init__(self):
        self.is_in_maintenance = False

    def is_maintenance_time(self):
        """Check if it's maintenance time (Monday or Wednesday 23:59)"""
        now = datetime.now()
        # Check if it's maintenance night (Monday or Wednesday)
        is_maintenance_night = now.weekday() in [0, 2]
        # If it's after 23:29 on maintenance night, consider it maintenance time
        return is_maintenance_night and (now.hour == 23 and now.minute >= 29)

    def is_maintenance_day(self):
        """Check if it's a maintenance day (Tuesday or Thursday)"""
        return datetime.now().weekday() in [1, 3]

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
            
            # Send initial maintenance message
            maintenance_msg = "🔧 **MAINTENANCE MODE**\n"
            maintenance_msg += f"Server will be down until {('Wednesday' if datetime.now().weekday() == 0 else 'Friday')} 8 AM"
            broadcast_discord_message(maintenance_msg)
            
            # Check if server is empty, if not, wait until it is
            while not server_manager.check_server_empty():
                log("Server not empty, waiting 5 minutes...")
                time.sleep(300)
            
            log("Server is empty, proceeding with maintenance shutdown")
            
            # Stop the Minecraft container
            server_manager.stop_server()
            
            # Signal Windows to sleep using sleep module
            signal_windows_sleep()
            
        except Exception as e:
            log(f"Error during maintenance: {e}")
            broadcast_discord_message(f"⚠️ Error during maintenance: {e}")

    def schedule_maintenance(self):
        """Schedule maintenance warnings and checks"""
        import schedule
        
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