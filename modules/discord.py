import requests
import time
import asyncio
import threading
from config import DISCORD_TOKEN, CHAT, WATCHDOG  # Added WATCHDOG_CHANNEL
from modules.logging import log
from modules.server import server_manager
import discord
from datetime import datetime
import socket
from discord.ext import commands
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class DiscordBot:
    def __init__(self):
        self.token = DISCORD_TOKEN
        # Store both channel IDs
        self.channels = {
            'chat': CHAT,
            'watchdog': WATCHDOG
        }
        self.headers = {
            'Authorization': f'Bot {self.token}',
            'Content-Type': 'application/json'
        }
        self.server_manager = server_manager
        self._ready = False
        self._failed_channels = {}
        
        # Setup Discord client with message content intent
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        
        # Setup session with retry strategy - simplified
        self.session = requests.Session()
        
        # Create a robust session
        self._create_session()
        
        # Instead of using DNS resolver, just use a simple cache
        self.discord_ips = {}
        
        # Initialize validation status
        self.api_validated = False

        # Track last message IDs per channel
        self.last_message_ids = {channel_id: None for channel_id in self.channels.values() if channel_id}
        
        # Register event handlers
        @self.client.event
        async def on_ready():
            """Called when the bot is ready and connected to Discord"""
            log(f'Logged in as {self.client.user}')
            log(f'Bot is now visible as online in Discord')
            
            await self.client.change_presence(
                status=discord.Status.online, 
                activity=discord.Activity(type=discord.ActivityType.watching, name="a POG Vault 🎁")
            )
            log("Bot status set to online with 'Watching a POG Vault!' activity")
            
            self._failed_channels = {}
            # Log both channels being used
            log(f"Using CHAT channel: {self.channels.get('chat')}")
            log(f"Using WATCHDOG channel: {self.channels.get('watchdog')}")
            
            self._ready = True
        
        # Setup hook for initialization
        async def setup_hook():
            log("Bot setup hook called")
        
        # Assign the setup hook
        self.client.setup_hook = setup_hook

    def is_ready(self):
        """Check if the bot is ready"""
        return self._ready and self.client and self.client.is_ready()

    def _cache_discord_ip(self):
        """Simple DNS caching without external libraries"""
        try:
            addr_info = socket.getaddrinfo('discord.com', 443, socket.AF_INET)
            if addr_info:
                ip = addr_info[0][4][0]
                self.discord_ips['discord.com'] = ip
                log(f"Cached Discord IP: {ip}")
            else:
                log("Failed to resolve discord.com")
        except Exception as e:
            log(f"Error caching Discord IP: {e}")

    def _create_session(self):
        """Create a new robust session with proper retry handling"""
        self.session = requests.Session()
        
        # Configure robust retries
        retries = Retry(
            total=10,
            backoff_factor=1.5,
            status_forcelist=[500, 502, 503, 504, 429],
            allowed_methods=["GET", "POST"],
        )
        
        # Use a longer timeout
        adapter = HTTPAdapter(max_retries=retries, pool_connections=5, pool_maxsize=10)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        # Set a default timeout
        self.session.timeout = 20

    def send_message(self, channel_id, message):
        """Send a message to a specific Discord channel"""
        # Ensure channel_id is valid before attempting to send
        if not channel_id:
            log(f"Attempted to send message to invalid channel ID: {channel_id}")
            return False
            
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Don't use discord_ip, just make the request directly
                response = self.session.post(
                    f'https://discord.com/api/v10/channels/{channel_id}/messages',
                    headers=self.headers,
                    json={'content': message},
                    timeout=15
                )
                
                if response.status_code == 200:
                    log(f"Discord message sent successfully to channel {channel_id}: {message[:80]}{'...' if len(message) > 80 else ''}") # Truncate long messages in log
                    return True
                elif response.status_code == 429:  # Rate limited
                    retry_after = response.json().get('retry_after', 5)
                    log(f"Discord rate limited on channel {channel_id}, waiting {retry_after} seconds")
                    time.sleep(retry_after)
                else:
                    log(f"Failed to send Discord message to channel {channel_id}: {response.status_code}")
                    time.sleep(2 * (retry_count + 1))
                    
                retry_count += 1
                
            except Exception as e:
                log(f"Error sending Discord message to channel {channel_id}: {e}")
                retry_count += 1
                time.sleep(5)
        
        if retry_count >= max_retries:
            log(f"Failed to send Discord message to channel {channel_id} after {max_retries} retries")
        return False

    def monitor_commands(self):
        """Monitor Discord channels for commands"""
        base_retry_delay = 5
        max_retry_delay = 300  # 5 minutes
        retry_count = 0
        
        # Validate connection once at startup
        if not self.api_validated:
            self.api_validated = self._validate_connection()
            if self.api_validated:
                log("✓ Discord API validated at startup")
            else:
                log("⚠️ Discord API validation failed at startup, but continuing anyway")
        
        # Define supported commands per channel
        supported_commands = {
            self.channels.get('chat'): ['!start'],
            self.channels.get('watchdog'): ['!stop']
        }
        # Filter out None channels just in case env vars are missing
        valid_channel_ids = [ch_id for ch_id in self.channels.values() if ch_id]

        while True:
            try:
                # Check Discord connection readiness
                if not self.is_ready():
                    log("Discord bot not connected, retrying in 30 seconds")
                    time.sleep(30)
                    continue
                
                # --- Loop through each configured channel ---
                for channel_id in valid_channel_ids:
                    current_last_id = self.last_message_ids.get(channel_id)

                    # Initialize last_message_id for this channel if not set
                    if current_last_id is None:
                        try:
                            response = self.session.get(
                                f'https://discord.com/api/v10/channels/{channel_id}/messages?limit=1',
                                headers=self.headers,
                                timeout=10
                            )
                            if response.status_code == 200:
                                messages_data = response.json()
                                if messages_data:
                                    self.last_message_ids[channel_id] = messages_data[0]['id']
                                    log(f"Initialized last message ID for channel {channel_id}: {self.last_message_ids[channel_id]}")
                                else:
                                     log(f"No messages found in channel {channel_id} to initialize ID.")
                                     # Set to 0 or a special value if needed, or just retry next loop
                                     self.last_message_ids[channel_id] = '0' # Start from beginning if channel was empty
                            else:
                                log(f"Failed to initialize last message ID for channel {channel_id}: {response.status_code}")
                                # Optionally wait a bit before continuing to next channel or next loop iteration
                                time.sleep(1) 
                        except Exception as init_err:
                             log(f"Error initializing last message ID for channel {channel_id}: {init_err}")
                             time.sleep(1) # Wait briefly on error
                        continue # Move to next channel or wait for next loop iteration

                    # Fetch new messages for this specific channel
                    fetch_url = f'https://discord.com/api/v10/channels/{channel_id}/messages'
                    # Only add 'after' if we have a valid ID (not None or '0')
                    if current_last_id and current_last_id != '0':
                        fetch_url += f'?after={current_last_id}'
                    else:
                         fetch_url += '?limit=5' # Fetch a few messages if starting from scratch

                    try:
                        response = self.session.get(fetch_url, headers=self.headers, timeout=10)
                        
                        if response.status_code == 200:
                            messages = response.json()
                            if messages:
                                message_count = len(messages)
                                # Update last message ID for this channel (newest first)
                                self.last_message_ids[channel_id] = messages[0]['id'] 
                                
                                # Filter for commands relevant to *this* channel
                                channel_commands = supported_commands.get(channel_id, [])
                                command_messages = [
                                    m for m in messages 
                                    if m.get('content', '').strip().lower() in channel_commands
                                ]

                                if command_messages:
                                    log(f"Found {len(command_messages)} command(s) in channel {channel_id} out of {message_count} new messages")
                                
                                # Process messages relevant to this channel (oldest first)
                                for message in reversed(messages):
                                    content = message.get('content', '').strip().lower()
                                    author = message.get('author', {}).get('username', 'Unknown')

                                    # --- !start command handling (CHAT channel only) ---
                                    if channel_id == self.channels.get('chat') and content == '!start':
                                        log(f"Received !start command from {author} in CHAT channel ({channel_id})")
                                        if self.server_manager.check_server():
                                            self.send_message(channel_id, "ℹ️ Server is already running!")
                                        else:
                                            log("Starting server...")
                                            # Assuming start_server returns (success, message)
                                            success, response_msg = self.server_manager.start_server()
                                            self.send_message(channel_id, response_msg)

                                    # --- !stop command handling (WATCHDOG channel only) ---
                                    elif channel_id == self.channels.get('watchdog') and content == '!stop':
                                        log(f"Received !stop command from {author} in WATCHDOG channel ({channel_id})")
                                        if self.server_manager.check_server():
                                            log("Stopping server...")
                                            # Assuming stop_server returns (success, message)
                                            success, response_msg = self.server_manager.stop_server() 
                                            self.send_message(channel_id, response_msg)
                                        else:
                                            self.send_message(channel_id, "ℹ️ Server is already stopped.")
                                    
                                    # Ignore other messages or commands in wrong channels silently
                                    
                        elif response.status_code == 404:
                             log(f"Channel {channel_id} not found or access denied.")
                             # Maybe remove this channel from valid_channel_ids list if persistent?
                        elif response.status_code == 429:
                             retry_after = response.json().get('retry_after', 2)
                             log(f"Rate limited fetching messages for channel {channel_id}, waiting {retry_after}s")
                             time.sleep(retry_after)
                        else:
                            log(f"Error fetching messages for channel {channel_id}: {response.status_code}")
                            # Add specific handling for other errors if needed

                    except requests.exceptions.RequestException as req_err:
                        log(f"Network error fetching messages for channel {channel_id}: {req_err}")
                        # Implement backoff or wait before retrying this channel
                        time.sleep(5) 
                    except Exception as fetch_err:
                        log(f"Unexpected error fetching messages for channel {channel_id}: {fetch_err}")
                        time.sleep(2) # Short wait on unexpected error

                # --- End of channel loop ---
                
                # Wait a short interval before checking all channels again
                time.sleep(3) # Check channels every 3 seconds
            
            # --- Global error handling for the main loop ---
            except Exception as e:
                log(f"Error in command monitor main loop: {str(e)[:150]}") # Truncate long errors
                retry_count += 1
                retry_delay = min(max_retry_delay, base_retry_delay * (2 ** retry_count))
                log(f"Waiting {retry_delay}s before retrying monitor loop...")
                time.sleep(retry_delay)

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
            except discord.errors.LoginFailure:
                 log(f"Discord login failed: Invalid Token provided.")
                 # Potentially stop the whole watchdog service here if login fails
            except Exception as e:
                log(f"Error in Discord bot run_until_complete: {e}")
            finally:
                # Always close the loop properly
                if not loop.is_closed():
                    log("Shutting down Discord bot async tasks and closing loop.")
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.close()
                    log("Event loop closed.")
                
        except Exception as e:
            log(f"Error setting up bot thread: {e}")
        finally:
            log("Bot thread exiting")

    def _validate_connection(self):
        """Test connection to Discord API before starting monitor"""
        try:
            response = self.session.get(
                'https://discord.com/api/v10/gateway',
                headers=self.headers,
                timeout=15
            )
            if response.status_code == 200:
                log("Successfully validated Discord API connection")
                return True
            else:
                log(f"Discord API returned status {response.status_code} during validation")
                return False
        except Exception as e:
            log(f"Discord API connection validation failed: {e}")
            return False

