# IntelligentRobotics/hardware/car_exit.py
import platform
import cv2
import numpy as np
from ultralytics import YOLO
import pytesseract
import os
import time
import serial
import serial.tools.list_ports
import sqlite3
from collections import Counter
from datetime import datetime

# Fix Qt platform plugin issues
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "1"
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"
os.environ["OPENCV_OPENCL_DEVICE"] = "disabled"

# Import configuration
try:
    from config import DB_PATH, MODEL_PATH, CAPTURE_THRESHOLD, MAX_DISTANCE, MIN_DISTANCE, GATE_BAUD_RATE, CAMERA_INDEX
    print(f"[INFO] Config loaded: DB_PATH={os.path.abspath(DB_PATH)}, MODEL_PATH={os.path.abspath(MODEL_PATH)}")
except ImportError:
    print("[ERROR] Could not import config.py. Using fallback configuration.")
    DB_PATH = 'parking_system.db'
    MODEL_PATH = '../model_dev/runs/detect/train/weights/best.pt'
    CAPTURE_THRESHOLD = 3
    MAX_DISTANCE = 50
    MIN_DISTANCE = 0
    GATE_BAUD_RATE = 9600
    CAMERA_INDEX = 0

# Constants
EXIT_COOLDOWN = 300  # seconds
GATE_OPEN_TIME = 15  # seconds
OCR_CONFIG = '--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
ALERT_COOLDOWN = 60  # seconds to wait before alerting again for the same plate

# Initialize YOLO model
try:
    model = YOLO(MODEL_PATH)
    print(f"[INFO] YOLO model loaded successfully from {MODEL_PATH}")
except Exception as e:
    print(f"[ERROR] Failed to load YOLO model from {MODEL_PATH}: {e}")
    exit(1)

# Check database
try:
    from config import check_database
    db_available = check_database()
except ImportError:
    print("[WARNING] config.py or check_database function not found.")
    db_available = os.path.exists(DB_PATH)

# Auto-detect Arduino port
def detect_arduino_port():
    for port_info in serial.tools.list_ports.comports():
        dev = port_info.device
        print(f"[DEBUG] Checking port: {dev} - {port_info.description}")
        if platform.system() == 'Linux' and ('ttyACM' in dev or 'ttyUSB' in dev):
            if "LUFA CDC" in port_info.description or "Arduino" in port_info.description:
                return dev
        if platform.system() == 'Darwin' and ('usbmodem' in dev or 'usbserial' in dev):
            return dev
        if platform.system() == 'Windows' and 'COM' in dev:
            if "Arduino" in port_info.description:
                return dev
    return None

# Read Arduino data
def read_arduino_line_with_timeout(arduino_serial):
    if not arduino_serial or not arduino_serial.is_open:
        return None
    try:
        line = arduino_serial.readline().decode('utf-8').strip()
        if line:
            return float(line)
        return None
    except (UnicodeDecodeError, ValueError) as e:
        print(f"[ERROR] Error decoding or converting Arduino data: {e}")
        return None
    except serial.SerialException as e:
        print(f"[ERROR] Serial exception during read: {e}")
        return None

# Database functions
def check_payment_status(plate):
    if not db_available:
        print("[WARNING] Database unavailable, assuming payment required.")
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT payment_status, entry_time FROM parking_log
            WHERE plate_number = ? AND exit_time IS NULL AND payment_status = 'PAID'
            ORDER BY entry_time DESC LIMIT 1
        """, (plate,))
        result = cursor.fetchone()
        
        if result:
            entry_time = datetime.strptime(result[1], '%Y-%m-%d %H:%M:%S')
            print(f"[ACCESS_GRANTED] Paid entry found for {plate}")
            conn.close()
            return True
            
        conn.close()
        print(f"[ACCESS_DENIED] No recent paid entry for {plate}")
        return False
    except Exception as e:
        print(f"[ERROR] Database error while checking payment status: {e}")
        return False

def log_exit(plate):
    if not db_available:
        print("[WARNING] Database unavailable, cannot log exit.")
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        exit_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            UPDATE parking_log
            SET exit_time = ?
            WHERE plate_number = ? AND exit_time IS NULL
        """, (exit_timestamp, plate))
        conn.commit()
        conn.close()
        print(f"[DB_LOG] Logged exit for plate {plate}")
    except Exception as e:
        print(f"[ERROR] Failed to log exit to database: {e}")

