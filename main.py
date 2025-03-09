import signal
import sys
import asyncio
import time
import os
import schedule
from threading import Thread
from config import MC_LOG, CONSOLE_CHANNEL

from modules.logging import log
from modules.discord import discord_bot, broadcast_discord_message, start_discord_bot, start_discord_monitor
from modules.server import server_manager
from modules.maintenance import maintenance_manager
from modules.maintenance import is_maintenance_time, is_maintenance_day, is_maintenance_mode
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
    """Start Discord bot and command monitoring in separate threads"""
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            # Start the Discord bot
            discord_thread = Thread(target=start_discord_bot, daemon=True)
            discord_thread.start()
            
            # Give Discord time to connect and become ready
            wait_time = 0
            max_wait = 30  # Maximum seconds to wait for ready state
            
            while wait_time < max_wait:
                if discord_bot.is_ready():
                    # Start the command monitoring only after bot is ready
                    monitor_thread = Thread(target=start_discord_monitor, daemon=True)
                    monitor_thread.start()
                    
                    log("Discord bot and command monitoring started")
                    return True
                time.sleep(1)
                wait_time += 1
            
            if wait_time >= max_wait:
                log("Discord bot failed to become ready in time")
                retry_count += 1
                if retry_count < max_retries:
                    log(f"Retrying Discord connection (attempt {retry_count + 1}/{max_retries})")
                    time.sleep(5)
                continue
            
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                log(f"Discord connection attempt {retry_count} failed: {str(e)[:100]}... Retrying in 30 seconds")
                time.sleep(30)
            else:
                log(f"Failed to start Discord after {max_retries} attempts. Continuing without Discord.")
                return False

def main():
    try:
        # Register signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        log("🤖 Watchdog Service Starting")
        
        # Start Discord bot and monitor first
        discord_started = start_discord()
        if discord_started:
            log("✓ Discord bot started")
            # Send startup message only after we know Discord is ready
            broadcast_discord_message("👀 Watchdog is now monitoring the server!", force=True)
            log("✓ Discord message sent")
        else:
            log("⚠️ Watchdog starting without Discord integration")
        
        # Schedule maintenance and sleep checks
        maintenance_manager.schedule_maintenance()
        log("✓ Maintenance scheduled")
        sleep_manager.schedule_sleep()
        log("✓ Sleep checks scheduled")
        
        # Start monitoring threads
        log_monitor = Thread(target=monitor_minecraft_logs, daemon=True)
        log_monitor.start()
        
        # Initial maintenance check - only set the flag, don't initiate maintenance
        if is_maintenance_mode():
            log("Watchdog started during maintenance mode")
            server_manager.manual_stop = True
        
        # Main loop - handle scheduling and connection listening
        while True:
            try:
                schedule.run_pending()
                
                # Listen for connections if server is down and not in maintenance
                if not server_manager.check_server() and not server_manager.manual_stop:
                    if server_manager.listen_for_connection():
                        server_manager.start_server()
                
                time.sleep(1)
                
            except Exception as e:
                log(f"Error in main loop iteration: {e}")
                # Don't broadcast transient errors to Discord
                time.sleep(5)  # Brief pause before retrying
            
    except Exception as e:
        log(f"Fatal error in main loop: {e}")
        broadcast_discord_message("⚠️ Watchdog encountered a fatal error and needs to be restarted")
        raise

if __name__ == "__main__":
    main()