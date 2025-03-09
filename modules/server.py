import socket
import subprocess
import time
from modules.logging import log
from config import SERVER_PORT, DOCKER_CONTAINER, MC_LOG
from modules import message_tracker
from datetime import datetime

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
            container_status = self.get_container_status()
            log(f"Current container status: {container_status}")
            
            if container_status != "running":
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
                    log(f"Command stdout: {result.stdout}")
                    log(f"Command stderr: {result.stderr}")
                    
                    if result.returncode != 0:
                        self._starting = False
                        raise Exception(f"Docker start command failed with exit code {result.returncode}: {result.stderr}")
                    
                    # If we get here, the command succeeded
                    from modules.discord import broadcast_discord_message
                    
                    # Always send startup message
                    broadcast_discord_message("🚀 Server is starting up!")
                    
                    log("Starting Minecraft server...")
                    
                    # Wait for server to start (4 minutes timeout)
                    server_started = False
                    for i in range(240):  # 4 minutes = 240 seconds
                        # Check container health status first
                        health_status = self.get_container_status()
                        
                        # Every 30 seconds, send a status update
                        if i > 0 and i % 30 == 0:
                            log(f"Server startup in progress... Health status: {health_status}")
                            
                            # If unhealthy after 30 seconds, consider it failed
                            if health_status == "unhealthy" and i >= 30:
                                log("Container is unhealthy, server failed to start properly")
                                broadcast_discord_message("❌ Server failed to start properly (unhealthy container)")
                                self.stop_server()
                                self._starting = False
                                return False
                            
                            # If still starting after 3 minutes, send an update
                            if i >= 180:
                                log("Server is taking longer than usual to start...")
                        
                        # Only consider server ready when container is healthy AND port is responding
                        if health_status == "healthy" and self.check_server():
                            log("Server has started successfully and is healthy!")
                            broadcast_discord_message("✅ Server is now online and ready!")
                            self._starting = False
                            server_started = True
                            return True
                        
                        time.sleep(1)
                    
                    # If we get here, the server didn't start within the timeout
                    if not server_started:
                        log("Server failed to start after 4 minute timeout")
                        
                        # Check final health status
                        health_status = self.get_container_status()
                        log(f"Final container health status: {health_status}")
                        
                        # Stop the container
                        log("Stopping container due to failed start")
                        self.stop_server()
                        
                        # Send failure message with health status
                        broadcast_discord_message(f"❌ Server failed to start after 4 minutes (status: {health_status})")
                        
                        self._starting = False
                        return False
                    
                except Exception as e:
                    self._starting = False
                    raise e  # Re-raise to be caught by outer try/except
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

    def check_server_empty(self, return_players=False):
        """
        Check if the server has no players by parsing server logs
        
        Args:
            return_players: If True, return (is_empty, online_players_list) instead of just is_empty
        """
        try:
            log("Checking if server is empty...")
            
            # First check if server is running
            container_status = self.get_container_status()
            if container_status != "running":
                log("Server is not running, considering it empty")
                return (True, []) if return_players else True
            
            # Parse logs to check for players
            log("Checking server logs for player activity...")
            mc_log_path = MC_LOG
            active_players = {}  # Track each player's state: {player: {"state": "online/offline", "last_action": timestamp}}
            
            with open(mc_log_path, 'r') as f:
                # Start from end and read last 1000 lines (configurable)
                lines = f.readlines()
                recent_lines = lines[-1000:] if len(lines) > 1000 else lines
                
                log(f"Analyzing {len(recent_lines)} recent log lines")
                
                for line in recent_lines:
                    if "[Server thread/INFO]" in line:
                        try:
                            # Extract timestamp from log line
                            timestamp_part = line.split("]")[0].strip("[")
                            
                            # Check for player join events
                            if "joined the game" in line:
                                player = line.split("]: ")[1].split(" joined")[0]
                                active_players[player] = {
                                    "state": "online",
                                    "last_action": timestamp_part,
                                    "last_event": "join"
                                }
                                log(f"Log shows player {player} joined at {timestamp_part}")
                                
                            # Check for player leave events
                            elif "left the game" in line:
                                player = line.split("]: ")[1].split(" left")[0]
                                if player in active_players:
                                    active_players[player] = {
                                        "state": "offline",
                                        "last_action": timestamp_part,
                                        "last_event": "leave"
                                    }
                                    log(f"Log shows player {player} left at {timestamp_part}")
                            
                        except IndexError:
                            continue  # Skip malformed lines
            
            # Check for any online players
            online_players = [
                player for player, data in active_players.items()
                if data["state"] == "online"
            ]
            
            if online_players:
                log(f"Log analysis found online players: {', '.join(online_players)}")
                return (False, online_players) if return_players else False
            
            log("Log analysis found no active players")
            return (True, []) if return_players else True
            
        except Exception as e:
            log(f"Error checking if server empty: {e}")
            log("Assuming server is NOT empty due to error")
            return (False, []) if return_players else False  # Assume not empty if we can't check

    def listen_for_connection(self):
        """Only listen for connections if not manually stopped"""
        if self.manual_stop:
            return False
        
        # Don't try to listen if server is already running
        if self.check_server():
            if hasattr(self, '_listening_active'):
                delattr(self, '_listening_active')  # Reset if server is running
            return False
        
        # Check if we're in maintenance mode
        from modules.maintenance import is_maintenance_mode
        
        # Send connection attempt message only when we start listening for the first time
        # and not in maintenance mode
        if (not hasattr(self, '_listening_active') or not self._listening_active) and not is_maintenance_mode():
            log("Starting new listening period")
            from modules.discord import broadcast_discord_message
            broadcast_discord_message("💤 Next connection attempt will wake up server!")
            self._listening_active = True
        elif not hasattr(self, '_listening_active') or not self._listening_active:
            # Just log without sending message during maintenance
            log("Starting new listening period (maintenance mode - no message sent)")
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
            # Use shell=True to match terminal behavior
            result = subprocess.run(
                f"docker inspect -f '{{{{.State.Status}}}}' {self.container}",
                shell=True,
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                status = result.stdout.strip().replace("'", "")  # Remove any quotes
                
                # Only log if status changed or if this is the first check
                if not hasattr(self, '_last_logged_status') or self._last_logged_status != status:
                    log(f"Container status: {status}")
                    self._last_logged_status = status
                
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

def check_server_empty():
    return server_manager.check_server_empty()

def listen_for_connection():
    return server_manager.listen_for_connection()

# Instead, define a helper function to check maintenance day
def _is_maintenance_day():
    """Check if it's a maintenance day (Tuesday or Thursday)"""
    return datetime.now().weekday() in [1, 3]