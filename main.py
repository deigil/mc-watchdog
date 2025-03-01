import signal
import sys
import time
import os
import schedule
from threading import Thread
from config import MC_LOG

from modules.logging import log
from modules.discord import discord_bot, broadcast_discord_message
from modules.server import server_manager
from modules.maintenance import maintenance_manager
from modules.utils import is_maintenance_time, is_maintenance_day
from modules.sleep import sleep_manager

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    log(f"Received signal {signum}, shutting down gracefully...")
    broadcast_discord_message("⚠️ Watchdog is shutting down...")
    sys.exit(0)

def monitor_minecraft_logs():
    """Start the Minecraft log monitoring thread"""
    from modules.logging import log_op
    
    mc_log_path = MC_LOG
    if os.path.exists(mc_log_path):
        with open(mc_log_path, 'r') as f:
            f.seek(0, 2)  # Go to end of file
            while True:
                line = f.readline()
                if line:
                    log_op(line)
                time.sleep(0.1)

def main():
    try:
        # Register signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        log("Watchdog started")
        log(f"Working directory: {os.getcwd()}")
        
        # Send startup message
        broadcast_discord_message("👀 Watchdog is now monitoring the server!")
        
        # Schedule maintenance and sleep checks
        maintenance_manager.schedule_maintenance()
        sleep_manager.schedule_sleep()
        
        # Start monitoring threads
        log_monitor = Thread(target=monitor_minecraft_logs, daemon=True)
        discord_monitor = Thread(target=discord_bot.monitor_commands, daemon=True)
        
        log_monitor.start()
        discord_monitor.start()
        
        # Initial maintenance check
        if is_maintenance_time() or is_maintenance_day():
            server_manager.manual_stop = True
            maintenance_manager.initiate_maintenance()
        
        # Main loop - just handle scheduling and connection listening
        while True:
            schedule.run_pending()
            
            # Listen for connections if server is down and not in maintenance
            if not server_manager.check_server() and not server_manager.manual_stop:
                if server_manager.listen_for_connection():
                    server_manager.start_server()
            
            time.sleep(1)
            
    except Exception as e:
        log(f"Fatal error in main loop: {e}")
        broadcast_discord_message(f"⚠️ Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()