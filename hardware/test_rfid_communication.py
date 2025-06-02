#!/usr/bin/env python3
import serial
import time
import sys

# Test basic communication with the Arduino RFID writer
def test_arduino_communication(port, timeout=30):
    try:
        # Open serial connection
        print(f"Opening serial port {port} at 9600 baud...")
        ser = serial.Serial(port, 9600, timeout=1)
        print(f"✅ Connected to {port}")
        
        # Give Arduino time to reset after connection
        time.sleep(2)
        
        # Read any startup messages
        if ser.in_waiting:
            initial = ser.read(ser.in_waiting).decode(errors='ignore')
            print("Initial Arduino output:")
            print(initial)
        else:
            print("No initial output from Arduino")
        
        # Simple echo test - wait for input and send it to Arduino
        print("\n=== Interactive Arduino Serial Monitor ===")
        print("Type messages to send to Arduino or Ctrl+C to exit")
        print("All input will be sent with a '#' character appended")
        
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            # Check for Arduino output
            if ser.in_waiting:
                output = ser.read(ser.in_waiting).decode(errors='ignore')
                print(f"[ARDUINO] {output}", end='')
                start_time = time.time()  # Reset timeout when we get output
            
            # Check for user input
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                line = input("")
                if line:
                    print(f"[SENT] {line}#")
                    ser.write(f"{line}#".encode())
                    start_time = time.time()  # Reset timeout on user input
            
            time.sleep(0.1)
        
        print("\nTimeout reached. Closing connection.")
        ser.close()
        
    except serial.SerialException as e:
        print(f"❌ Serial error: {e}")
    except KeyboardInterrupt:
        print("\nTest terminated by user")
        if 'ser' in locals():
            ser.close()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    import argparse
    import select
    
    parser = argparse.ArgumentParser(description="Test Arduino RFID communication")
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serial port to use")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds (default: 60)")
    args = parser.parse_args()
    
    test_arduino_communication(args.port, args.timeout)
