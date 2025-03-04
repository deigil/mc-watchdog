import signal
import sys
import asyncio
import time
import os
import schedule
from threading import Thread
from config import MC_LOG, CONSOLE_CHANNEL

from modules.logging import log
from modules.discord import discord_bot, broadcast_discord_message, start_discord_bot
from modules.server import server_manager
from modules.maintenance import maintenance_manager
from modules.maintenance import is_maintenance_time, is_maintenance_day
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

def start_discord():
    """Start Discord bot in a separate thread"""
    discord_thread = Thread(target=start_discord_bot, daemon=True)
    discord_thread.start()
    time.sleep(2)  # Give Discord time to connect

def main():
    try:
        # Register signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        log("🤖 Watchdog Service Starting")
        
        # Start Discord bot first
        start_discord()
        log("✓ Discord bot started")
        
        # Send startup message
        broadcast_discord_message("👀 Watchdog is now monitoring the server!")
        log("✓ Discord message sent")
        
        # Schedule maintenance and sleep checks
        maintenance_manager.schedule_maintenance()
        log("✓ Maintenance scheduled")
        sleep_manager.schedule_sleep()
        log("✓ Sleep checks scheduled")
        
        # Start monitoring threads
        log_monitor = Thread(target=monitor_minecraft_logs, daemon=True)
        log_monitor.start()
        
        # Initial maintenance check
        if is_maintenance_time() or is_maintenance_day():
            server_manager.manual_stop = True
            maintenance_manager.initiate_maintenance()
        
        # Main loop - handle scheduling and connection listening
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