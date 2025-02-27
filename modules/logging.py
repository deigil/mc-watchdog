from datetime import datetime
import sys
import os
from config import WATCHDOG_LOG, OP_LOG

class Logger:
    def __init__(self):
        self.ensure_log_directories()
        
    def ensure_log_directories(self):
        """Ensure all log directories exist and clear latest logs"""
        # Ensure directories exist
        os.makedirs(os.path.dirname(WATCHDOG_LOG), exist_ok=True)
        os.makedirs(os.path.dirname(OP_LOG), exist_ok=True)
        
        # Clear watchdog.log on startup
        with open(WATCHDOG_LOG, 'w') as f:
            f.write('')

    def log(self, message, log_type="watchdog"):
        """Log a message with timestamp to specified log"""
        timestamp = datetime.now()
        log_message = f"[{timestamp}] {message}"
        
        # Write to appropriate log file
        log_file = WATCHDOG_LOG if log_type == "watchdog" else OP_LOG
        with open(log_file, 'a') as f:
            f.write(log_message + '\n')
        
        # Print to console without timestamp for cleaner output
        print(message)
        sys.stdout.flush()

    def log_op_action(self, minecraft_log_line):
        """Log OP actions from Minecraft server logs"""
        if "[Server thread/INFO]" in minecraft_log_line and (
            "issued server command:" in minecraft_log_line or
            ("Stopping the server" in minecraft_log_line and "Rcon" not in minecraft_log_line) or
            ("Starting the server" in minecraft_log_line and "Rcon" not in minecraft_log_line) or
            (": [" in minecraft_log_line and any(name in minecraft_log_line for name in ["DeiSan", "Blueberypie", "yeet_SK"]))
        ):
            self.log(minecraft_log_line.strip(), log_type="op")

# Create singleton instance
logger = Logger()

# Export convenience functions
def log(message):
    logger.log(message)

def log_op(message):
    logger.log_op_action(message)