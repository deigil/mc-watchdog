from modules.logging import log

# Global variable to store the broadcast function
_broadcast_function = None
_pending_messages = []  # Store messages that arrive before broadcast function is set

def set_broadcast_function(func):
    """Set the function to be used for broadcasting messages"""
    global _broadcast_function, _pending_messages
    _broadcast_function = func
    
    # Send any pending messages
    if _pending_messages:
        log(f"Processing {len(_pending_messages)} pending messages")
        for msg, force in _pending_messages:
            broadcast_message(msg, force)
        _pending_messages.clear()

def broadcast_message(message, force=False):
    """Broadcast a message using the registered broadcast function"""
    global _broadcast_function, _pending_messages
    
    if _broadcast_function:
        try:
            _broadcast_function(message, force=force)
        except Exception as e:
            log(f"Error broadcasting message: {e}")
            # Store failed message for retry
            _pending_messages.append((message, force))
    else:
        # If no broadcast function is registered yet, store the message
        log(f"[QUEUED] {message}")
        _pending_messages.append((message, force)) 