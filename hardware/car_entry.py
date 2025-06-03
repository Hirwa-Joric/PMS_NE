# IntelligentRobotics/hardware/car_entry.py
import platform
import cv2
import numpy as np # Added for blank frame
from ultralytics import YOLO
import pytesseract
import os
import time
import serial
import serial.tools.list_ports
import sqlite3
from collections import Counter
# import importlib.util # Not used directly in this version
# import sys # Not used directly in this version
from datetime import datetime

# Fix Qt platform plugin issues (keep for now, can test removal later if issues persist)
os.environ["QT_QPA_PLATFORM"] = "xcb"
# Try to force GPU rendering off if causing issues
os.environ["OPENCV_VIDEOIO_DEBUG"] = "1"
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"
os.environ["OPENCV_OPENCL_DEVICE"] = "disabled"

# Import configuration
try:
    from config import DB_PATH, MODEL_PATH, CAPTURE_THRESHOLD, SAVE_DIR, MAX_DISTANCE, MIN_DISTANCE, GATE_BAUD_RATE
    print(f"Resolved DB_PATH from config: {os.path.abspath(DB_PATH)}")
    print(f"Resolved MODEL_PATH from config: {os.path.abspath(MODEL_PATH)}")
except ImportError:
    print("[ERROR] Could not import config.py. Make sure it exists and is correct.")
    # Fallback to default paths if config import fails (not ideal, but for robustness during debug)
    DB_PATH = 'parking_system.db'
    MODEL_PATH = '../model_dev/runs/detect/train/weights/best.pt'
    CAPTURE_THRESHOLD = 3
    SAVE_DIR = 'plates'
    MAX_DISTANCE = 50
    MIN_DISTANCE = 0
    GATE_BAUD_RATE = 9600
    print("[WARNING] Using fallback configuration paths.")


ENTRY_COOLDOWN = 300  # seconds
GATE_OPEN_TIME = 15   # seconds

# Load YOLOv8 model
try:
    model = YOLO(MODEL_PATH)
    print(f"[INFO] YOLO model loaded successfully from {MODEL_PATH}")
except Exception as e:
    print(f"[ERROR] Failed to load YOLO model from {MODEL_PATH}: {e}")
    exit(1)


# Ensure directories exist
os.makedirs(SAVE_DIR, exist_ok=True)

# Use the centralized database check function from config
try:
    from config import check_database
    db_available = check_database()
except ImportError:
    print("[WARNING] config.py or check_database function not found. Database checks might be limited.")
    db_available = os.path.exists(DB_PATH)


# Auto-detect Arduino Serial Port
def detect_arduino_port():
    for port_info in serial.tools.list_ports.comports():
        dev = port_info.device
        print(f"[DEBUG] Checking port: {dev} - {port_info.description}")
        if platform.system() == 'Linux' and ('ttyACM' in dev or 'ttyUSB' in dev):
            if "LUFA CDC" in port_info.description or "Arduino" in port_info.description : # More specific check
                return dev
        if platform.system() == 'Darwin' and ('usbmodem' in dev or 'usbserial' in dev):
            return dev
        if platform.system() == 'Windows' and 'COM' in dev: # May need more specific check for Windows too
             if "Arduino" in port_info.description:
                return dev
    return None

def read_arduino_line_with_timeout(arduino_serial):
    if not arduino_serial or not arduino_serial.is_open:
        return None
    try:
        # pyserial's readline() respects the timeout set during Serial object creation
        line = arduino_serial.readline().decode('utf-8').strip()
        if line:
            return float(line)
        return None # Timeout occurred or empty line
    except (UnicodeDecodeError, ValueError) as e:
        print(f"[ERROR] Error decoding or converting Arduino data: {e}")
        return None
    except serial.SerialException as e:
        print(f"[ERROR] Serial exception during read: {e}")
        return None

