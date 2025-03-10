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
            
            # Import maintenance functions
            from modules.maintenance import is_maintenance_mode
            
            # Check maintenance mode (this will also ensure correct state based on day)
            in_maintenance = is_maintenance_mode()
            
            # Set appropriate status based on maintenance mode
            if in_maintenance:
                await self.client.change_presence(
                    status=discord.Status.online,
                    activity=discord.Activity(type=discord.ActivityType.playing, name="Architect Vault ⚙️")
                )
                log("Bot status set to maintenance mode")
            else:
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
                json=data
            )
            
            if response.status_code == 200:
                log(f"Discord message sent successfully to channel {channel_id}: {message}")
                return True
            else:
                log(f"Failed to send Discord message to channel {channel_id}: {response.status_code}")
                return False
                
        except Exception as e:
            log(f"Error sending Discord message: {e}")
            return False

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
                                
                                elif content == '/maintenance':
                                    log("Received maintenance command from Discord")
                                    self.send_message(self.console_channel, "⚙️ Checking maintenance status...")
                                    
                                    # Import maintenance functions
                                    from modules.maintenance import is_maintenance_mode
                                    
                                    # Check current day
                                    current_day = datetime.now().weekday()
                                    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                                    
                                    # Check maintenance status
                                    in_maintenance = is_maintenance_mode()
                                    
                                    if in_maintenance:
                                        # Determine when maintenance will end
                                        if current_day == 1:  # Tuesday
                                            end_day = "Wednesday"
                                        elif current_day == 3:  # Thursday
                                            end_day = "Friday"
                                        else:
                                            end_day = day_names[(current_day + 1) % 7]
                                        
                                        self.send_message(
                                            self.console_channel, 
                                            f"🔧 **MAINTENANCE MODE ACTIVE**\nToday is {day_names[current_day]}. Maintenance will end on {end_day} at 8:00 AM."
                                        )
                                    else:
                                        # Determine when next maintenance will start
                                        days_to_monday = (0 - current_day) % 7
                                        days_to_wednesday = (2 - current_day) % 7
                                        
                                        if days_to_monday == 0:
                                            next_maintenance = "tonight at 11:59 PM"
                                        elif days_to_wednesday == 0:
                                            next_maintenance = "tonight at 11:59 PM"
                                        elif days_to_monday < days_to_wednesday:
                                            next_maintenance = f"on Monday night (in {days_to_monday} days)"
                                        else:
                                            next_maintenance = f"on Wednesday night (in {days_to_wednesday} days)"
                                        
                                        self.send_message(
                                            self.console_channel, 
                                            f"✅ **NORMAL MODE**\nToday is {day_names[current_day]}. Next maintenance will begin {next_maintenance}."
                                        )
                    
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
        force: If True, send even during maintenance mode without prefix
    """
    try:
        # Check if we're in maintenance mode
        from modules.maintenance import is_maintenance_mode
        maintenance_mode = is_maintenance_mode()
        
        # Wait briefly for bot to be ready if it's not
        if not discord_bot.is_ready():
            time.sleep(2)
        
        if maintenance_mode and not force:
            # During maintenance, add a prefix to the message
            prefixed_message = f"[⚙️] {message}"
            log(f"Sending maintenance-prefixed message: {prefixed_message}")
            
            # Send to all configured channels with the prefix
            for channel in discord_bot.channels:
                discord_bot.send_message(channel, prefixed_message)
        else:
            # Normal case or forced message - send to all channels without prefix
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