# Initialize Arduino
arduino_port = detect_arduino_port()
arduino = None
if arduino_port:
    print(f"[INFO] Connecting to Arduino on {arduino_port} at baud {GATE_BAUD_RATE}...")
    try:
        arduino = serial.Serial(arduino_port, GATE_BAUD_RATE, timeout=1)
        time.sleep(2)
        if arduino.is_open:
            print(f"[SUCCESS] Connected to Arduino on {arduino_port}")
        else:
            print(f"[ERROR] Failed to open serial port {arduino_port}")
            arduino = None
    except serial.SerialException as e:
        print(f"[ERROR] Could not connect to Arduino on {arduino_port}: {e}")
        arduino = None
else:
    print("[WARNING] Arduino not detected. Gate control will be simulated.")

# Initialize Webcam
print("[INFO] Initializing camera...")
cap = None
for camera_index_attempt in [CAMERA_INDEX, CAMERA_INDEX + 1]:
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

# Create windows
cv2.namedWindow('Exit Webcam Feed', cv2.WINDOW_NORMAL)
cv2.namedWindow('Plate', cv2.WINDOW_AUTOSIZE)
cv2.namedWindow('Processed', cv2.WINDOW_AUTOSIZE)
cv2.resizeWindow('Exit Webcam Feed', 800, 600)
print("[INFO] Camera setup complete.")

# State variables
plate_buffer = []
last_processed_plate = None
last_exit_time = 0
last_alert_time = 0
frame_count = 0
current_gate_status = "CLOSED"
gate_action_finish_time = 0

print("[SYSTEM] Ready. Press 'q' to exit.")

