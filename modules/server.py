import socket
import subprocess
import time  # This is the time module for sleep()
from modules.logging import log
from config import SERVER_PORT, DOCKER_CONTAINER, MC_LOG
from modules import message_tracker, is_maintenance_period  # Import from modules package
from datetime import datetime  # This is for datetime objects
from modules.connection_tracker import connection_tracker
import ipaddress
import json
import re

def get_real_ip(addr):
    """Get the real client IP, handling Docker network IPs"""
    ip = addr[0]
    try:
        # Clean IP if it's in CIDR notation
        if '/' in ip:
            ip = ip.split('/')[0]
            
        ip_obj = ipaddress.ip_address(ip)
        
        # For Docker bridge network IPs, try to get the actual source
        if ip_obj.is_private:
            try:
                # First check the bridge network specifically
                result = subprocess.run(
                    "docker network inspect bridge -f '{{json .IPAM.Config}}'",
                    shell=True, capture_output=True, text=True
                )
                if result.returncode == 0:
                    network_config = json.loads(result.stdout)
                    for config in network_config:
                        subnet = config.get('Subnet', '')
                        if subnet and ipaddress.ip_address(ip) in ipaddress.ip_network(subnet):
                            # This IP is from the bridge network, try to get the source port mapping
                            port_result = subprocess.run(
                                f"docker port wvh",  # Using the container name from docker-compose
                                shell=True, capture_output=True, text=True
                            )
                            if port_result.returncode == 0:
                                # Parse port mappings to find the source IP
                                for line in port_result.stdout.splitlines():
                                    if '46945/tcp' in line:  # The port from docker-compose
                                        parts = line.split(' -> ')
                                        if len(parts) == 2:
                                            source = parts[1].split(':')[0]
                                            if source != '0.0.0.0':
                                                log(f"Found source IP {source} from port mapping")
                                                return source
                            
                            # If we can't get the source from port mapping, try to get the gateway
                            gateway_result = subprocess.run(
                                "docker network inspect bridge -f '{{range .Containers}}{{.IPv4Address}}{{end}}'",
                                shell=True, capture_output=True, text=True
                            )
                            if gateway_result.returncode == 0 and gateway_result.stdout.strip():
                                container_ips = gateway_result.stdout.strip().split('/')
                                if container_ips:
                                    log(f"Connection through Docker bridge network from {ip}")
                                    # This is a connection through Docker bridge, use the original IP
                                    # as it's likely the actual client IP
                                    return ip
                            
            except Exception as e:
                log(f"Error inspecting Docker network: {e}")
                
        # If we get here and it's not a private IP, it's already an external IP
        if not ip_obj.is_private:
            log(f"IP {ip} is already an external IP")
        else:
            log(f"Using original IP {ip} (likely direct connection)")
            
        return ip
    except ValueError as e:
        log(f"Invalid IP address format: {e}")
        return ip

def get_container_memory_stats(container_name, samples=5, interval=2):
    """Get container memory usage statistics
    Args:
        container_name: Name of the container
        samples: Number of samples to collect
        interval: Seconds between samples
    Returns:
        dict with min, max, avg memory usage in MB
    """
    memory_samples = []
    
    try:
        for _ in range(samples):
            result = subprocess.run(
                f'docker stats {container_name} --no-stream --format "{{{{.MemUsage}}}}"',
                shell=True, capture_output=True, text=True
            )
            if result.returncode == 0:
                # Parse memory usage (format is like "1.2GiB / 15.5GiB")
                mem_str = result.stdout.strip().split('/')[0].strip()
                # Convert to MB for consistent comparison
                if 'GiB' in mem_str:
                    mb = float(mem_str.replace('GiB', '')) * 1024
                elif 'MiB' in mem_str:
                    mb = float(mem_str.replace('MiB', ''))
                else:
                    continue
                    
                memory_samples.append(mb)
                time.sleep(interval)
                
        if memory_samples:
            avg_mem = sum(memory_samples) / len(memory_samples)
            min_mem = min(memory_samples)
            max_mem = max(memory_samples)
            return {
                'min': f"{min_mem:.1f}MB",
                'max': f"{max_mem:.1f}MB",
                'avg': f"{avg_mem:.1f}MB",
                'samples': len(memory_samples)
            }
    except Exception as e:
        log(f"Error getting memory stats: {e}")
    
    return None

