import serial
import time

def read_float(serial_port):
    """
    Reads a line from the given serial port and returns it as a float.
    Returns None if the line is empty or not a valid float.
    """
    if serial_port.in_waiting > 0:
        try:
            line = serial_port.readline().decode('utf-8').strip()
            value = float(line)
            return value
        except ValueError:
            # Invalid float received
            return None
    return None

# Set up the serial connection
ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
time.sleep(1)  # Give the connection time to initialize

print("Reading float values from Arduino. Press Ctrl+C to stop.\n")

try:
    while True:
        value = read_float(ser)
        if value is not None:
            print(f"Received: {value}")
except KeyboardInterrupt:
    print("\nStopped by user.")
finally:
    ser.close()