def has_unpaid_record(plate):
    if not db_available:
        print("[WARNING] Database unavailable, cannot check for unpaid records.")
        return False # Assume no unpaid record if DB is not available to avoid blocking valid entries
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM parking_log
            WHERE plate_number = ? AND
            exit_time IS NULL AND payment_status = 'UNPAID'
        """, (plate,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        print(f"[ERROR] Database error while checking for unpaid records: {e}")
        return False # Treat DB errors as "no unpaid record found" to prevent blocking

# Initialize Arduino
arduino_port = detect_arduino_port()
arduino = None
if arduino_port:
    print(f"[INFO] Attempting to connect to Arduino on {arduino_port} at baud {GATE_BAUD_RATE}...")
    try:
        arduino = serial.Serial(arduino_port, GATE_BAUD_RATE, timeout=1) # timeout=1 for readline
        time.sleep(2) # Wait for connection to stabilize
        if arduino.is_open:
            print(f"[SUCCESS] Connected to Arduino on {arduino_port}")
        else:
            print(f"[ERROR] Failed to open serial port {arduino_port}, though detected.")
            arduino = None # Explicitly set to None
    except serial.SerialException as e:
        print(f"[ERROR] Could not connect to Arduino on {arduino_port}: {e}")
        arduino = None
else:
    print("[WARNING] Arduino not detected. Gate control and distance sensing will be simulated/disabled.")

# Initialize Webcam
print("[INFO] Initializing camera...")
cap = None
for camera_index_attempt in range(2): # Try camera 0 and 1
    print(f"[INFO] Trying camera index {camera_index_attempt}...")
    temp_cap = cv2.VideoCapture(camera_index_attempt)
    if temp_cap.isOpened():
        ret, test_frame = temp_cap.read()
        if ret and test_frame is not None and test_frame.size > 0:
            print(f"[SUCCESS] Camera {camera_index_attempt} initialized successfully.")
            cap = temp_cap
            break
        else:
            print(f"[WARNING] Camera {camera_index_attempt} opened but couldn't read frames.")
            temp_cap.release()
    else:
        print(f"[WARNING] Failed to open camera at index {camera_index_attempt}.")

if cap is None:
    print("[ERROR] Cannot open any camera. Exiting.")
    exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
# cap.set(cv2.CAP_PROP_FPS, 30) # Setting FPS can be problematic; often best left to auto

# Create windows
cv2.namedWindow('Webcam Feed', cv2.WINDOW_NORMAL)
cv2.namedWindow('Plate', cv2.WINDOW_AUTOSIZE) # Autosize might be better for small plate images
cv2.namedWindow('Processed', cv2.WINDOW_AUTOSIZE)
cv2.resizeWindow('Webcam Feed', 800, 600)
print("[INFO] Camera setup complete.")

# State variables
plate_buffer = []
last_saved_plate = None
last_entry_time = 0
entry_count = 0

# Get entry count from database if available
if db_available:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM parking_log")
        entry_count = cursor.fetchone()[0]
        conn.close()
        print(f"[INFO] Found {entry_count} existing entries in database")
    except Exception as e:
        print(f"[ERROR] Failed to get entry count from database: {e}")

print("[SYSTEM] Ready. Press 'q' to exit.")
frame_count = 0

try:
    while True:
        annotated_frame = None # Ensure it's defined for imshow
        plate_img_display = None
        thresh_display = None

        try:
            ret, frame = cap.read()

            if not ret or frame is None or frame.size == 0:
                print("[WARNING] Frame capture failed. Displaying blank.")
                # Create a blank frame to keep window responsive
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "No Camera Signal", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                annotated_frame = frame.copy()
            else:
                frame_count += 1
                if frame_count % 150 == 0: # approx every 5 seconds if 30fps
                    print(f"[INFO] Camera running: {frame_count} frames processed. Press 'q' to quit.")

                annotated_frame = frame.copy() # Start with a copy of the current frame

                # Temporarily disable Arduino interaction for testing camera responsiveness
                # distance_value = read_arduino_line_with_timeout(arduino)
                # if distance_value is None:
                #     distance = MAX_DISTANCE + 1 # Default if no reading or error
                # else:
                #     distance = distance_value
                #     print(f"[DEBUG] Distance from Arduino: {distance} cm")
                distance = MAX_DISTANCE - 1 # Force processing path for testing

                if MIN_DISTANCE <= distance <= MAX_DISTANCE:
                    results = model(frame)[0]
                    annotated_frame = results.plot() # Update annotated_frame with YOLO plot

                    for box in results.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        plate_img = frame[y1:y2, x1:x2]

                        if plate_img.size == 0:
                            continue
                        
                        plate_img_display = plate_img.copy() # For display

                        gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                        blur = cv2.GaussianBlur(gray, (5,5), 0)
                        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                        thresh_display = thresh.copy() # For display

                        text = pytesseract.image_to_string(
                            thresh,
                            config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                        ).strip().replace(' ', '')

                        if text.startswith('RA') and len(text) >= 7:
                            plate = text[:7]
                            pr, dg, su = plate[:3], plate[3:6], plate[6]
                            if pr.isalpha() and dg.isdigit() and su.isalpha():
                                plate_buffer.append(plate)

                        if len(plate_buffer) >= CAPTURE_THRESHOLD:
                            common_plate = Counter(plate_buffer).most_common(1)[0][0]
                            current_time_secs = time.time()

                            if not has_unpaid_record(common_plate):
                                if common_plate != last_saved_plate or (current_time_secs - last_entry_time) > ENTRY_COOLDOWN:
                                    if db_available:
                                        try:
                                            conn = sqlite3.connect(DB_PATH)
                                            cursor = conn.cursor()
                                            entry_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                            cursor.execute("""
                                                INSERT INTO parking_log (plate_number, entry_time, payment_status)
                                                VALUES (?, ?, ?)
                                            """, (common_plate, entry_timestamp, 'UNPAID'))
                                            entry_count += 1
                                            conn.commit()
                                            conn.close()
                                            print(f"[DB_LOG] Logged plate {common_plate} to database.")
                                        except Exception as e:
                                            print(f"[ERROR] Failed to log entry to database: {e}")
                                    else:
                                        print(f"[WARNING] Database unavailable. Entry for {common_plate} not recorded.")

                                    if arduino and arduino.is_open:
                                        try:
                                            arduino.write(b'1')
                                            print(f"[GATE] Opening gate for plate {common_plate}")
                                            time.sleep(GATE_OPEN_TIME) # This is a blocking call, consider threading for gate timer
                                            arduino.write(b'0')
                                            print(f"[GATE] Closing gate after {GATE_OPEN_TIME} seconds")
                                        except serial.SerialException as se:
                                            print(f"[ERROR] Arduino serial error during gate operation: {se}")
                                    else:
                                        print(f"[SIMULATE_GATE] Gate would open for {common_plate}")


                                    last_saved_plate = common_plate
                                    last_entry_time = current_time_secs
                                else:
                                    print(f"[SKIPPED] Cooldown or duplicate: {common_plate}")
                            else:
                                print(f"[SKIPPED] Unpaid record exists for {common_plate}")
                            plate_buffer.clear()
            
            # Display webcam feed
            if annotated_frame is not None:
                cv2.imshow('Webcam Feed', annotated_frame)
            
            # Display plate and processed images if they exist
            if plate_img_display is not None and plate_img_display.size > 0 :
                 cv2.imshow('Plate', plate_img_display)
            if thresh_display is not None and thresh_display.size > 0:
                cv2.imshow('Processed', thresh_display)

        except Exception as e:
            print(f"[ERROR] Error in main loop processing: {e}")
            # Display a generic error on the feed if possible
            if 'annotated_frame' in locals() and annotated_frame is not None:
                 cv2.putText(annotated_frame, "Processing Error", (50,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255),2)
                 cv2.imshow('Webcam Feed', annotated_frame)
            elif 'frame' in locals() and frame is not None:
                 cv2.putText(frame, "Processing Error", (50,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255),2)
                 cv2.imshow('Webcam Feed', frame)


        # Crucial: Ensure waitKey is called for GUI events
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("[INFO] 'q' pressed, exiting...")
            break

finally:
    print("[INFO] Cleaning up...")
    if cap is not None and cap.isOpened():
        cap.release()
        print("[INFO] Camera released.")
    if arduino is not None and arduino.is_open:
        try:
            arduino.close()
            print("[INFO] Arduino serial port closed.")
        except Exception as e:
            print(f"[ERROR] Exception while closing Arduino: {e}")
    cv2.destroyAllWindows()
    print("[INFO] OpenCV windows destroyed.")
    print("[INFO] Script finished.")

# This part is for when car_entry.py is run directly or as a module
# The main logic is already at the global scope.
def car_entry_main(db_path_arg=None, camera_index_arg=0, debug_arg=False):
    """
    Main entry point when run as a module from parking_system.py
    Note: This function primarily sets global-like variables if provided,
    but the script's main execution logic is already at the top level.
    """
    global DB_PATH, CAMERA_INDEX # These are already effectively global
    if db_path_arg:
        DB_PATH = db_path_arg
    # camera_index is handled during cap initialization
    # debug_arg can be used to set a global debug flag if needed
    
    # Since the main loop is at global scope, this function doesn't need to call it.
    # If you were to encapsulate the while loop in a function, you'd call it here.
    print(f"[INFO] car_entry_main called with DB: {DB_PATH}, Cam: {camera_index_arg}")
    # To run the logic when called as a module, you might need to restructure
    # the main while loop into a function and call it here.
    # For now, it will execute when the script is imported if not guarded by if __name__ == "__main__":

if __name__ == "__main__":
    # This block allows the script to be run directly.
    # The main while loop will execute.
    pass