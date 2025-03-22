import requests
import time
import asyncio
import threading
from config import DISCORD_TOKEN, DISCORD_CHANNELS, COMMAND_CHANNEL
from modules.logging import log
from modules.server import server_manager
from modules import is_maintenance_period  # Import from modules package
import discord
from datetime import datetime  # This is for datetime objects
import socket
from discord.ext import commands
from modules.utils import set_broadcast_function

class DiscordBot:
    def __init__(self):
        self.token = DISCORD_TOKEN
        self.channels = DISCORD_CHANNELS
        self.command_channel = COMMAND_CHANNEL
        self.headers = {
            'Authorization': f'Bot {self.token}',
            'Content-Type': 'application/json'
        }
        self.server_manager = server_manager
        self._ready = False  # Track ready state
        self._failed_channels = {}  # Initialize empty failed channels cache
        
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
            
            # Reset failed channels cache on startup
            self._failed_channels = {}
            log(f"Using Discord channels: Command={self.command_channel}, Broadcast={self.channels}")
            
            # Register broadcast function now that we're ready
            set_broadcast_function(broadcast_discord_message)
            
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
        
        # Check if this channel has been failing consistently
        if hasattr(self, '_failed_channels') and channel_id in self._failed_channels:
            last_failure, count = self._failed_channels[channel_id]
            # If channel has failed more than 5 times in the last hour, skip it
            if count > 5 and time.time() - last_failure < 3600:
                log(f"Skipping message to channel {channel_id} due to previous failures")
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
                    # Reset failure count for this channel if it exists
                    if hasattr(self, '_failed_channels') and channel_id in self._failed_channels:
                        del self._failed_channels[channel_id]
                    return True
                elif response.status_code == 404:
                    # Channel not found - likely deleted or bot doesn't have access
                    log(f"Discord channel {channel_id} not found (404)")
                    
                    # Track failed channels to avoid repeated attempts
                    if not hasattr(self, '_failed_channels'):
                        self._failed_channels = {}
                    
                    if channel_id in self._failed_channels:
                        _, count = self._failed_channels[channel_id]
                        self._failed_channels[channel_id] = (time.time(), count + 1)
                    else:
                        self._failed_channels[channel_id] = (time.time(), 1)
                    
                    # Don't retry for 404 errors
                    return False
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
        """Monitor Discord command channel for commands"""
        try:
            # Get initial last message ID by fetching most recent message
            response = requests.get(
                f'https://discord.com/api/v10/channels/{self.command_channel}/messages?limit=1',
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
                    url = f'https://discord.com/api/v10/channels/{self.command_channel}/messages'
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
                                if content == 'start':
                                    log("Received start command from Discord")
                                    
                                    # Only respond if not in maintenance mode
                                    if not is_maintenance_period():
                                        self.send_message(self.command_channel, "⚙️ Processing start command...")
                                    
                                    # Check if server is already running
                                    if self.server_manager.check_server():
                                        self.send_message(self.command_channel, "ℹ️ Server is already running!")
                                        continue
                                    
                                    # Make sure we're not already in the process of starting
                                    if self.server_manager.is_starting:
                                        self.send_message(self.command_channel, "⏳ Server is already in the process of starting...")
                                        continue
                                    
                                    # 1. Stop any active listening and release the port
                                    log("Stopping any active listening and releasing port")
                                    self.server_manager.stop_listening()
                                    
                                    # 2. Start the server using the existing function
                                    if self.server_manager.start_server():
                                        # 3. Confirm with docker ps
                                        try:
                                            import subprocess
                                            result = subprocess.run(
                                                "docker ps --filter name=wvh --format '{{.Names}} {{.Status}}'",
                                                shell=True, 
                                                capture_output=True, 
                                                text=True
                                            )
                                            if result.stdout.strip():
                                                # 4. Send confirmation to the command channel
                                                self.send_message(self.command_channel, f"✅ Server started successfully! Status: {result.stdout.strip()}")
                                            else:
                                                self.send_message(self.command_channel, "⚠️ Server start command succeeded but container not found in docker ps")
                                        except Exception as e:
                                            log(f"Error checking docker ps: {e}")
                                            self.send_message(self.command_channel, "✅ Server start command succeeded")
                                        
                                        # Reset manual_stop flag to ensure listening works
                                        self.server_manager.manual_stop = False
                                    else:
                                        self.send_message(self.command_channel, "❌ Failed to start server!")
                    
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
                        self.send_message(self.command_channel, f"⚠️ Persistent Discord connection issues detected. Will continue retrying.")
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
            
            # Check if token is valid before trying to start
            if not self.token or self.token == '' or self.token == 'your_discord_token_here':
                log(f"Invalid Discord token: '{self.token}'. Please set a valid token in environment variables.")
                return
                
            # Run the bot with proper async handling
            try:
                loop.run_until_complete(self.client.start(self.token))
            except asyncio.CancelledError:
                # Handle cancellation gracefully
                log("Discord bot task was cancelled")
            except Exception as e:
                log(f"Error in Discord bot: {e}")
            finally:
                # Always close the loop properly
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
                
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
    """Send a message to all broadcast channels"""
    if not discord_bot.is_ready():
        log(f"Discord bot not ready, message not sent: {message}")
        return False
        
    try:
        success = False
        # Send to all broadcast channels
        for channel_id in discord_bot.channels:
            try:
                # Get the channel using the client
                channel = discord_bot.client.get_channel(int(channel_id))
                if channel:
                    # Create task to send message
                    asyncio.run_coroutine_threadsafe(
                        channel.send(message),
                        discord_bot.client.loop
                    )
                    success = True
                else:
                    log(f"Could not find broadcast channel {channel_id}")
            except Exception as e:
                log(f"Error sending to channel {channel_id}: {e}")
                continue
                
        return success
    except Exception as e:
        log(f"Error broadcasting message: {e}")
        return False

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