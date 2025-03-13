import requests
import time
import asyncio
import threading
from config import DISCORD_TOKEN, DISCORD_CHANNELS, CONSOLE_CHANNEL
from modules.logging import log
from modules.server import server_manager
from modules import is_maintenance_period  # Import from modules package
import discord
from datetime import datetime  # This is for datetime objects

class DiscordBot:
    def __init__(self):
        self.token = DISCORD_TOKEN
        self.channels = DISCORD_CHANNELS
        self.console_channel = CONSOLE_CHANNEL
        self.headers = {
            'Authorization': f'Bot {self.token}',
            'Content-Type': 'application/json'
        }
        self.server_manager = server_manager
        self._ready = False  # Track ready state
        
        # Setup Discord client
        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        
        # Register event handlers
        @self.client.event
        async def on_ready():
            """Called when the bot is ready and connected to Discord"""
            log(f'Logged in as {self.client.user}')
            log(f'Bot is now visible as online in Discord')
            
            # Set normal status
            await self.client.change_presence(
                status=discord.Status.online, 
                activity=discord.Activity(type=discord.ActivityType.watching, name="a POG Vault 🎁")
            )
            log("Bot status set to online with 'Watching a POG Vault!' activity")
            
            self._ready = True  # Mark bot as ready
        
        # Setup hook for initialization
        async def setup_hook():
            log("Bot setup hook called")
            # Any additional setup can go here
        
        # Assign the setup hook
        self.client.setup_hook = setup_hook

    def is_ready(self):
        """Check if the bot is ready"""
        return self._ready and self.client and self.client.is_ready()

    def send_message(self, channel_id, message):
        """Send a message to a specific Discord channel"""
        # Skip sending messages during maintenance period
        if is_maintenance_period():
            log(f"[MAINTENANCE MODE] Message not sent to Discord: {message}")
            return False
            
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Wait for bot to be ready before sending
                if not self.is_ready():
                    log("Discord bot not ready, queuing message for retry")
                    time.sleep(2)  # Brief pause before retry
                    if not self.is_ready():  # Check again after pause
                        log("Discord bot still not ready, message not sent")
                        return False
                
                data = {'content': message}
                response = requests.post(
                    f'https://discord.com/api/v10/channels/{channel_id}/messages',
                    headers=self.headers,
                    json=data,
                    timeout=10  # Add timeout
                )
                
                if response.status_code == 200:
                    log(f"Discord message sent successfully to channel {channel_id}: {message}")
                    return True
                elif response.status_code == 429:  # Rate limited
                    retry_after = response.json().get('retry_after', 5)
                    log(f"Discord rate limited, waiting {retry_after} seconds")
                    time.sleep(retry_after)
                    retry_count += 1
                else:
                    log(f"Failed to send Discord message to channel {channel_id}: {response.status_code}")
                    retry_count += 1
                    time.sleep(2 * retry_count)  # Increasing delay between retries
                    
            except requests.exceptions.RequestException as e:
                log(f"Network error sending Discord message: {e}")
                retry_count += 1
                time.sleep(2 * retry_count)  # Increasing delay between retries
            except Exception as e:
                log(f"Error sending Discord message: {e}")
                return False
        
        log(f"Failed to send Discord message after {max_retries} retries")
        return False

    def monitor_commands(self):
        """Monitor Discord console channel for commands"""
        try:
            # Get initial last message ID by fetching most recent message
            response = requests.get(
                f'https://discord.com/api/v10/channels/{self.console_channel}/messages?limit=1',
                headers=self.headers,
                timeout=10  # Add timeout
            )
            if response.status_code == 200 and response.json():
                last_message_id = response.json()[0]['id']
            else:
                last_message_id = None
            
            # Track consecutive errors
            consecutive_errors = 0
            max_consecutive_errors = 5
            
            while True:
                try:
                    # Check Discord connection
                    if not discord_bot.is_ready():
                        log("Discord bot not connected, retrying in 30 seconds")
                        time.sleep(30)
                        continue
                    
                    # Only fetch messages after our last seen message
                    url = f'https://discord.com/api/v10/channels/{self.console_channel}/messages'
                    if last_message_id:
                        url += f'?after={last_message_id}'
                    
                    response = requests.get(url, headers=self.headers, timeout=10)
                    
                    if response.status_code == 200:
                        messages = response.json()
                        if messages:
                            # Update last_message_id to the most recent message
                            last_message_id = messages[0]['id']
                            
                            # Process messages (newest first)
                            for message in messages:
                                content = message.get('content', '').strip().lower()
                                if content == '!start':
                                    log("Received start command from Discord")
                                    
                                    # Only respond if not in maintenance mode
                                    if not is_maintenance_period():
                                        self.send_message(self.console_channel, "⚙️ Processing start command...")
                                    
                                    if not self.server_manager.check_server():
                                        # Get current container status
                                        container_status = self.server_manager.get_container_status()
                                        
                                        # Release port if we're listening for connections
                                        if hasattr(self.server_manager, 'is_listening') and self.server_manager.is_listening:
                                            log("Releasing port before starting server")
                                            self.server_manager.stop_listening()
                                            # Brief pause to ensure port is fully released
                                            time.sleep(1)
                                        
                                        if self.server_manager.start_server():
                                            self.send_message(self.console_channel, "✅ Server started successfully!")
                                            
                                            # Reset manual_stop flag to ensure listening works
                                            self.server_manager.manual_stop = False
                                        else:
                                            self.send_message(self.console_channel, "❌ Failed to start server!")
                                    else:
                                        self.send_message(self.console_channel, "ℹ️ Server is already running!")
                                
                                elif content == '!status':
                                    log("Received status command from Discord")
                                    
                                    # Only respond if not in maintenance mode
                                    if not is_maintenance_period():
                                        self.send_message(self.console_channel, "⚙️ Checking server status...")
                                    
                                    # Check current day
                                    current_day = datetime.now().weekday()
                                    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                                    
                                    # Check server status
                                    server_running = self.server_manager.check_server()
                                    
                                    if server_running:
                                        self.send_message(
                                            self.console_channel, 
                                            f"✅ **SERVER ONLINE**\nToday is {day_names[current_day]}. Server is running normally."
                                        )
                                    else:
                                        self.send_message(
                                            self.console_channel, 
                                            f"❌ **SERVER OFFLINE**\nToday is {day_names[current_day]}. Server is not running."
                                        )
                    
                    # Reset consecutive error counter on success
                    consecutive_errors = 0
                    
                    time.sleep(2)  # Wait 2 seconds between checks
                    
                except requests.exceptions.RequestException as e:
                    consecutive_errors += 1
                    error_msg = str(e)
                    
                    # Log the error but don't spam Discord with temporary network issues
                    log(f"Discord API connection issue: {error_msg[:200]}...")
                    
                    # Only send error to Discord if it's persistent (not just a brief network hiccup)
                    if consecutive_errors >= max_consecutive_errors:
                        self.send_message(self.console_channel, f"⚠️ Persistent Discord connection issues detected. Will continue retrying.")
                        consecutive_errors = 0  # Reset after notifying
                    
                    # Exponential backoff for retries
                    retry_delay = min(30, 2 ** consecutive_errors)
                    time.sleep(retry_delay)
                    
        except Exception as e:
            log(f"Fatal error in Discord monitor: {e}")

    def run(self):
        """Start the Discord bot"""
        try:
            log("Starting Discord bot client...")
            # Run the bot in a separate thread with its own event loop
            bot_thread = threading.Thread(target=self._run_bot_in_thread, daemon=True)
            bot_thread.start()
            log("Discord bot thread started")
        except Exception as e:
            log(f"Error starting Discord bot: {e}")
    
    def _run_bot_in_thread(self):
        """Run the bot in a separate thread"""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the bot
            loop.run_until_complete(self.client.start(self.token))
        except Exception as e:
            log(f"Error in bot thread: {e}")
        finally:
            log("Bot thread exiting")

