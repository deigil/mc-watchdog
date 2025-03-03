import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Discord configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNELS = [
    os.getenv('DISCORD_CHANNEL_1'),
    os.getenv('DISCORD_CHANNEL_2')
]
CONSOLE_CHANNEL = os.getenv('DISCORD_CONSOLE_CHANNEL')

# Server configuration
DOCKER_CONTAINER = os.getenv('DOCKER_CONTAINER', 'wvh')
SERVER_PORT = int(os.getenv('SERVER_PORT'))

# File paths
WATCHDOG_LOG = os.getenv('WATCHDOG_LOG', '/workspace/watchdog/logs/watchdog.log')
OP_LOG = os.getenv('OP_LOG', '/workspace/watchdog/logs/op.log')
MC_LOG = os.getenv('MC_LOG', '/workspace/data/logs/latest.log')
SLEEP_TRIGGER_DIR = os.getenv('SLEEP_TRIGGER_DIR')
SLEEP_TRIGGER_FILE = os.getenv('SLEEP_TRIGGER_FILE')

# Validate required settings
required_settings = [
    ('DISCORD_TOKEN', DISCORD_TOKEN),
    ('DISCORD_CHANNEL_1', DISCORD_CHANNELS[0]),
    ('DISCORD_CHANNEL_2', DISCORD_CHANNELS[1]),
    ('DISCORD_CONSOLE_CHANNEL', CONSOLE_CHANNEL),
    ('SLEEP_TRIGGER_DIR', SLEEP_TRIGGER_DIR)
]

for setting_name, setting_value in required_settings:
    if not setting_value:
        raise ValueError(f"Missing required environment variable: {setting_name}")