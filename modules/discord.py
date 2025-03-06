import requests
import time
import asyncio
import threading
from config import DISCORD_TOKEN, DISCORD_CHANNELS, CONSOLE_CHANNEL
from modules.logging import log
from modules.server import server_manager
import discord
from datetime import datetime

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
        
        # Setup Discord client
        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        
        # Register event handlers
        @self.client.event
        async def on_ready():
            """Called when the bot is ready and connected to Discord"""
            log(f'Logged in as {self.client.user}')
            log(f'Bot is now visible as online in Discord')
            
            # Set appropriate status based on maintenance mode
            from modules.maintenance import is_maintenance_mode
            
            # Check if it's past 8 AM on a maintenance day
            current_time = datetime.now().time()
            current_day = datetime.now().weekday()
            morning_time = time(8, 0)
            
            # If it's past 8 AM and we're in maintenance mode, check if we should exit
            if is_maintenance_mode() and current_time >= morning_time:
                # Only exit maintenance on Wednesday (2) or Friday (4) mornings
                if current_day in [2, 4]:
                    log("It's morning after maintenance day, updating bot status to normal mode")
                    await self.client.change_presence(
                        status=discord.Status.online, 
                        activity=discord.Activity(type=discord.ActivityType.watching, name="a POG Vault 🎁")
                    )
                    log("Bot status set to online with 'Watching a POG Vault!' activity")
                    
                    # Import here to avoid circular dependency
                    from modules.maintenance import maintenance_manager
                    maintenance_manager.exit_maintenance()
                else:
                    log(f"Current day is {current_day}, staying in maintenance mode")
                    await self.client.change_presence(
                        status=discord.Status.online,
                        activity=discord.Activity(type=discord.ActivityType.playing, name="Architect Vault ⚙️")
                    )
                    log("Bot status set to online with 'Playing Architect Vault' activity")
            elif is_maintenance_mode():
                await self.client.change_presence(
                    status=discord.Status.online,
                    activity=discord.Activity(type=discord.ActivityType.playing, name="Architect Vault ⚙️")
                )
                log("Bot status set to online with 'Playing Architect Vault' activity")
            else:
                await self.client.change_presence(
                    status=discord.Status.online, 
                    activity=discord.Activity(type=discord.ActivityType.watching, name="a POG Vault 🎁")
                )
                log("Bot status set to online with 'Watching a POG Vault!' activity")
            
            # Store the client in shared state if needed
            # set_discord_client(self.client)
        
        # Setup hook for initialization
        async def setup_hook():
            log("Bot setup hook called")
            # Any additional setup can go here
        
        # Assign the setup hook
        self.client.setup_hook = setup_hook

    def send_message(self, channel_id, message):
        """Send a message to a specific Discord channel"""
        try:
            data = {'content': message}
            response = requests.post(
                f'https://discord.com/api/v10/channels/{channel_id}/messages',
                headers=self.headers,
                json=data
            )
            
            if response.status_code == 200:
                log(f"Discord message sent successfully to channel {channel_id}: {message}")
            else:
                log(f"Failed to send Discord message to channel {channel_id}: {response.status_code}")
                
        except Exception as e:
            log(f"Error sending Discord message: {e}")

    def monitor_commands(self):
        """Monitor Discord console channel for commands"""
        try:
            # Get initial last message ID by fetching most recent message
            response = requests.get(
                f'https://discord.com/api/v10/channels/{self.console_channel}/messages?limit=1',
                headers=self.headers
            )
            if response.status_code == 200 and response.json():
                last_message_id = response.json()[0]['id']
            else:
                last_message_id = None
            
            while True:
                try:
                    # Only fetch messages after our last seen message
                    url = f'https://discord.com/api/v10/channels/{self.console_channel}/messages'
                    if last_message_id:
                        url += f'?after={last_message_id}'
                    
                    response = requests.get(url, headers=self.headers)
                    
                    if response.status_code == 200:
                        messages = response.json()
                        if messages:
                            # Update last_message_id to the most recent message
                            last_message_id = messages[0]['id']
                            
                            # Process messages (newest first)
                            for message in messages:
                                content = message.get('content', '').strip().lower()
                                if content == '/start':
                                    log("Received start command from Discord")
                                    self.send_message(self.console_channel, "⚙️ Processing start command...")
                                    
                                    # Check if we're in maintenance mode
                                    from modules.maintenance import is_maintenance_mode
                                    if is_maintenance_mode():
                                        self.send_message(self.console_channel, "⚠️ Starting server during maintenance mode")
                                    
                                    if not self.server_manager.check_server():
                                        # Get current container status
                                        container_status = self.server_manager.get_container_status()
                                        
                                        if self.server_manager.start_server():
                                            self.send_message(self.console_channel, "✅ Server started successfully!")
                                            
                                            # Reset manual_stop flag to ensure listening works
                                            self.server_manager.manual_stop = False
                                            
                                            # If in maintenance mode, add a note
                                            if is_maintenance_mode():
                                                self.send_message(self.console_channel, "⚠️ Note: Server started in maintenance mode")
                                        else:
                                            self.send_message(self.console_channel, "❌ Failed to start server!")
                                    else:
                                        self.send_message(self.console_channel, "ℹ️ Server is already running!")
                                    
                                elif content == '/stop':
                                    log("Received stop command from Discord")
                                    self.send_message(self.console_channel, "⚙️ Processing stop command...")
                                    
                                    if self.server_manager.check_server():
                                        if self.server_manager.stop_server():
                                            self.send_message(self.console_channel, "✅ Server stopped successfully!")
                                        else:
                                            self.send_message(self.console_channel, "❌ Failed to stop server!")
                                    else:
                                        self.send_message(self.console_channel, "ℹ️ Server is already stopped!")
                                    
                                elif content == '/sleep':
                                    log("Received sleep command from Discord")
                                    self.send_message(self.console_channel, "⚙️ Processing sleep command...")
                                    
                                    # Import sleep_manager and use its initiate_sleep method directly
                                    from modules.sleep import sleep_manager
                                    
                                    # The initiate_sleep method already handles:
                                    # - Checking if server is empty
                                    # - Stopping the server if it's running
                                    # - Creating the sleep trigger file
                                    # - Setting manual_stop flag
                                    if sleep_manager.initiate_sleep("manual"):
                                        # Only send to console channel, not to all channels
                                        self.send_message(self.console_channel, "💤 Server is going to sleep...")
                                        self.send_message(self.console_channel, "✅ Sleep initiated successfully!")
                                    else:
                                        self.send_message(self.console_channel, "❌ Failed to initiate sleep!")
                                
                                elif content == '/players':
                                    log("Received players command from Discord")
                                    self.send_message(self.console_channel, "⚙️ Checking for players via server logs...")
                                    
                                    # Check if server is running
                                    if not self.server_manager.check_server():
                                        self.send_message(self.console_channel, "ℹ️ Server is not running")
                                        continue
                                    
                                    # Get player information
                                    is_empty, online_players = self.server_manager.check_server_empty(return_players=True)
                                    
                                    if is_empty:
                                        self.send_message(self.console_channel, "ℹ️ No players currently online")
                                    else:
                                        # Format the player list nicely
                                        player_list = ", ".join(online_players)
                                        player_count = len(online_players)
                                        
                                        # Create a nice message with emoji
                                        if player_count == 1:
                                            message = f"✅ **1 player online**: {player_list}"
                                        else:
                                            message = f"✅ **{player_count} players online**: {player_list}"
                                        
                                        self.send_message(self.console_channel, message)
                    
                    time.sleep(2)  # Wait 2 seconds between checks
                    
                except Exception as e:
                    log(f"Error monitoring Discord commands: {e}")
                    self.send_message(self.console_channel, f"⚠️ Error processing command: {e}")
                    time.sleep(5)  # Wait longer on error
                    
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

