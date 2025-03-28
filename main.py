import signal
import sys
import asyncio
import time
import os
import schedule
from threading import Thread
from config import MC_LOG, COMMAND_CHANNEL, DISCORD_TOKEN
import socket

from modules.logging import log
from modules.discord import discord_bot, start_discord_bot, start_discord_monitor, broadcast_discord_message
from modules.server import server_manager

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    log(f"Received signal {signum}, shutting down gracefully...")
    
    # Only try to send message if Discord bot is ready
    if discord_bot.is_ready():
        try:
            # Send to all broadcast channels directly
            for channel_id in discord_bot.channels:
                discord_bot.send_message(channel_id, "⚠️ Watchdog is shutting down...")
            time.sleep(1)  # Brief pause to allow message to send
        except Exception as e:
            log(f"Error sending shutdown message: {e}")
    
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
    # First check if token is valid
    if not DISCORD_TOKEN or DISCORD_TOKEN == '' or DISCORD_TOKEN == 'your_discord_token_here':
        log("⚠️ Invalid Discord token. Please set DISCORD_TOKEN in environment variables.")
        return False
    
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
    
    log("⚠️ Could not connect to Discord after multiple attempts. Check your token and network connection.")
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
            broadcast_discord_message("👀 Watchdog is now monitoring the server!")
            log("✓ Discord message sent")
        else:
            log("✗ Discord bot failed to start")
        
        # Set up a periodic check for server status
        last_server_check = 0
        server_check_interval = 30  # Check server status every 30 seconds
        
        # Main monitoring loop
        while True:
            try:
                current_time = time.time()
                
                # Run scheduled tasks
                schedule.run_pending()
                
                # Periodically check server status (without logging)
                if current_time - last_server_check >= server_check_interval:
                    server_manager.check_server()
                    last_server_check = current_time
                
                time.sleep(1)
                
            except Exception as e:
                log(f"Error in main loop iteration: {e}")
                time.sleep(5)  # Brief pause before retrying
            
    except Exception as e:
        log(f"Fatal error in main loop: {e}")
        broadcast_discord_message("⚠️ Watchdog encountered a fatal error and needs to be restarted")
        raise

if __name__ == "__main__":
    main()