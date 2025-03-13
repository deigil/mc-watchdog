from datetime import datetime
import time as time_module  # Rename the time module import to avoid collision

class MessageTracker:
    def __init__(self):
        self.last_message = None
        self.port_logged = False

message_tracker = MessageTracker()

def is_maintenance_period():
    """
    Check if current time is during the maintenance period
    Maintenance period: Tuesday 11:59 PM to Thursday 8:00 AM
    """
    now = datetime.now()
    current_day = now.weekday()  # 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday
    current_time = now.time()
    
    # Tuesday after 11:59 PM
    if current_day == 1 and current_time.hour == 23 and current_time.minute >= 59:
        return True
    
    # All of Wednesday
    if current_day == 2:
        return True
    
    # Thursday before 8:00 AM
    if current_day == 3 and (current_time.hour < 8):
        return True
        
    return False
