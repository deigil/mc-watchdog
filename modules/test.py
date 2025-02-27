import sys
from modules.discord import broadcast_discord_message, send_console_message
from modules.server import server_manager
from modules.sleep import sleep_manager
from modules.maintenance import maintenance_manager
from modules.logging import log

def test_discord():
    """Test Discord messaging functionality"""
    print("\nTesting Discord messaging...")
    try:
        # Test broadcast message
        broadcast_discord_message("🧪 Test broadcast message")
        
        # Test console message
        send_console_message("🧪 Test console message")
        
        print("✅ Discord messages sent successfully")
    except Exception as e:
        print(f"❌ Discord test failed: {e}")

def test_server():
    """Test server management functionality"""
    print("\nTesting server management...")
    try:
        # Check server status
        status = server_manager.check_server()
        print(f"Server status: {'🟢 Running' if status else '🔴 Stopped'}")
        
        # Test stop if running
        if status:
            print("Testing server stop...")
            if server_manager.stop_server():
                print("✅ Server stopped successfully")
            else:
                print("❌ Failed to stop server")
        
        # Test start if stopped
        if not server_manager.check_server():
            print("Testing server start...")
            if server_manager.start_server():
                print("✅ Server started successfully")
            else:
                print("❌ Failed to start server")
    except Exception as e:
        print(f"❌ Server test failed: {e}")

def test_sleep():
    """Test sleep functionality"""
    print("\nTesting sleep trigger...")
    try:
        if sleep_manager.signal_windows_sleep():
            print("✅ Sleep trigger file created successfully")
        else:
            print("❌ Failed to create sleep trigger")
    except Exception as e:
        print(f"❌ Sleep test failed: {e}")

def test_maintenance():
    """Test maintenance checks"""
    print("\nTesting maintenance status...")
    try:
        from modules.maintenance import is_maintenance_time, is_maintenance_day
        
        is_maint_time = is_maintenance_time()
        is_maint_day = is_maintenance_day()
        
        print(f"Maintenance time: {'🟢 Yes' if is_maint_time else '🔴 No'}")
        print(f"Maintenance day: {'🟢 Yes' if is_maint_day else '🔴 No'}")
    except Exception as e:
        print(f"❌ Maintenance test failed: {e}")

def main():
    while True:
        print("\nWatchdog Test Menu:")
        print("1. Test Discord Messages")
        print("2. Test Server Management")
        print("3. Test Sleep Trigger")
        print("4. Test Maintenance Status")
        print("5. Run All Tests")
        print("0. Exit")
        
        choice = input("\nEnter test number (0-5): ")
        
        if choice == "1":
            test_discord()
        elif choice == "2":
            test_server()
        elif choice == "3":
            test_sleep()
        elif choice == "4":
            test_maintenance()
        elif choice == "5":
            test_discord()
            test_server()
            test_sleep()
            test_maintenance()
        elif choice == "0":
            print("\nExiting test suite...")
            sys.exit(0)
        else:
            print("\n❌ Invalid choice, please try again")
        
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest suite interrupted, exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error in test suite: {e}")
        sys.exit(1)
