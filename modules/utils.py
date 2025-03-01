from datetime import datetime, time

def is_maintenance_day():
    """Check if it's a maintenance day (Tuesday or Thursday)"""
    return datetime.now().weekday() in [1, 3]

def is_maintenance_time():
    """Check if it's maintenance time (Monday or Wednesday 23:59)"""
    now = datetime.now()
    # Check if it's maintenance night (Monday or Wednesday)
    is_maintenance_night = now.weekday() in [0, 2]
    # If it's after 23:29 on maintenance night, consider it maintenance time
    return is_maintenance_night and (now.hour == 23 and now.minute >= 29)

def is_restart_time():
    """Check if it's time to restart after maintenance (Wednesday or Friday 8:00)"""
    now = datetime.now()
    return (now.weekday() in [2, 4] and  # Wednesday or Friday
            now.hour == 8 and now.minute == 0) 