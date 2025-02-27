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
            current_state = False  # Default to server being down
            
            if container_status == "running":
                # Then check if port is available
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(3)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind(("0.0.0.0", self.port))
                        # If we can bind, server is not listening yet
                        current_state = False
                except socket.error:
                    # Can't bind, server is up and listening
                    current_state = True
            
            # Only log state change from up to down
            if self.last_server_state and not current_state:
                log(f"Server stopped unexpectedly. Docker container status: {container_status}")
            
            self.last_server_state = current_state
            return current_state
            
        except Exception as e:
            log(f"Error checking server: {e}")
            return False

    def release_port(self):
        """Release the port by closing any existing socket"""
        try:
            # Create a temporary socket to force close any existing connections
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            temp_sock.bind(("0.0.0.0", self.port))
            temp_sock.close()
            log(f"Port {self.port} released")
        except Exception as e:
            log(f"Error releasing port: {e}")

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
            log("Attempting to stop server...")
            self.manual_stop = True  # Set flag when manually stopping
            subprocess.run(["docker", "stop", self.container], check=True)
            log("Stopped Minecraft server")
            return True
        except Exception as e:
            log(f"Error stopping server: {e}")
            self.manual_stop = False  # Reset flag if stop fails
            return False

    def check_server_empty(self):
        """Check if server is empty using logs"""
        try:
            mc_log_path = MC_LOG
            players = set()
            
            with open(mc_log_path, 'r') as f:
                for line in f:
                    if "[Server thread/INFO]" in line:
                        if "joined the game" in line:
                            player = line.split(": ")[1].split(" joined")[0]
                            players.add(player)
                        elif "left the game" in line:
                            player = line.split(": ")[1].split(" left")[0]
                            if player in players:
                                players.remove(player)
            
            return len(players) == 0
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