# --- Standalone functions (using the singleton instance) ---

# Create singleton instance
discord_bot = DiscordBot()

# (Keep send_discord_message, broadcast_discord_message, start_discord_monitor, start_discord_bot as they are, 
# they interact with the singleton instance which now handles multiple channels)

def send_discord_message(channel_id, message):
    return discord_bot.send_message(channel_id, message)

# Note: broadcast_discord_message currently uses client.get_channel which might need adjustment
# if you intend it for a specific channel or want it to broadcast to multiple.
# The current implementation sends only to the *single* channel stored in discord_bot.channel,
# which is now ambiguous. Let's update it to send to the CHAT channel by default.

def broadcast_discord_message(message):
    """Send a message to the default CHAT Discord channel"""
    chat_channel_id = discord_bot.channels.get('chat')
    if not discord_bot.is_ready():
        log(f"Discord bot not ready, broadcast message not sent: {message}")
        return False
    if not chat_channel_id:
        log(f"CHAT channel ID not configured, broadcast message not sent: {message}")
        return False
        
    try:
        # Ensure we are operating within the bot's event loop
        loop = discord_bot.client.loop
        if loop and loop.is_running():
             # Get channel object using the ID
            channel = discord_bot.client.get_channel(int(chat_channel_id))
            if channel:
                asyncio.run_coroutine_threadsafe(
                    channel.send(message),
                    loop
                )
                # log(f"Broadcast message scheduled for channel {chat_channel_id}") # Maybe too verbose
                return True
            else:
                # This might happen if the bot hasn't fully loaded guilds/channels yet
                log(f"Could not find CHAT channel object for ID {chat_channel_id}. Bot might still be starting.")
                # Fallback to direct API call if channel object not found?
                # return send_discord_message(chat_channel_id, message) # Alternative
                return False
        else:
             log(f"Discord client event loop not running. Cannot broadcast message.")
             return False
    except Exception as e:
        log(f"Error broadcasting message to CHAT channel {chat_channel_id}: {e}")
        return False

# start_discord_monitor now implicitly uses the updated monitor_commands
def start_discord_monitor():
    """Monitor Discord for commands in configured channels"""
    log("Starting Discord command monitor thread...")
    monitor_thread = threading.Thread(target=discord_bot.monitor_commands, daemon=True)
    monitor_thread.start()
    log("Discord command monitor thread started.")


def start_discord_bot():
    """Start the Discord bot connection and monitoring"""
    try:
        discord_bot.run() # Starts the connection thread
        # Wait a moment for the bot to potentially connect before starting the monitor
        time.sleep(5) 
        if discord_bot.is_ready():
             start_discord_monitor() # Starts the command monitoring thread
        else:
             log("Bot not ready after startup, command monitor not started immediately. Will retry.")
             # The monitor_commands loop itself handles retrying if not ready later
             start_discord_monitor() # Start it anyway, it will wait internally if not ready

    except Exception as e:
        log(f"Error in main start_discord_bot function: {e}")