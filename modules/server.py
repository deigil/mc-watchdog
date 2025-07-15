import socket
import subprocess
import time  # This is the time module for sleep()
from modules.logging import log
from config import SERVER_PORT, DOCKER_CONTAINER, MC_LOG
from modules import message_tracker  # Import from modules package
from datetime import datetime  # This is for datetime objects
import json
import re

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
                
            # Check if container is running and strictly healthy
            is_up = "Up" in status
            is_strictly_healthy = "healthy" in status and "unhealthy" not in status

            if is_up and is_strictly_healthy:
                # Only log status changes
                if not hasattr(self, '_last_health_status') or self._last_health_status != True:
                    log(f"Container is strictly healthy: {status}")
                    self._last_health_status = True
                return True
            else:
                # Only log status changes
                if not hasattr(self, '_last_health_status') or self._last_health_status != False:
                    log(f"Container is not strictly healthy: {status}")
                    self._last_health_status = False
                return False
                
        except Exception as e:
            log(f"Error checking container health: {e}")
            return False

    def check_server(self):
        """Check if the Minecraft server is running based on container health"""
        try:
            # Only check container health status
            container_healthy = self.check_container_health()
            
            # Update server state and log only on state changes
            if container_healthy != self.last_server_state:
                if container_healthy:
                    log("Server is now running (container healthy)")
                else:
                    log("Server is now stopped (container unhealthy)")
                self.last_server_state = container_healthy
                
            return container_healthy
                
        except Exception as e:
            log(f"Error checking server: {e}")
            self.last_server_state = False
            return False

    def start_server(self):
        """Start the Minecraft server"""
        try:
            # Prevent duplicate starts
            if hasattr(self, '_starting') and self._starting:
                log("Server start already in progress")
                return False, "⏳ Server is already in the process of starting..."
            
            self._starting = True
            self.is_starting = True
            self.manual_stop = False
            log("Attempting to start server...")
            
            # Check container health first
            if not self.check_container_health():
                # Container doesn't exist or isn't healthy
                container_status = self.get_container_status()
                if container_status == "unknown":
                    log("Container does not exist")
                    return False, "❌ Server container not found. Please contact an administrator."
            
            # Check container status
            container_status = self.get_container_status()
            log(f"Current container status: {container_status}")
            
            # If container is running but server isn't responsive, stop it first
            if container_status == "running":
                if not self.check_server():
                    log("Container is running but server is not responding, stopping container...")
                    self.stop_server()
                    time.sleep(5)  # Brief pause after stop
                else:
                    log("Server is already running and responding")
                    self._starting = False
                    self.is_starting = False
                    return False, "ℹ️ Server is already running!"
            
            # Restart the container (this will stop it if running, then start it)
            try:
                # Using "restart" instead of "start"
                start_cmd = ["docker", "restart", self.container]
                log(f"Executing command: {' '.join(start_cmd)}")
                
                result = subprocess.run(
                    ' '.join(start_cmd),
                    shell=True,
                    capture_output=True, 
                    text=True
                )
                
                # Log the result
                log(f"Command exit code: {result.returncode}")
                if result.stdout.strip():
                    log(f"Command stdout: {result.stdout}")
                if result.stderr.strip():
                    log(f"Command stderr: {result.stderr}")
                
                if result.returncode != 0:
                    raise Exception(f"Docker start command failed with exit code {result.returncode}: {result.stderr}")
                
                log("Starting Minecraft server...")
                return True, "🚀 Server is starting up! Give it like 4 minutes to start..."
                
            except Exception as e:
                log(f"Error starting container: {e}")
                return False, "❌ Failed to start server. Please try again later."
                
        except Exception as e:
            log(f"Error in start_server: {e}")
            return False, "❌ An error occurred while starting the server."
        finally:
            self._starting = False
            self.is_starting = False

    def stop_server(self):
        """Stops the Minecraft server Docker container."""
        log("Attempting to stop server...")
        if not self.check_server():
            log("Server is already stopped.")
            return False, "ℹ️ Server is already stopped."

        try:
            # Execute docker stop command
            command = f"docker stop {self.container}"
            log(f"Executing command: {command}")
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
            log(f"Command exit code: {result.returncode}")
            if result.stdout: log(f"Command stdout: {result.stdout.strip()}")
            if result.stderr: log(f"Command stderr: {result.stderr.strip()}")

            if result.returncode == 0:
                log(f"Container '{self.container}' stopped successfully.")
                # Update internal state if necessary
                self.manual_stop = False 
                return True, f"🛑 Server '{self.container}' stopped successfully."
            else:
                log(f"Failed to stop container '{self.container}'. Exit code: {result.returncode}")
                return False, f"⚠️ Failed to stop server. Check logs for details. Error: {result.stderr.strip()[:100]}"

        except Exception as e:
            log(f"Exception while stopping server: {e}")
            return False, f"❌ An error occurred while trying to stop the server: {e}"

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