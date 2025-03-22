import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Discord configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '')  # Get token from environment variable
COMMAND_CHANNEL = os.getenv('DISCORD_COMMAND_CHANNEL', '')  # Channel for server control commands
DISCORD_CHANNELS = [
    os.getenv('DISCORD_CHANNELS', '')
]

# Server configuration
DOCKER_CONTAINER = os.getenv('DOCKER_CONTAINER', 'wvh')
SERVER_PORT = int(os.getenv('SERVER_PORT'))

# File paths
WATCHDOG_LOG = os.getenv('WATCHDOG_LOG', '/workspace/watchdog/logs/watchdog.log')
OP_LOG = os.getenv('OP_LOG', '/workspace/watchdog/logs/op.log')
MC_LOG = os.getenv('MC_LOG', '/workspace/data/logs/latest.log')

# Validate required settings
required_settings = [
    ('DISCORD_TOKEN', DISCORD_TOKEN),
    ('DISCORD_WATCHDOG_CHANNEL', DISCORD_CHANNELS[0]),
    ('DISCORD_COMMAND_CHANNEL', COMMAND_CHANNEL)
]

for setting_name, setting_value in required_settings:
    if not setting_value:
        raise ValueError(f"Missing required environment variable: {setting_name}")