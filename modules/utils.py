from datetime import datetime, time
from modules.logging import log

def is_maintenance_day():
    """Check if it's a maintenance day (Tuesday or Thursday)"""
    return datetime.now().weekday() in [1, 3]

def is_maintenance_time():
    """Check if it's maintenance time (Monday or Wednesday 23:59)"""
    now = datetime.now()
    # Check if it's maintenance night (Monday or Wednesday)
    is_maintenance_night = now.weekday() in [0, 2]
    # If it's after 23:29 on maintenance night, consider it maintenance time
    return is_maintenance_night and (now.hour == 23 and now.minute >= 29)

def is_restart_time():
    """Check if it's time to restart after maintenance (Wednesday or Friday 8:00)"""
    now = datetime.now()
    return (now.weekday() in [2, 4] and  # Wednesday or Friday
            now.hour == 8 and now.minute == 0)

# Shared state for Discord client
class SharedState:
    """Singleton for sharing state between modules"""
    def __init__(self):
        self.discord_client = None
        
    def set_discord_client(self, client):
        self.discord_client = client
        
    def get_discord_client(self):
        return self.discord_client

# Create singleton instance
shared_state = SharedState()

# Export convenience functions
def set_discord_client(client):
    shared_state.set_discord_client(client)

def get_discord_client():
    return shared_state.get_discord_client()

def get_player_count():
    """Get the number of players currently online"""
    try:
        # First check if the server is actually running
        from modules.server import server_manager
        
        # If server is not running, we know there are 0 players
        container_status = server_manager.get_container_status()
        if container_status != "running":
            log(f"Server is not running (status: {container_status}), player count is 0")
            return 0
            
        # Use the DiscordBot's get_player_count method
        from modules.discord import discord_bot
        return discord_bot.get_player_count()
        
    except Exception as e:
        log(f"Error getting player count: {str(e)}")
        log("Assuming server is empty due to error")
        return 0 