class ServerManager:
    def __init__(self):
        self.port = SERVER_PORT
        self.container = DOCKER_CONTAINER
        self.manual_stop = False  # Flag for manual stops
        self.last_server_state = True  # Last server state
        self.is_starting = False  # Flag to track server startup process
        self._listening_socket = None  # Socket for listening

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
                # Container is healthy, record successful connection for the last IP that tried
                if hasattr(self, '_last_connection_ip'):
                    connection_tracker.record_attempt(self._last_connection_ip, successful_join=True)
                    delattr(self, '_last_connection_ip')  # Clear it after recording
                
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
                    
                    # Only release port if we're not already listening
                    if not self.is_listening():
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
            
            # Only release port if we're not already listening
            if not self.is_listening():
                self.release_port(force=True)
                
            self.last_server_state = False
            return False

    def release_port(self, force=False):
        """Release the server port"""
        # Skip if we're actively listening (to avoid conflicts)
        if self.is_listening():
            log(f"Skipping port release because we're actively listening on port {self.port}")
            return False
            
        try:
            # Track when we last released the port to avoid duplicate messages
            current_time = time.time()
            if hasattr(self, '_last_port_release') and current_time - self._last_port_release < 5 and not force:
                # Skip if we just released the port recently (within 5 seconds)
                return True
                
            self._last_port_release = current_time
            
            if not message_tracker.port_logged or force:
                log(f"Attempting to release port {self.port}")
                message_tracker.port_logged = True
            
            # Try to find and kill any process using the port
            try:
                # First check what's using the port
                cmd = f"lsof -i :{self.port} -n -P"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.stdout:
                    log(f"Processes using port {self.port}:\n{result.stdout}")
                
                # Now get just the PIDs
                cmd = f"lsof -i :{self.port} -t"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.stdout:
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        if pid.strip():
                            log(f"Killing process {pid} using port {self.port}")
                            try:
                                # First try graceful termination
                                subprocess.run(['kill', pid.strip()], check=False)
                                time.sleep(0.5)
                                
                                # Then check if it's still running
                                if subprocess.run(['ps', '-p', pid.strip()], capture_output=True).returncode == 0:
                                    # If still running, force kill
                                    log(f"Process {pid} still running, force killing")
                                    subprocess.run(['kill', '-9', pid.strip()], check=False)
                            except Exception as e:
                                log(f"Error killing process {pid}: {e}")
                
                # Verify port is now free
                try:
                    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_socket.settimeout(1)
                    test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    test_socket.bind(('0.0.0.0', self.port))
                    log(f"Port {self.port} is now free")
                    test_socket.close()
                except socket.error as e:
                    log(f"Port {self.port} is still in use after kill attempts: {e}")
            except Exception as e:
                log(f"Error finding/killing processes using port {self.port}: {e}")
                
            # Reset listening flags to ensure we don't think we're still listening
            if hasattr(self, '_listening_active'):
                delattr(self, '_listening_active')
                
            return True
                
        except Exception as e:
            if not message_tracker.port_logged or force:
                log(f"Error releasing port: {e}")
            return False

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
            
            # Explicitly check if the port is available
            try:
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(1)
                test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                test_socket.bind(('0.0.0.0', self.port))
                log(f"Port {self.port} is available")
                test_socket.close()
            except socket.error as e:
                log(f"Port {self.port} is still in use: {e}")
                # Try to forcefully release the port
                self.release_port(force=True)
                time.sleep(2)  # Wait for port to be released
                
                # Check again
                try:
                    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_socket.settimeout(1)
                    test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    test_socket.bind(('0.0.0.0', self.port))
                    log(f"Port {self.port} is now available after forced release")
                    test_socket.close()
                except socket.error as e2:
                    log(f"Port {self.port} is still in use after forced release: {e2}")
                    self._starting = False
                    self.is_starting = False
                    return False
            
            # Check container status first
            container_status = self.get_container_status()
            log(f"Current container status: {container_status}")
            
            if container_status == "running":
                log("Container is already running, checking if server is responsive")
                if self.check_server():
                    log("Server is already running and responding")
                    self._starting = False
                    self.is_starting = False
                    return True
                else:
                    log("Container is running but server is not responding, stopping container...")
                    self.stop_server()
                    time.sleep(5)  # Wait for container to fully stop
            
            # Now start the container
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
            
            # Close the listening socket if it exists
            if hasattr(self, '_listening_socket') and self._listening_socket:
                try:
                    self._listening_socket.close()
                    self._listening_socket = None
                    log("Listening socket closed")
                except Exception as e:
                    log(f"Error closing listening socket: {e}")
            
            # Reset listening flags
            if hasattr(self, '_listening_active'):
                delattr(self, '_listening_active')
            
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
            if self.is_listening():
                # If we were listening but server is now running, log that we're stopping
                log("Server is now running, stopping connection listener")
                self.stop_listening()
            return False
        
        # Set up listening socket if we haven't already
        if not self.is_listening():
            # Check if port is already free before trying to release it
            port_is_free = False
            try:
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(1)
                test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                test_socket.bind(('0.0.0.0', self.port))
                test_socket.close()
                port_is_free = True
            except socket.error:
                # Port is in use, need to release it
                self.release_port(force=True)
                time.sleep(1)  # Brief pause to ensure port is released
            
            # Create and set up the socket
            try:
                # Create new socket
                self._listening_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._listening_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._listening_socket.bind(("0.0.0.0", self.port))
                self._listening_socket.listen(1)
                self._listening_socket.settimeout(5)  # 5 second timeout
                
                # Log that we're starting to listen
                log("Listening for connection attempts...")
                
                # Send message only once when we start listening
                from modules.discord import broadcast_discord_message
                if not is_maintenance_period():
                    broadcast_discord_message("💤 Next connection attempt will wake up server!")
                
                self._listening_active = True
            except socket.error as e:
                log(f"Error setting up listening socket: {e}")
                return False
        
        # Now just check for connections without additional logging
        try:
            if not hasattr(self, '_listening_socket') or self._listening_socket is None:
                return False
                
            try:
                conn, addr = self._listening_socket.accept()
                client_ip = get_real_ip(addr)
                log(f"Connection attempt from {addr} (real IP: {client_ip})")

                # Check if this IP is allowed to attempt connection
                if not connection_tracker.record_attempt(client_ip):
                    conn.close()
                    return False

                # Store the IP for tracking successful connections
                self._last_connection_ip = client_ip
                
                conn.close()
                
                # Clean up listening state
                self._listening_socket.close()
                self._listening_socket = None
                self._listening_active = False
                
                log("Connection received, starting server...")
                return True
            except socket.timeout:
                # Silent timeout is expected
                return False
        except Exception as e:
            # Only log errors
            log(f"Error in connection listener: {e}")
            return False

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

    def is_listening(self):
        """Check if we're actively listening for connections"""
        return hasattr(self, '_listening_active') and self._listening_active and hasattr(self, '_listening_socket') and self._listening_socket is not None

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