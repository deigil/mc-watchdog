import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Discord configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '')  # Get token from environment variable
CHAT = os.getenv('DISCORD_CHANNEL', '')  # Channel for server control commands
WATCHDOG = os.getenv('WATCHDOG_CHANNEL', '')  # Channel for watchdog

# Server configuration
DOCKER_CONTAINER = os.getenv('DOCKER_CONTAINER', 'wvh')
SERVER_PORT = int(os.getenv('SERVER_PORT'))

# File paths
WATCHDOG_LOG = os.getenv('WATCHDOG_LOG', '/workspace/watchdog/logs/watchdog.log')
OP_LOG = os.getenv('OP_LOG', '/workspace/watchdog/logs/op.log')
MC_LOG = os.getenv('MC_LOG', '/workspace/data/logs/latest.log')