# Export convenience functions
def send_discord_message(channel_id, message):
    discord_bot.send_message(channel_id, message)

def broadcast_discord_message(message, force=False):
    """
    Send message to all configured Discord channels
    
    Args:
        message: The message to send
        force: If True, send even during maintenance mode
    """
    try:
        # Check if we're in maintenance mode
        from modules.maintenance import is_maintenance_mode
        maintenance_mode = is_maintenance_mode()
        
        # Only broadcast to all channels if not in maintenance mode or if forced
        if not maintenance_mode or force:
            # Send to all configured channels
            for channel in discord_bot.channels:
                discord_bot.send_message(channel, message)
        
        # During maintenance, always send to console channel with prefix
        if maintenance_mode and not force:
            log(f"Skipping broadcast during maintenance: {message}")
            
            # Always send to console channel during maintenance
            discord_bot.send_message(discord_bot.console_channel, f"[MAINTENANCE] {message}")
    except Exception as e:
        log(f"Error in broadcast_discord_message: {e}")

def start_discord_monitor():
    """Start the Discord command monitoring thread"""
    from threading import Thread
    monitor_thread = Thread(target=discord_bot.monitor_commands, daemon=True)
    monitor_thread.start()

def start_discord_bot():
    """Start the Discord bot"""
    try:
        discord_bot.run()
    except Exception as e:
        log(f"Error starting Discord bot: {e}")