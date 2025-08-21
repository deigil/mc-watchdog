import socket
import subprocess
import time  # This is the time module for sleep()
from modules.logging import log
from config import SERVER_PORT, DOCKER_CONTAINER, MC_LOG
from modules import message_tracker  # Import from modules package
from datetime import datetime  # This is for datetime objects
import json
import re
import os
import requests

class ServerManager:
    def __init__(self):
        self.port = SERVER_PORT
        self.container = DOCKER_CONTAINER
        self.manual_stop = False  # Flag for manual stops
        self.last_server_state = True  # Last server state
        self.is_starting = False  # Flag to track server startup process
        self.is_updating = False  # Flag to track server update process

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

    def get_modpack_version(self, data_dir):
        """Read the modpack version from GitHub raw pack.toml"""
        import re
        import requests
        
        try:
            # Use GitHub raw URL to get the latest pack.toml
            github_raw_url = "https://raw.githubusercontent.com/iwolfking/Wolds-Vaults/master/pack.toml"
            
            response = requests.get(github_raw_url, timeout=10)
            if response.status_code == 200:
                content = response.text
                match = re.search(r'version\s*=\s*"([^"]+)"', content)
                if match:
                    version = match.group(1)
                    log(f"Read modpack version from GitHub: {version}")
                    return version
            
            # Fallback to local pack.toml if GitHub fails
            wolds_repo_path = os.path.join(os.path.dirname(data_dir), "Wolds-Vaults")
            pack_toml_path = os.path.join(wolds_repo_path, "pack.toml")
            if os.path.exists(pack_toml_path):
                with open(pack_toml_path, 'r') as f:
                    content = f.read()
                    match = re.search(r'version\s*=\s*"([^"]+)"', content)
                    if match:
                        version = match.group(1)
                        log(f"Fallback: Read modpack version from local pack.toml: {version}")
                        return version
            
            return "Unknown"
        except Exception as e:
            log(f"Warning: Could not read modpack version: {e}")
            return "Unknown"

    def update_server(self):
        """Complete server update process with progress messages"""
        import requests
        import zipfile
        import shutil
        import os
        import subprocess
        
        # Prevent duplicate updates
        if self.is_updating:
            log("Update already in progress")
            return False, ["⏳ Server update is already in progress..."]
        
        self.is_updating = True
        
        try:
            # Configuration matching update.py
            WOLDS_ROOT = "/workspace"  # Container path
            UPDATE_DIR = os.path.join(WOLDS_ROOT, "update")
            DATA_DIR = os.path.join(WOLDS_ROOT, "data")
            ZIP_FILE_PATH = os.path.join(WOLDS_ROOT, "latest-wolds-server-pack.zip")
            DOWNLOAD_URL = "https://cloud.iwolfking.xyz/s/eKAXACJgx7ELqwg/download/latest-wolds-server-pack.zip"
            
            # Config exclusions from update.py
            CONFIG_EXCLUSIONS = [
                "server-icon.png",
                "config/luckperms/luckperms-h2.mv.db",
                "config/minimotd/main.conf",
                "config/the_vault/player_titles.json",
                "config/lightmansdiscord_messages.txt",
            ]
            
            messages = []
            
            # Step 1: Ensure data directory exists
            if not os.path.exists(DATA_DIR):
                error_msg = f"Data directory '{DATA_DIR}' does not exist. Cannot update."
                log(f"ERROR: {error_msg}")
                messages.append(f"❌ {error_msg}")
                return False, messages
            
            # Log paths for debugging
            log(f"Update paths - WOLDS_ROOT: {WOLDS_ROOT}, DATA_DIR: {DATA_DIR}, UPDATE_DIR: {UPDATE_DIR}")
            
            # Step 2: Cleanup old files first (safe operation)
            log("Starting update: Cleaning up old files...")
            messages.append("🧹 Cleaning up old update files...")
            
            # Remove old zip file safely
            try:
                if os.path.exists(ZIP_FILE_PATH):
                    os.remove(ZIP_FILE_PATH)
                    log(f"Removed old zip file: {ZIP_FILE_PATH}")
            except Exception as e:
                log(f"Warning: Could not remove old zip file: {e}")
                
            # Remove old update directory safely
            try:
                if os.path.exists(UPDATE_DIR):
                    shutil.rmtree(UPDATE_DIR)
                    log(f"Removed old update directory: {UPDATE_DIR}")
            except Exception as e:
                log(f"Warning: Could not remove old update directory: {e}")
                
            # Create fresh update directory
            try:
                os.makedirs(UPDATE_DIR, exist_ok=True)
                log(f"Created fresh update directory: {UPDATE_DIR}")
            except Exception as e:
                error_msg = f"Failed to create update directory: {e}"
                log(f"ERROR: {error_msg}")
                messages.append(f"❌ {error_msg}")
                return False, messages
            
            # Step 3: Download update (if this fails, data dir is untouched)
            log("Downloading server update...")
            messages.append("⬇️ Downloading server update...")
            
            response = requests.get(DOWNLOAD_URL, stream=True, timeout=120)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            bytes_downloaded = 0
            
            with open(ZIP_FILE_PATH, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
            
            log(f"Download completed: {bytes_downloaded / (1024*1024):.2f} MB")
            messages.append("✅ Download completed successfully!")
            
            # Step 3: Extract the update
            log("Extracting update files...")
            messages.append("📦 Extracting update files...")
            
            with zipfile.ZipFile(ZIP_FILE_PATH, 'r') as zip_ref:
                zip_ref.extractall(UPDATE_DIR)
            
            log("Extraction completed")
            
            # Step 4: Stop server (only after successful download/extract)
            was_running = self.check_server()
            if was_running:
                log("Stopping server for update...")
                messages.append("🛑 Stopping server for update...")
                
                success, stop_msg = self.stop_server()
                if not success:
                    raise Exception(f"Failed to stop server: {stop_msg}")
                    
                messages.append("✅ Server stopped successfully!")
            else:
                messages.append("ℹ️ Server was already stopped.")
            
            # Step 6: Delete mods folder for clean installation
            mods_dir = os.path.join(DATA_DIR, "mods")
            try:
                if os.path.exists(mods_dir):
                    log("Removing old mods folder...")
                    messages.append("🗑️ Removing old mods for clean installation...")
                    shutil.rmtree(mods_dir)
                    log("Old mods folder removed")
                else:
                    log("No existing mods folder found, proceeding...")
            except Exception as e:
                log(f"Warning: Could not remove mods folder: {e}")
                messages.append("⚠️ Could not remove old mods folder, but continuing...")
            
            # Step 7: Run rsync with same config as update.py
            log("Synchronizing update files...")
            messages.append("🔄 Synchronizing server files...")
            
            # Build exclusion arguments
            exclusion_args = []
            for config_file in CONFIG_EXCLUSIONS:
                exclusion_args.extend(['--exclude', config_file])
            
            # Build rsync command
            rsync_cmd = [
                'rsync', '-avu'
            ] + exclusion_args + [
                f'{UPDATE_DIR}/',
                f'{DATA_DIR}/'
            ]
            
            result = subprocess.run(rsync_cmd, capture_output=True, text=True, check=True)
            log("Rsync completed successfully")
            if result.stdout:
                log(f"Rsync output: {result.stdout[:200]}...")  # Log first 200 chars
            
            messages.append("✅ File synchronization completed!")
            
            # Step 8: Cleanup
            log("Cleaning up temporary files...")
            messages.append("🧹 Cleaning up temporary files...")
            
            # Remove zip file safely
            try:
                if os.path.exists(ZIP_FILE_PATH):
                    os.remove(ZIP_FILE_PATH)
                    log(f"Removed zip file: {ZIP_FILE_PATH}")
            except Exception as e:
                log(f"Warning: Could not remove zip file: {e}")
                
            # Remove update directory safely
            try:
                if os.path.exists(UPDATE_DIR):
                    shutil.rmtree(UPDATE_DIR)
                    log(f"Removed update directory: {UPDATE_DIR}")
            except Exception as e:
                log(f"Warning: Could not remove update directory: {e}")
                
            log("Cleanup completed")
            messages.append("✅ Cleanup completed!")
            
            # Step 9: Restart server if it was running
            if was_running:
                log("Restarting server...")
                messages.append("🚀 Restarting server...")
                
                success, start_msg = self.start_server()
                if success:
                    messages.append("✅ Server restarted successfully!")
                else:
                    messages.append(f"⚠️ Server restart failed: {start_msg}")
                    log(f"Server restart failed: {start_msg}")
                    return False, messages
            else:
                messages.append("ℹ️ Server was not running before update, leaving stopped.")
            
            # Get the updated version
            updated_version = self.get_modpack_version(DATA_DIR)
            log(f"Server update completed successfully! Updated to version: {updated_version}")
            
            # Add version info to final success message
            if updated_version != "Unknown":
                messages.append(f"🎉 Server updated to version {updated_version} successfully!")
            else:
                messages.append("🎉 Server update completed successfully!")
            
            return True, messages
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Download failed: {str(e)[:100]}"
            log(f"Update failed during download: {e}")
            messages.append(f"❌ {error_msg}")
            
            # If server was running, try to restart it
            if 'was_running' in locals() and was_running:
                log("Attempting to restart server after download failure...")
                success, start_msg = self.start_server()
                if success:
                    messages.append("🚀 Server restarted after failed update.")
                else:
                    messages.append(f"⚠️ Failed to restart server: {start_msg}")
            
            return False, messages
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Rsync failed: {str(e)[:100]}"
            log(f"Update failed during rsync: {e}")
            messages.append(f"❌ {error_msg}")
            
            # Try to restart server even after rsync failure
            if 'was_running' in locals() and was_running:
                log("Attempting to restart server after rsync failure...")
                success, start_msg = self.start_server()
                if success:
                    messages.append("🚀 Server restarted after failed update.")
                else:
                    messages.append(f"⚠️ Failed to restart server: {start_msg}")
            
            return False, messages
            
        except Exception as e:
            error_msg = f"Update failed: {str(e)[:100]}"
            log(f"Update failed with exception: {e}")
            messages.append(f"❌ {error_msg}")
            
            # Try to restart server if it was stopped during update
            if 'was_running' in locals() and was_running:
                log("Attempting to restart server after update failure...")
                success, start_msg = self.start_server()
                if success:
                    messages.append("🚀 Server restarted after failed update.")
                else:
                    messages.append(f"⚠️ Failed to restart server: {start_msg}")
            
            return False, messages
        
        finally:
            self.is_updating = False

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

def update_server():
    return server_manager.update_server()