try:
    while True:
        ret, frame = cap.read()
        annotated_frame = None
        plate_img_display = None
        thresh_display = None

        current_time = time.time()

        if not ret or frame is None or frame.size == 0:
            print("[WARNING] Frame capture failed. Displaying blank.")
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "No Camera Signal", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            annotated_frame = frame.copy()
        else:
            frame_count += 1
            if frame_count % 150 == 0:
                print(f"[INFO] Camera running: {frame_count} frames processed. Press 'q' to quit.")

            annotated_frame = frame.copy()

            # Auto-close gate if timer expired
            if current_gate_status == "OPEN" and current_time >= gate_action_finish_time:
                if arduino and arduino.is_open:
                    try:
                        arduino.write(b'0')
                        print("[GATE] Closing gate after timeout")
                    except serial.SerialException as se:
                        print(f"[ERROR] Arduino serial error during gate close: {se}")
                current_gate_status = "CLOSED"

            # Read distance from Arduino
            distance = MAX_DISTANCE + 1
            if arduino and arduino.is_open:
                distance_value = read_arduino_line_with_timeout(arduino)
                if distance_value is not None:
                    distance = distance_value
                    print(f"[DEBUG] Distance from Arduino: {distance} cm")
                else:
                    print(f"[DEBUG] No valid distance data received from Arduino")

            if MIN_DISTANCE <= distance <= MAX_DISTANCE and current_gate_status == "CLOSED":
                print(f"[DEBUG] Car detected within range ({distance} cm), attempting plate detection")
                results = model(frame, conf=0.5)[0]
                annotated_frame = results.plot()
                print(f"[DEBUG] YOLO detection results: {len(results.boxes)} potential plates found")

                for box in results.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    plate_img = frame[y1:y2, x1:x2]

                    if plate_img.size == 0:
                        print("[DEBUG] Empty plate image, skipping")
                        continue

                    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                    blur = cv2.GaussianBlur(gray, (5, 5), 0)
                    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

                    text = pytesseract.image_to_string(thresh, config=OCR_CONFIG).strip().replace(" ", "")
                    print(f"[DEBUG] OCR result: '{text}'")
                    if text and len(text) >= 7:
                        plate = text[:7]
                        pr, dg, su = plate[:3], plate[3:6], plate[6]
                        if pr.isalpha() and dg.isdigit() and su.isalpha():
                            print(f"[DEBUG] Valid plate format detected: {plate}")
                            plate_buffer.append(plate)
                        else:
                            print(f"[DEBUG] Invalid plate format for '{plate}'")
                    else:
                        print(f"[DEBUG] OCR text too short or empty: '{text}'")

                    if len(plate_buffer) >= CAPTURE_THRESHOLD:
                        common_plate = Counter(plate_buffer).most_common(1)[0][0]
                        plate_buffer.clear()

                        if common_plate != last_processed_plate or (current_time - last_exit_time) > EXIT_COOLDOWN:
                            print(f"[PLATE_CONFIRMED] {common_plate}")
                            if check_payment_status(common_plate):
                                if arduino and arduino.is_open:
                                    try:
                                        arduino.write(b'1')  # Open gate
                                        print(f"[GATE] Opening gate for plate {common_plate}")
                                        current_gate_status = "OPEN"
                                        gate_action_finish_time = current_time + GATE_OPEN_TIME
                                        # Log the exit in the database
                                        log_exit(common_plate)
                                        print(f"[DB_UPDATE] Recorded exit for plate {common_plate}")
                                    except serial.SerialException as se:
                                        print(f"[ERROR] Arduino serial error during gate open: {se}")
                                else:
                                    print(f"[SIMULATE_GATE] Gate would open for {common_plate}")
                                    # Log the exit in the database even in simulation mode
                                    log_exit(common_plate)
                                    print(f"[DB_UPDATE] Recorded exit for plate {common_plate}")
                                last_processed_plate = common_plate
                                last_exit_time = current_time
                            else:
                                print(f"[PAYMENT_REQUIRED] Plate {common_plate} has unpaid status.")
                                if (common_plate != last_processed_plate or (current_time - last_alert_time) > ALERT_COOLDOWN):
                                    if arduino and arduino.is_open:
                                        try:
                                            arduino.write(b'2')  # Trigger alert/buzzer
                                            print(f"[ALERT] Triggering alarm for unpaid plate {common_plate}")
                                        except serial.SerialException as se:
                                            print(f"[ERROR] Arduino serial error during alert: {se}")
                                    last_alert_time = current_time
                                    last_processed_plate = common_plate
                                else:
                                    print(f"[ALERT_COOLDOWN] Skipping alert for {common_plate}, last alert was {(current_time - last_alert_time):.1f} seconds ago")
                    if plate_img_display is None:
                        plate_img_display = plate_img
                    if thresh_display is None:
                        thresh_display = thresh

        if annotated_frame is not None:
            cv2.imshow('Exit Webcam Feed', annotated_frame)
        if plate_img_display is not None and plate_img_display.size > 0:
            cv2.imshow('Plate', plate_img_display)
        if thresh_display is not None and thresh_display.size > 0:
            cv2.imshow('Processed', thresh_display)

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
            arduino.write(b'0')  # Ensure gate is closed
            arduino.close()
            print("[INFO] Arduino serial port closed.")
        except Exception as e:
            print(f"[ERROR] Exception while closing Arduino: {e}")
    cv2.destroyAllWindows()
    print("[INFO] OpenCV windows destroyed.")
    print("[INFO] Script finished.")

def car_exit_main(db_path_arg=None, camera_index_arg=CAMERA_INDEX, debug_arg=False):
    global DB_PATH, CAMERA_INDEX
    if db_path_arg:
        DB_PATH = db_path_arg
    CAMERA_INDEX = camera_index_arg
    print(f"[INFO] car_exit_main called with DB: {DB_PATH}, Cam: {CAMERA_INDEX}")