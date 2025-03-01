import socket
import subprocess
import time
from modules.logging import log
from config import SERVER_PORT, DOCKER_CONTAINER, MC_LOG
from modules import message_tracker
from datetime import datetime
from modules.utils import is_maintenance_day

class ServerManager:
    def __init__(self):
        self.port = SERVER_PORT
        self.container = DOCKER_CONTAINER
        self.manual_stop = False  # Add flag for manual stops
        self.last_server_state = True  # Add last server state

    def check_server(self):
        """Check if the Minecraft server is running"""
        try:
            # First check if container is running
            container_status = self.get_container_status()
            if container_status != "running":
                if self.last_server_state:  # If server was up before
                    log(f"Server stopped unexpectedly. Docker container status: {container_status}")
                    self.last_server_state = False  # Update state to prevent multiple messages
                    self.release_port(force=True)
                return False

            # Then check if port is available
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("0.0.0.0", self.port))
                    # If we can bind, server is not listening
                    self.last_server_state = False
                    return False
                except socket.error:
                    # Can't bind, server is up
                    self.last_server_state = True
                    return True
                
        except Exception as e:
            log(f"Error checking server: {e}")
            self.release_port(force=True)
            self.last_server_state = False
            return False

    def release_port(self, force=False):
        """Release the server port"""
        try:
            if not message_tracker.port_logged:
                log(f"Port {self.port} released")
                message_tracker.port_logged = True
            
            # Try to find and kill any process using the port
            try:
                cmd = f"lsof -i :{self.port} -t"
                pid = subprocess.check_output(cmd, shell=True).decode().strip()
                if pid:
                    subprocess.run(['kill', '-9', pid], check=False)
            except:
                pass
        except Exception as e:
            if not message_tracker.port_logged:
                log(f"Error releasing port: {e}")

    def start_server(self):
        """Start the Minecraft server"""
        try:
            # Add a flag to prevent duplicate messages and starts
            if hasattr(self, '_starting') and self._starting:
                log("Server start already in progress")
                return True
            
            self._starting = True
            self.manual_stop = False  # Reset manual stop flag when starting
            log("Attempting to start server...")
            
            self.release_port()
            time.sleep(2)
            
            # Check container status first
            if self.get_container_status() != "running":
                subprocess.run(["docker", "start", self.container], check=True)
                from modules.discord import broadcast_discord_message
                from modules.utils import is_maintenance_day
                
                # Always send startup message
                broadcast_discord_message("🚀 Server is starting up!")
                
                # Only send morning greeting if not maintenance day
                if not is_maintenance_day():
                    current_hour = datetime.now().hour
                    if 8 <= current_hour < 9:
                        broadcast_discord_message("🌅 Good morning! Server is waking up!")
                
                log("Starting Minecraft server...")
                
                # Wait for server to start (3 minutes timeout)
                for _ in range(180):
                    if self.check_server():
                        log("Server has started successfully!")
                        self._starting = False
                        return True
                    time.sleep(1)
                
                self._starting = False
                raise Exception("Server failed to start after waiting period")
            else:
                log("Container already running")
                self._starting = False
                return True
            
        except Exception as e:
            self._starting = False
            log(f"Error starting server: {e}")
            return False

    def stop_server(self):
        """Stop the Minecraft server"""
        try:
            if self.check_server():
                subprocess.run(["docker", "stop", self.container], check=True)
                log("Server container stop command sent")
                
                # First wait period (20 seconds)
                for _ in range(20):
                    if self.get_container_status() == "exited":
                        self.release_port(force=True)
                        self.manual_stop = False  # Reset manual stop to allow for new connections
                        self._listening_active = False  # Reset listening state for new connections
                        return True
                    time.sleep(1)
                
                # If still running, wait another 20 seconds
                log("Server taking longer to stop, waiting additional time...")
                for _ in range(20):
                    if self.get_container_status() == "exited":
                        self.release_port(force=True)
                        self.manual_stop = False  # Reset manual stop to allow for new connections
                        self._listening_active = False  # Reset listening state for new connections
                        return True
                    time.sleep(1)
                
                raise Exception("Server did not stop after 40 seconds")
            return False
        except Exception as e:
            log(f"Error stopping server: {e}")
            self.release_port(force=True)
            return False

    def check_server_empty(self):
        """Check if server is empty using logs"""
        try:
            mc_log_path = MC_LOG
            active_players = {}  # Track each player's state: {player: {"state": "online/offline", "last_action": timestamp}}
            
            with open(mc_log_path, 'r') as f:
                # Start from end and read last 1000 lines (configurable)
                lines = f.readlines()
                recent_lines = lines[-1000:] if len(lines) > 1000 else lines
                
                for line in recent_lines:
                    if "[Server thread/INFO] [net.minecraft.server.dedicated.DedicatedServer/]:" in line:
                        try:
                            # Extract timestamp from [28Feb2025 09:40:21.357] format
                            timestamp = line.split("]")[0].strip("[")
                            
                            if "joined the game" in line:
                                player = line.split("DedicatedServer/]: ")[1].split(" joined")[0]
                                active_players[player] = {
                                    "state": "online",
                                    "last_action": timestamp,
                                    "last_event": "join"
                                }
                                log(f"Player {player} joined at {timestamp}")
                                
                            elif "left the game" in line:
                                player = line.split("DedicatedServer/]: ")[1].split(" left")[0]
                                if player in active_players:
                                    active_players[player] = {
                                        "state": "offline",
                                        "last_action": timestamp,
                                        "last_event": "leave"
                                    }
                                    log(f"Player {player} left at {timestamp}")
                                
                        except IndexError:
                            continue  # Skip malformed lines
            
            # Check for any online players
            online_players = [
                player for player, data in active_players.items()
                if data["state"] == "online"
            ]
            
            if online_players:
                log(f"Currently online players: {', '.join(online_players)}")
                return False
            
            log("No active players detected")
            return True
            
        except Exception as e:
            log(f"Error checking logs for players: {e}")
            return False  # Assume not empty if we can't check

    def listen_for_connection(self):
        """Only listen for connections if not manually stopped"""
        if self.manual_stop:
            return False
        
        # Don't try to listen if server is already running
        if self.check_server():
            if hasattr(self, '_listening_active'):
                delattr(self, '_listening_active')  # Reset if server is running
            return False
        
        # Send connection attempt message only when we start listening for the first time
        if not hasattr(self, '_listening_active') or not self._listening_active:
            log("Starting new listening period")
            from modules.discord import broadcast_discord_message
            broadcast_discord_message("💤 Next connection attempt will wake up server!")
            self._listening_active = True
        
        sock = None
        try:
            self.release_port()
            time.sleep(1)
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.port))
            sock.listen(1)
            sock.settimeout(5)  # 5 second timeout
            
            if not hasattr(self, '_listening_logged'):
                log("Listening for connection attempts...")
                self._listening_logged = True
            
            try:
                conn, addr = sock.accept()
                log(f"Connection attempt from {addr}")
                conn.close()
                self._listening_logged = False  # Reset for next listen cycle
                delattr(self, '_listening_active')  # Use delattr instead of setting to False
                log("Connection received, starting server...")  # Added log message
                return True
            except socket.timeout:
                return False
            
        except Exception as e:
            log(f"Error in connection listener: {e}")
            return False
        finally:
            if sock:
                sock.close()

    def get_container_status(self):
        """Get Docker container status"""
        try:
            result = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", self.container], 
                                  capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception as e:
            log(f"Error getting container status: {e}")
            return "unknown"

# Create singleton instance
server_manager = ServerManager()

# Export convenience functions
def check_server():
    return server_manager.check_server()

def start_server():
    return server_manager.start_server()

def stop_server():
    return server_manager.stop_server()

def check_server_empty():
    return server_manager.check_server_empty()

def listen_for_connection():
    return server_manager.listen_for_connection()