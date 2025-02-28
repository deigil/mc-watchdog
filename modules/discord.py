import requests
import time
from config import DISCORD_TOKEN, DISCORD_CHANNELS, CONSOLE_CHANNEL
from modules.logging import log
from modules.server import server_manager

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
                                            broadcast_discord_message("🚀 Server is starting up!")
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
                                            broadcast_discord_message("🛑 Server has been stopped")
                                            self.send_message(self.console_channel, "✅ Server stopped successfully!")
                                        else:
                                            self.send_message(self.console_channel, "❌ Failed to stop server!")
                                    else:
                                        self.send_message(self.console_channel, "ℹ️ Server is already stopped!")
                                    
                                elif content == '/sleep':
                                    log("Received sleep command from Discord")
                                    self.send_message(self.console_channel, "⚙️ Processing sleep command...")
                                    
                                    if self.server_manager.check_server():
                                        self.send_message(self.console_channel, "🛑 Stopping server first...")
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
            self.send_message(self.console_channel, "🔴 Console Bot has stopped due to an error")

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