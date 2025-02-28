import socket
import subprocess
import time
from modules.logging import log
from config import SERVER_PORT, DOCKER_CONTAINER, MC_LOG

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
                    # Force release port if container is not running
                    self.release_port(force=True)
                return False

            # Then check if port is available
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("0.0.0.0", self.port))
                    # If we can bind, server is not listening
                    return False
                except socket.error:
                    # Can't bind, server is up
                    return True
                
        except Exception as e:
            log(f"Error checking server: {e}")
            # On error, try to force release port
            self.release_port(force=True)
            return False

    def release_port(self, force=False):
        """Release the server port"""
        try:
            # First check if port is actually in use
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', self.port))
            sock.close()
            
            if result == 0 or force:  # Port is in use or force release
                # Try to find and kill any process using the port
                try:
                    cmd = f"lsof -i :{self.port} -t"
                    pid = subprocess.check_output(cmd, shell=True).decode().strip()
                    if pid:
                        subprocess.run(['kill', '-9', pid], check=False)
                        log(f"Killed process {pid} using port {self.port}")
                except:
                    pass  # Ignore errors from lsof/kill
                
                # Try to bind to port to ensure it's released
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(('0.0.0.0', self.port))
                    sock.close()
                except Exception as e:
                    if not force:
                        raise Exception(f"Error releasing port: {e}")
            
            log(f"Port {self.port} released")
            return True
            
        except Exception as e:
            log(f"Error releasing port: {e}")
            return False

    def start_server(self):
        """Start the Minecraft server"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                log("Attempting to start server...")
                
                self.release_port()
                time.sleep(2)
                
                # Check container status first
                if self.get_container_status() != "running":
                    subprocess.run(["docker", "start", self.container], check=True)
                    log("Starting Minecraft server...")
                    
                    # Wait for server to start (3 minutes timeout)
                    for _ in range(180):
                        if self.check_server():
                            log("Server has started successfully!")
                            return True
                        time.sleep(1)
                    
                    raise Exception("Server failed to start after waiting period")
                else:
                    log("Container already running")
                    return True
                
            except Exception as e:
                if attempt < max_retries - 1:
                    log(f"Retry {attempt + 1}/{max_retries} after error: {e}")
                    time.sleep(30)  # Wait between retries
                else:
                    raise
            return False

    def stop_server(self):
        """Stop the Minecraft server"""
        try:
            if self.check_server():
                subprocess.run(["docker", "stop", self.container], check=True)
                log("Server container stopped")
                # Force release port after stopping
                self.release_port(force=True)
                self.manual_stop = True
                return True
            return False
        except Exception as e:
            log(f"Error stopping server: {e}")
            # Try to force release port on error
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
                                # Extract player name from "Blueberypie joined the game"
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
        sock = None
        try:
            self.release_port()
            time.sleep(1)
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.port))
            sock.listen()
            
            log("Listening for connection attempts...")
            
            while True:
                try:
                    conn, addr = sock.accept()
                    log(f"Connection attempt from {addr}")
                    conn.close()
                    return True
                except socket.timeout:
                    continue
        except Exception as e:
            log(f"Error in connection listener: {e}")
            return False
        finally:
            if sock:
                sock.close()
                log("Closed listening socket")

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