# Create singleton instance
discord_bot = DiscordBot()

def send_discord_message(channel_id, message):
    # Skip sending messages during maintenance period
    if is_maintenance_period():
        log(f"[MAINTENANCE MODE] Message not sent to Discord: {message}")
        return False
    return discord_bot.send_message(channel_id, message)

def broadcast_discord_message(message, force=False):
    """
    Send message to all configured Discord channels
    
    Args:
        message: The message to send
        force: If True, send even if bot is not ready or during maintenance
    """
    try:
        # Check for maintenance period unless force=True
        if not force and is_maintenance_period():
            log(f"[MAINTENANCE MODE] Broadcast message not sent to Discord: {message}")
            return False
            
        # Wait briefly for bot to be ready if it's not
        if not discord_bot.is_ready():
            time.sleep(2)
        
        # Send to all configured channels
        for channel in discord_bot.channels:
            discord_bot.send_message(channel, message)
                
    except Exception as e:
        log(f"Error in broadcast_discord_message: {e}")

def start_discord_monitor():
    """Monitor Discord for commands"""
    try:
        while True:
            try:
                # Check Discord connection
                if not discord_bot.is_ready():
                    log("Discord bot not connected, retrying in 30 seconds")
                    time.sleep(30)
                    continue
                
                # Process commands
                discord_bot.monitor_commands()
                
            except Exception as e:
                log(f"Error monitoring Discord commands: {str(e)[:100]}")  # Truncate long error messages
                time.sleep(30)  # Wait before retrying
                
            time.sleep(1)
            
    except Exception as e:
        log(f"Fatal error in Discord monitor: {e}")
        # Don't try to send Discord message here as it might be the source of the error

def start_discord_bot():
    """Start the Discord bot"""
    try:
        discord_bot.run()
    except Exception as e:
        log(f"Error starting Discord bot: {e}")