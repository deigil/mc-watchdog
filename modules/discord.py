import requests
import time
import asyncio
import threading
from config import DISCORD_TOKEN, DISCORD_CHANNELS, CONSOLE_CHANNEL
from modules.logging import log
from modules.server import server_manager
import discord

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
            
            # Set the bot's presence to online with "Watching a POG Vault!" status
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

    def broadcast(self, message):
        """Send message to all configured Discord channels"""
        for channel in self.channels:
            self.send_message(channel, message)

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
                                    
                                    if not self.server_manager.check_server():
                                        if self.server_manager.start_server():
                                            self.send_message(self.console_channel, "✅ Server started successfully!")
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
                                    
                                    if self.server_manager.check_server():
                                        if not self.server_manager.stop_server():
                                            self.send_message(self.console_channel, "❌ Failed to stop server!")
                                            continue
                                        time.sleep(2)  # Wait for server to stop
                                    
                                    broadcast_discord_message("💤 Server is going to sleep...")
                                    from modules.sleep import sleep_manager
                                    if sleep_manager.initiate_sleep("manual"):
                                        self.send_message(self.console_channel, "✅ Sleep initiated successfully!")
                                    else:
                                        self.send_message(self.console_channel, "❌ Failed to initiate sleep!")
                    
                    time.sleep(2)  # Wait 2 seconds between checks
                    
                except Exception as e:
                    log(f"Error monitoring Discord commands: {e}")
                    self.send_message(self.console_channel, f"⚠️ Error processing command: {e}")
                    time.sleep(5)  # Wait longer on error
                    
        except Exception as e:
            log(f"Fatal error in Discord monitor: {e}")

    def get_player_count(self):
        """Get player count from bot status"""
        try:
            # Find the WOLDS BOT by its user ID
            bot = self.client.get_user(1336788464041066506)  # WOLDS BOT ID
            
            if not bot:
                log("Could not find WOLDS BOT")
                return 0
            
            if not bot.activity:
                log("WOLDS BOT has no activity status - server may be offline")
                return 0
            
            # Parse the activity status
            status_text = bot.activity.name
            log(f"Bot status: {status_text}")
            
            # Check for offline status
            if "offline" in status_text.lower():
                log("Server is offline according to status")
                return 0
            
            # Check for booting status
            if "booting" in status_text.lower():
                log("Server is booting according to status")
                return 0
            
            # Normal case: "X players"
            if "players" in status_text:
                try:
                    # Extract the number before "players"
                    count = int(status_text.split("players")[0].strip())
                    log(f"Extracted player count: {count}")
                    return count
                except ValueError:
                    log(f"Could not parse player count from status: {status_text}")
                    return 0
            
            # If we get here, the status text doesn't match expected formats
            log(f"Unrecognized status format: {status_text}")
            return 0
            
        except Exception as e:
            log(f"Error getting player count from Discord: {e}")
            return 0

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

def broadcast_discord_message(message):
    discord_bot.broadcast(message)

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