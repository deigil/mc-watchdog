import signal
import sys
import time
import os
import schedule
from threading import Thread
from config import MC_LOG

from modules.logging import log
from modules.discord import discord_bot, broadcast_discord_message, start_discord_monitor
from modules.server import server_manager
from modules.maintenance import maintenance_manager, is_maintenance_time, is_maintenance_day
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
    last_server_state = server_manager.check_server()
    
    if os.path.exists(mc_log_path):
        with open(mc_log_path, 'r') as f:
            f.seek(0, 2)  # Go to end of file
            while True:
                line = f.readline()
                if line:
                    log_op(line)
                    
                # Just track server state without sending messages
                current_server_state = server_manager.check_server()
                last_server_state = current_server_state
                    
                time.sleep(0.1)

def main():
    try:
        # Register signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        log("Watchdog started")
        log(f"Working directory: {os.getcwd()}")
        
        # Send startup messages
        broadcast_discord_message("👀 Watchdog is now monitoring the server!")
        
        # If server is down and not in maintenance, let players know they can wake it
        if not server_manager.check_server() and not is_maintenance_time() and not is_maintenance_day():
            broadcast_discord_message("💤 Next connection attempt will wake up server!")
        
        # Schedule maintenance and sleep checks
        maintenance_manager.schedule_maintenance()
        sleep_manager.schedule_sleep()
        
        # Start monitoring threads
        log_monitor = Thread(target=monitor_minecraft_logs, daemon=True)
        discord_monitor = Thread(target=start_discord_monitor, daemon=True)
        
        log_monitor.start()
        discord_monitor.start()
        
        last_message = "💤 Next connection attempt will wake up server!"  # Set initial message
        last_server_state = server_manager.check_server()  # Track server state
        
        # Set initial manual_stop state based on maintenance
        if is_maintenance_time() or is_maintenance_day():
            server_manager.manual_stop = True
            broadcast_discord_message("🔧 Server is in maintenance mode")
            last_message = "🔧 Server is in maintenance mode"
        
        while True:
            schedule.run_pending()  # Run any scheduled tasks
            
            current_server_state = server_manager.check_server()
            
            if not current_server_state:  # Server is down
                current_message = ""
                
                # Only listen for connections if not maintenance time or maintenance day
                # and not manually stopped
                if not is_maintenance_time() and not is_maintenance_day() and not server_manager.manual_stop:
                    if server_manager.listen_for_connection():
                        log("Connection attempt received, starting server...")
                        if server_manager.start_server():  # Only send message if start successful
                            current_message = "🚀 Server is starting up!"
                    else:
                        # Only broadcast sleep message if not in maintenance and not manually stopped
                        current_message = "💤 Next connection attempt will wake up server!"
                elif is_maintenance_time() or is_maintenance_day():
                    # Override any sleep messages during maintenance periods
                    current_message = "🔧 Server is in maintenance mode"
                
                # Only send message if it's different from the last one
                if current_message and current_message != last_message:
                    broadcast_discord_message(current_message)
                    last_message = current_message
            
            last_server_state = current_server_state
            time.sleep(1)
            
    except Exception as e:
        log(f"Fatal error in main loop: {e}")
        broadcast_discord_message(f"⚠️ Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()