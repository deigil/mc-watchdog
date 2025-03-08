#!/usr/bin/env python3
"""
Trigger Sleep Script

This script creates a sleep trigger file that will put Windows to sleep.
Based on the successful test_sleep_trigger.py script.

Usage:
    python triggersleep.py

This will create a sleep trigger file in the Windows directory that will
cause the computer to go to sleep.
"""

import os
import sys
import time
from datetime import datetime

def log(message):
    """Simple logging function"""
    timestamp = datetime.now()
    print(f"[{timestamp}] {message}")
    
    # Also write to a log file
    try:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "triggersleep.log"), "a") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"Error writing to log file: {e}")

# Get paths from config
SLEEP_DIR = os.getenv('SLEEP_TRIGGER_DIR')
SLEEP_FILE = os.getenv('SLEEP_TRIGGER_FILE')

def create_sleep_trigger():
    """Create a sleep trigger file in the Windows directory"""
    try:
        log(f"Attempting to create sleep trigger in directory: {SLEEP_DIR}")
        log(f"Full trigger file path: {SLEEP_FILE}")
        
        # Print environment info
        log(f"Current working directory: {os.getcwd()}")
        log(f"Python version: {sys.version}")
        
        # Test Windows filesystem access
        if not os.path.exists("/mnt/c"):
            log("CRITICAL ERROR - Cannot access Windows filesystem (/mnt/c)")
            return False
            
        # Check if directory exists
        if os.path.exists(SLEEP_DIR):
            log(f"Directory exists: {SLEEP_DIR}")
            # List contents
            try:
                contents = os.listdir(SLEEP_DIR)
                log(f"Directory contents: {contents}")
            except Exception as e:
                log(f"Error listing directory: {e}")
        else:
            log(f"Directory does not exist: {SLEEP_DIR}")
            try:
                os.makedirs(SLEEP_DIR, exist_ok=True)
                log(f"Created directory: {SLEEP_DIR}")
            except Exception as e:
                log(f"Error creating directory: {e}")
                return False
        
        # Create a test file first
        test_file = f"{SLEEP_DIR}/test_file_123"
        try:
            with open(test_file, 'w') as f:
                f.write("test content")
            log(f"Successfully created test file: {test_file}")
            
            # Verify test file
            if os.path.exists(test_file):
                with open(test_file, 'r') as f:
                    content = f.read()
                log(f"Test file verified with content: {content}")
                os.remove(test_file)
                log(f"Test file removed")
            else:
                log(f"Test file not found after creation!")
        except Exception as e:
            log(f"Error with test file: {e}")
        
        # Write the actual trigger file
        timestamp = datetime.now()
        log(f"Writing timestamp to trigger file: {timestamp}")
        
        try:
            with open(SLEEP_FILE, 'w') as f:
                f.write(str(timestamp))
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            log(f"Wrote to trigger file")
            
            # Set file permissions to match the test script (0o777)
            try:
                os.chmod(SLEEP_FILE, 0o777)
                log(f"Set file permissions to 0o777")
            except Exception as e:
                log(f"Warning: Could not set file permissions: {e}")
        except Exception as e:
            log(f"Error writing trigger file: {e}")
            return False
        
        # Verify file was created
        if os.path.exists(SLEEP_FILE):
            # Read back the file to verify content
            with open(SLEEP_FILE, 'r') as f:
                content = f.read().strip()
            log(f"Verified trigger file creation. Content: {content}")
            
            # List all files in the directory again
            log(f"Files in trigger directory after creation: {os.listdir(SLEEP_DIR)}")
            
            # Get file permissions
            file_stat = os.stat(SLEEP_FILE)
            log(f"File permissions: {oct(file_stat.st_mode)}")
            
            log("Sleep trigger file created successfully. Your computer should go to sleep shortly.")
            return True
        else:
            log("Failed to verify sleep trigger file creation")
            return False
            
    except Exception as e:
        log(f"Error creating sleep trigger: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    log("=== STARTING SLEEP TRIGGER ===")
    
    # Create the sleep trigger file
    result = create_sleep_trigger()
    log(f"Sleep trigger creation {'SUCCEEDED' if result else 'FAILED'}")
    
    if result:
        log("Your computer should go to sleep shortly...")
    else:
        log("Failed to create sleep trigger. Check the log for details.")
    
    log("=== SLEEP TRIGGER COMPLETE ===") 