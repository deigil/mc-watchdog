from datetime import datetime, timedelta
from modules.logging import log
from modules.utils import broadcast_message

# Read from docker-compose.yml
AUTOSTOP_TIMEOUT = 900  # 15 minutes (from AUTOSTOP_TIMEOUT_EST in docker-compose.yml)

class ConnectionTracker:
    def __init__(self):
        self.connection_history = {}  # Store connection history by IP
        self.cooldown_ips = {}  # Store IPs in cooldown: {ip: (level, start_time)}
        self.base_cooldown = timedelta(minutes=30)  # 30 minute base cooldown
        self.attempt_window = timedelta(minutes=15)  # Window to track attempts
        self.max_failed_attempts = 2  # Max failed attempts before cooldown
        self.successful_connections = {}  # Track successful connection times: {ip: start_time}

    def record_attempt(self, ip, successful_join=False):
        """Record a connection attempt from an IP"""
        current_time = datetime.now()
        
        # Handle successful connections
        if successful_join:
            self.successful_connections[ip] = current_time
            # Don't reset cooldown immediately - we'll wait to see if they stay connected
            return True

        # Check if IP is in cooldown
        if self.is_in_cooldown(ip):
            level, start_time = self.cooldown_ips[ip]
            cooldown_duration = self.base_cooldown * (2 ** (level - 1))
            cooldown_end = start_time + cooldown_duration
            remaining = (cooldown_end - current_time).total_seconds() / 60
            log(f"Connection attempt from {ip} rejected - in cooldown level {level} for {remaining:.1f} more minutes")
            return False

        # Initialize history for new IPs
        if ip not in self.connection_history:
            self.connection_history[ip] = []

        # Add current attempt and clean old attempts
        self.connection_history[ip].append(current_time)
        self._clean_old_attempts(ip)

        # Check if should enter cooldown
        if len(self.connection_history[ip]) >= self.max_failed_attempts:
            # Determine cooldown level
            new_level = 1
            if ip in self.cooldown_ips:
                # Get the last level and increment it
                last_level = self.cooldown_ips[ip][0]
                new_level = last_level + 1

            self.cooldown_ips[ip] = (new_level, current_time)
            cooldown_duration = self.base_cooldown * (2 ** (new_level - 1))
            minutes = cooldown_duration.total_seconds() / 60
            
            log(f"IP {ip} placed in cooldown level {new_level} ({minutes:.0f} minutes) for excessive failed connection attempts")
            broadcast_message(f"⚠️ IP {ip} has been placed in cooldown for {minutes:.0f} minutes due to excessive failed connection attempts")
            return False

        return True

    def is_in_cooldown(self, ip):
        """Check if an IP is currently in cooldown"""
        if ip in self.cooldown_ips:
            current_time = datetime.now()
            level, start_time = self.cooldown_ips[ip]
            cooldown_duration = self.base_cooldown * (2 ** (level - 1))
            cooldown_end = start_time + cooldown_duration
            
            # Check if they had a successful connection that lasted longer than autostop
            if ip in self.successful_connections:
                success_time = self.successful_connections[ip]
                # If they connected successfully and enough time has passed
                if current_time - success_time > timedelta(seconds=AUTOSTOP_TIMEOUT):
                    # Reset everything for this IP
                    del self.cooldown_ips[ip]
                    del self.successful_connections[ip]
                    if ip in self.connection_history:
                        self.connection_history[ip] = []
                    log(f"IP {ip} cooldown reset due to successful connection")
                    return False
            
            if current_time < cooldown_end:
                return True
            else:
                # Cooldown expired but don't reset level
                del self.cooldown_ips[ip]
                if ip in self.connection_history:
                    self.connection_history[ip] = []
        return False

    def _clean_old_attempts(self, ip):
        """Remove attempts outside the tracking window"""
        if ip in self.connection_history:
            current_time = datetime.now()
            self.connection_history[ip] = [
                attempt for attempt in self.connection_history[ip]
                if current_time - attempt <= self.attempt_window
            ]

# Global instance
connection_tracker = ConnectionTracker() 