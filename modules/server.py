import socket
import subprocess
import time  # This is the time module for sleep()
from modules.logging import log
from config import SERVER_PORT, DOCKER_CONTAINER, MC_LOG
from modules import message_tracker, is_maintenance_period  # Import from modules package
from datetime import datetime  # This is for datetime objects

class ServerManager:
    def __init__(self):
        self.port = SERVER_PORT
        self.container = DOCKER_CONTAINER
        self.manual_stop = False  # Flag for manual stops
        self.last_server_state = True  # Last server state
        self.is_starting = False  # Flag to track server startup process

    def check_container_health(self):
        """Check if the container exists and is healthy"""
        try:
            # Check if container exists and get its status
            result = subprocess.run(
                f"docker ps -a --filter name={self.container} --format '{{{{.Status}}}}'",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                log(f"Error checking container status: {result.stderr}")
                return False
                
            status = result.stdout.strip()
            
            # If container doesn't exist, status will be empty
            if not status:
                log(f"Container {self.container} does not exist")
                return False
                
            # Check if container is running and healthy
            if "Up" in status and "healthy" in status:
                # Only log status changes
                if not hasattr(self, '_last_health_status') or self._last_health_status != True:
                    log(f"Container is healthy: {status}")
                    self._last_health_status = True
                return True
            else:
                # Only log status changes
                if not hasattr(self, '_last_health_status') or self._last_health_status != False:
                    log(f"Container is not healthy: {status}")
                    self._last_health_status = False
                return False
                
        except Exception as e:
            log(f"Error checking container health: {e}")
            return False

    def check_server(self):
        """Check if the Minecraft server is running and accepting connections"""
        try:
            # First check if container is running and healthy
            if not self.check_container_health():
                if self.last_server_state:  # If server was up before
                    log(f"Server stopped unexpectedly. Container is not healthy.")
                    self.last_server_state = False
                    self.release_port(force=True)
                return False

            # Then try to connect to the port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                try:
                    # Try to connect to the port
                    sock.connect(("localhost", self.port))
                    # If we can connect, server is up
                    self.last_server_state = True
                    return True
                except (socket.error, ConnectionRefusedError):
                    # Can't connect, server is not ready
                    self.last_server_state = False
                    return False
                
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
            self.is_starting = True  # Set global starting flag
            self.manual_stop = False  # Reset manual stop flag when starting
            log("Attempting to start server...")
            
            # First, explicitly stop any active listening
            self.stop_listening()
            
            # Check container status first
            if not self.check_container_health():
                try:
                    # Log the exact command we're about to run
                    start_cmd = ["docker", "start", self.container]
                    log(f"Executing command: {' '.join(start_cmd)}")
                    
                    # Run with shell=True to match terminal behavior
                    result = subprocess.run(
                        ' '.join(start_cmd),
                        shell=True,
                        capture_output=True, 
                        text=True
                    )
                    
                    # Log the complete result
                    log(f"Command exit code: {result.returncode}")
                    if result.stdout.strip():
                        log(f"Command stdout: {result.stdout}")
                    if result.stderr.strip():
                        log(f"Command stderr: {result.stderr}")
                    
                    if result.returncode != 0:
                        self._starting = False
                        self.is_starting = False  # Reset global starting flag
                        raise Exception(f"Docker start command failed with exit code {result.returncode}: {result.stderr}")
                    
                    # If we get here, the command succeeded
                    from modules.discord import broadcast_discord_message
                    
                    # Always send startup message unless in maintenance mode
                    if not is_maintenance_period():
                        broadcast_discord_message("🚀 Server is starting up! Give it like 4 minutes to start...")
                    else:
                        log("[MAINTENANCE MODE] Suppressed server startup message to Discord")
                    
                    log("Starting Minecraft server...")
                    
                    # Wait for server to start (4 minutes timeout)
                    server_started = False
                    start_time = time.time()
                    
                    while time.time() - start_time < 240:  # 4 minutes timeout
                        # Check container health and server response
                        if self.check_container_health() and self.check_server():
                            log("Server has started successfully!")
                            self._starting = False
                            self.is_starting = False  # Reset global starting flag
                            return True
                        
                        time.sleep(1)
                    
                    # If we get here, the server didn't start within the timeout
                    log("Server failed to start after 4 minute timeout")
                    self.stop_server()
                    self._starting = False
                    self.is_starting = False  # Reset global starting flag
                    return False
                    
                except Exception as e:
                    self._starting = False
                    self.is_starting = False  # Reset global starting flag
                    raise e  # Re-raise to be caught by outer try/except
            else:
                log("Container already running and healthy")
                if self.check_server():
                    log("Server is already running and responding")
                    self._starting = False
                    self.is_starting = False  # Reset global starting flag
                    return True
                else:
                    log("Container is healthy but server is not responding, stopping container...")
                    self.stop_server()
                    self._starting = False
                    self.is_starting = False  # Reset global starting flag
                    return False
            
        except Exception as e:
            self._starting = False
            self.is_starting = False  # Reset global starting flag
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
                        return True
                    time.sleep(1)
                
                # If still running, wait another 20 seconds
                log("Server taking longer to stop, waiting additional time...")
                for _ in range(20):
                    if self.get_container_status() == "exited":
                        self.release_port(force=True)
                        self.manual_stop = False  # Reset manual stop to allow for new connections
                        return True
                    time.sleep(1)
                
                raise Exception("Server did not stop after 40 seconds")
            return False
        except Exception as e:
            log(f"Error stopping server: {e}")
            self.release_port(force=True)
            return False

    def stop_listening(self):
        """Stop listening for connections and release the port"""
        try:
            log("Stopping connection listener and releasing port")
            self.release_port(force=True)
            
            # Reset listening flags
            if hasattr(self, '_listening_active'):
                delattr(self, '_listening_active')
            if hasattr(self, '_listening_logged'):
                delattr(self, '_listening_logged')
                
            # Small delay to ensure port is fully released
            time.sleep(1)
            return True
        except Exception as e:
            log(f"Error stopping listener: {e}")
            return False

    def listen_for_connection(self):
        """Listen for connection attempts to start the server"""
        # Don't listen if server is starting up
        if self.is_starting:
            return False
            
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
            
            # Only send message if not in maintenance mode
            if not is_maintenance_period():
                broadcast_discord_message("💤 Next connection attempt will wake up server!")
            else:
                log("[MAINTENANCE MODE] Suppressed connection listening message to Discord")
                
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
                log("Connection received, starting server...")
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
            # Use shell=True to match terminal behavior
            result = subprocess.run(
                f"docker inspect -f '{{{{.State.Status}}}}' {self.container}",
                shell=True,
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                status = result.stdout.strip().replace("'", "")  # Remove any quotes
                
                # Only log if status changed (ignoring timestamps in comparison)
                current_state = status.split()[0] if status else "unknown"  # Get first word of status
                if not hasattr(self, '_last_logged_state') or self._last_logged_state != current_state:
                    log(f"Container state changed to: {status}")
                    self._last_logged_state = current_state
                
                return status
            else:
                # Always log errors
                log(f"Error getting container status: {result.stderr}")
                return "unknown"
        except Exception as e:
            log(f"Exception getting container status: {e}")
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

def listen_for_connection():
    return server_manager.listen_for_connection()