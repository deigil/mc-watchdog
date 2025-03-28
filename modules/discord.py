import requests
import time
import asyncio
import threading
from config import DISCORD_TOKEN, DISCORD_CHANNELS, COMMAND_CHANNEL
from modules.logging import log
from modules.server import server_manager
import discord
from datetime import datetime
import socket
from discord.ext import commands
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import dns.resolver
import dns.exception

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
        self._ready = False
        self._failed_channels = {}
        
        # Setup Discord client
        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        # Setup simple DNS resolver with caching
        self.resolver = dns.resolver.Resolver()
        self.resolver.cache = dns.resolver.Cache()  # Simpler cache implementation
        self.discord_ip = None
        self._cache_discord_ip()
        
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
        """Cache Discord's IP address"""
        try:
            answers = self.resolver.resolve('discord.com', 'A')
            self.discord_ip = answers[0].to_text()
            log(f"Successfully cached Discord IP: {self.discord_ip}")
        except dns.exception.DNSException as e:
            log(f"DNS resolution failed for discord.com: {e}")
            self.discord_ip = None

    def send_message(self, channel_id, message):
        """Send a message to a specific Discord channel"""
        # Increase timeout and add exponential backoff
        max_retries = 5  # Increased from 3
        base_timeout = 15  # Increased from 10
        
        retry_count = 0
        while retry_count < max_retries:
            try:
                # Try to resolve DNS if we don't have it cached
                if not self.discord_ip:
                    self._cache_discord_ip()
                
                response = self.session.post(
                    f'https://discord.com/api/v10/channels/{channel_id}/messages',
                    headers=self.headers,
                    json={'content': message},
                    timeout=15  # Increased timeout
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
                    
            except requests.exceptions.ConnectionError as e:
                if "Name or service not known" in str(e):
                    # DNS resolution failed, try to refresh cache
                    self._cache_discord_ip()
                retry_count += 1
                time.sleep(min(30, 2 ** retry_count))
            except Exception as e:
                log(f"Error sending Discord message: {e}")
                retry_count += 1
                time.sleep(min(30, 2 ** retry_count))
        
        log(f"Failed to send Discord message after {max_retries} retries")
        return False

    def monitor_commands(self):
        """Monitor Discord channels for commands"""
        base_retry_delay = 5
        max_retry_delay = 300  # 5 minutes
        retry_count = 0
        
        while True:
            try:
                # Add DNS error handling
                try:
                    socket.getaddrinfo('discord.com', 443)
                except socket.gaierror:
                    log("DNS resolution failed for discord.com, waiting before retry...")
                    time.sleep(min(max_retry_delay, base_retry_delay * (2 ** retry_count)))
                    retry_count += 1
                    continue
                    
                # Reset retry count on successful connection
                retry_count = 0
                
                # Check Discord connection
                if not self.is_ready():
                    log("Discord bot not connected, retrying in 30 seconds")
                    time.sleep(30)
                    continue
                
                # Get initial last message IDs for both channels
                last_message_ids = {}
                
                # Command channel
                response = self.session.get(
                    f'https://discord.com/api/v10/channels/{self.command_channel}/messages?limit=1',
                    headers=self.headers,
                    timeout=10
                )
                if response.status_code == 200 and response.json():
                    last_message_ids[self.command_channel] = response.json()[0]['id']
                
                # Broadcast channel
                response = self.session.get(
                    f'https://discord.com/api/v10/channels/1342194255397130381/messages?limit=1',
                    headers=self.headers,
                    timeout=10
                )
                if response.status_code == 200 and response.json():
                    last_message_ids['1342194255397130381'] = response.json()[0]['id']
                
                # Monitor both channels
                for channel_id in [self.command_channel, '1342194255397130381']:
                    # Only fetch messages after our last seen message
                    url = f'https://discord.com/api/v10/channels/{channel_id}/messages'
                    if channel_id in last_message_ids:
                        url += f'?after={last_message_ids[channel_id]}'
                    
                    response = self.session.get(url, headers=self.headers, timeout=10)
                    
                    if response.status_code == 200:
                        messages = response.json()
                        if messages:
                            # Update last_message_id for this channel
                            last_message_ids[channel_id] = messages[0]['id']
                            
                            # Process messages (newest first)
                            for message in messages:
                                content = message.get('content', '').strip()
                                msg_channel_id = message.get('channel_id')
                                
                                # Handle !start command in broadcast channel
                                if msg_channel_id == '1342194255397130381' and content.lower() == '!start':
                                    log("Received start command from Discord broadcast channel")
                                    
                                    # Start the server and send the response message
                                    success, message = self.server_manager.start_server()
                                    self.send_message(msg_channel_id, message)
                                    continue
                                
                                # Handle original start command in command channel
                                elif msg_channel_id == self.command_channel and content.lower() == 'start':
                                    log("Received start command from Discord command channel")
                                    
                                    # Start the server and send the response message
                                    success, message = self.server_manager.start_server()
                                    self.send_message(self.command_channel, message)
                                    continue
                
                time.sleep(2)  # Wait 2 seconds between checks
                
            except requests.exceptions.RequestException as e:
                retry_delay = min(max_retry_delay, base_retry_delay * (2 ** retry_count))
                log(f"Discord API connection issue (waiting {retry_delay}s): {str(e)[:100]}...")
                time.sleep(retry_delay)
                retry_count += 1

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
    return discord_bot.send_message(channel_id, message)

def broadcast_discord_message(message):
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

def start_discord_bot():
    """Start the Discord bot"""
    try:
        discord_bot.run()
    except Exception as e:
        log(f"Error starting Discord bot: {e}")