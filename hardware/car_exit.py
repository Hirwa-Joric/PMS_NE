# IntelligentRobotics/hardware/car_exit.py
import os
os.environ["QT_QPA_PLATFORM"] = "xcb" # For Linux compatibility
import platform
import cv2
import numpy as np
from ultralytics import YOLO
import pytesseract
import time
import serial
import serial.tools.list_ports
import sqlite3
from collections import Counter
from datetime import datetime
import sys # For sys.exit

try:
    from config import (
        DB_PATH, MODEL_PATH, MAX_DISTANCE, MIN_DISTANCE, USE_SINGLE_ARDUINO,
        GATE_BAUD_RATE, RFID_BAUD_RATE, GATE_OPEN_COMMAND, GATE_CLOSE_COMMAND,
        ALERT_COMMAND, PAYMENT_GATE_DELAY, CAPTURE_THRESHOLD, OCR_CONFIG
    )
    from config import check_database, detect_arduino_ports # Import helper functions
except ImportError:
    print("[CRITICAL_ERROR] config.py not found or essential variables missing. Exiting.")
    sys.exit(1)

# --- Global Variables & States ---
gate_arduino = None
payment_arduino = None # Might be the same as gate_arduino if USE_SINGLE_ARDUINO is True
model = None
cap = None

# For non-blocking timers/actions
gate_status = "CLOSED"  # "CLOSED", "OPENING", "OPEN", "CLOSING"
gate_action_finish_time = 0
last_distance_read_time = 0.0
distance_read_interval = 0.25 # seconds, how often to query distance

# --- Helper Functions ---
def initialize_yolo_model():
    global model
    try:
        print(f"[INFO] Loading YOLO model from: {MODEL_PATH}")
        model = YOLO(MODEL_PATH)
        print("[SUCCESS] YOLO model loaded.")
        return True
    except Exception as e:
        print(f"[CRITICAL_ERROR] Failed to load YOLO model: {e}")
        return False

def initialize_camera(camera_index=0):
    global cap
    print(f"[INFO] Initializing camera (index {camera_index})...")
    for attempt in range(3): # Try a few times
        cap = cv2.VideoCapture(camera_index)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                print(f"[SUCCESS] Camera {camera_index} initialized.")
                return True
            else:
                cap.release()
                print(f"[WARNING] Camera {camera_index} opened but failed to read frame (Attempt {attempt+1}).")
        else:
            print(f"[WARNING] Failed to open camera {camera_index} (Attempt {attempt+1}).")
        time.sleep(0.5)
    print(f"[CRITICAL_ERROR] Could not initialize camera {camera_index} after multiple attempts.")
    return False

def connect_serial_port(port_name, baud_rate, description, timeout=0.1):
    """Attempts to connect to a serial port with a short timeout."""
    if not port_name:
        print(f"[WARNING] No port specified for {description}.")
        return None
    try:
        print(f"[INFO] Attempting to connect to {description} on {port_name} (Baud: {baud_rate})")
        ser = serial.Serial(port_name, baud_rate, timeout=timeout) # Short timeout for non-blocking reads
        time.sleep(2) # Allow Arduino to reset
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        if ser.is_open:
            print(f"[SUCCESS] Connected to {description} on {port_name}.")
            return ser
        else:
            print(f"[ERROR] Failed to open {description} port {port_name} (already reported by pyserial).")
            return None
    except serial.SerialException as e:
        print(f"[ERROR] SerialException connecting to {description} on {port_name}: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Unexpected error connecting to {description} on {port_name}: {e}")
        return None

def initialize_arduinos():
    global gate_arduino, payment_arduino, GATE_ARDUINO_PORT, PAYMENT_ARDUINO_PORT

    detected_gate_port, detected_payment_port = detect_arduino_ports()
    GATE_ARDUINO_PORT = detected_gate_port # Update global for reference

    if GATE_ARDUINO_PORT:
        gate_arduino = connect_serial_port(GATE_ARDUINO_PORT, GATE_BAUD_RATE, "Gate Arduino")
    else:
        print("[WARNING] No Gate Arduino port detected by config.py.")

    if USE_SINGLE_ARDUINO:
        if gate_arduino:
            payment_arduino = gate_arduino
            PAYMENT_ARDUINO_PORT = GATE_ARDUINO_PORT
            print(f"[INFO] Single Arduino mode: Using Gate Arduino ({GATE_ARDUINO_PORT}) for payments.")
        else:
            print("[ERROR] Single Arduino mode, but Gate Arduino connection failed. Payment will not work.")
    else: # Dual Arduino mode
        PAYMENT_ARDUINO_PORT = detected_payment_port
        if PAYMENT_ARDUINO_PORT and PAYMENT_ARDUINO_PORT != GATE_ARDUINO_PORT:
            payment_arduino = connect_serial_port(PAYMENT_ARDUINO_PORT, RFID_BAUD_RATE, "Payment Arduino")
        elif PAYMENT_ARDUINO_PORT == GATE_ARDUINO_PORT:
            print(f"[INFO] Detected payment port is same as gate port ({GATE_ARDUINO_PORT}).")
            if gate_arduino:
                payment_arduino = gate_arduino # Use the same connection object if ports are identical
                print("[INFO] Using Gate Arduino connection for payments (same port detected).")
            else:
                print("[WARNING] Payment port is same as gate, but gate Arduino connection failed.")
        else:
            print("[WARNING] No distinct Payment Arduino port detected. Payment processing might be affected.")
            # Fallback: if gate arduino exists, and no payment arduino, payment might still use gate_arduino if sketch supports
            if gate_arduino and not payment_arduino:
                payment_arduino = gate_arduino # Assign if no other payment arduino configured
                print("[INFO] Fallback: Using Gate Arduino for payments as no separate payment Arduino found.")

    if not gate_arduino:
        print("[CRITICAL] Gate Arduino not connected. Gate and distance sensor functionality will be unavailable.")
    if not payment_arduino:
        print("[CRITICAL] Payment Arduino not connected. RFID payment functionality will be unavailable.")
    return gate_arduino is not None # Return True if at least gate_arduino connected

def read_distance_non_blocking(ser_conn):
    if not ser_conn or not ser_conn.is_open:
        return None
    try:
        if ser_conn.in_waiting > 0:
            line = ser_conn.readline().decode('utf-8', errors='ignore').strip()
            if line:
                # Sanity check for numeric value and plausible range
                val = float(line)
                if 0 <= val <= 1000: # Assuming distance is in cm, up to 10m
                    return val
                else:
                    # print(f"[DEBUG_DIST] Discarded out-of-range distance: {val}")
                    return None # Or last known good, or specific error code
            return None # Empty line
        return None # No data available
    except ValueError:
        # print(f"[DEBUG_DIST] ValueError converting distance: '{line}'")
        return None
    except Exception as e:
        print(f"[ERROR_DIST_READ] {e}")
        return None

def control_gate(action, ser_conn):
    global gate_status, gate_action_finish_time
    if not ser_conn or not ser_conn.is_open:
        print(f"[GATE_ERROR] Arduino not connected for action: {action}")
        return

    command = None
    if action == "OPEN":
        command = GATE_OPEN_COMMAND
        gate_status = "OPENING"
    elif action == "CLOSE":
        command = GATE_CLOSE_COMMAND
        gate_status = "CLOSING"
    elif action == "ALARM":
        command = ALERT_COMMAND
        print(f"[GATE_ALARM] Triggering alarm (sent '{command.decode()}').")

    if command:
        try:
            ser_conn.write(command)
            print(f"[GATE_CMD] Sent '{command.decode()}' to {ser_conn.port}")
            if action == "OPEN":
                gate_action_finish_time = time.time() + GATE_OPEN_TIME # GATE_OPEN_TIME from config
                gate_status = "OPEN" # Assume it opens quickly
                print(f"[GATE_INFO] Gate is now {gate_status}, will auto-close in {GATE_OPEN_TIME}s.")
            elif action == "CLOSE":
                gate_status = "CLOSED"
                print(f"[GATE_INFO] Gate is now {gate_status}.")
        except serial.SerialException as e:
            print(f"[GATE_ERROR] Serial error sending command {action}: {e}")
            gate_status = "ERROR" # Mark gate status as error
        except Exception as e:
            print(f"[GATE_ERROR] Unexpected error sending command {action}: {e}")
            gate_status = "ERROR"


def validate_plate_format(plate_text):
    """Validates if the plate text matches the Rwandan format RAxxxA or RAAxxxA"""
    if not plate_text or not isinstance(plate_text, str):
        return None
    
    plate_text = plate_text.upper().replace(" ", "")
    
    # Common Rwandan formats: RA[A-Z][0-9]{3}[A-Z] or R[A-Z]{2}[0-9]{3}[A-Z]
    # Simplified for now: Starts with RA, then 3 letters, 3 digits, 1 letter
    # Or RA, 2 letters, 3 digits, 1 letter
    # Let's be more general for OCR robustness: R[A-Z]{1,2}[0-9]{3}[A-Z]
    
    # Assuming specific format from car_entry: RA + Alpha + 3 Digits + Alpha (e.g. RAG123H)
    # Or RA + 2 Alpha + 3 Digits + Alpha (e.g. RAA123H - this seems to be a typo in earlier examples, let's stick to 7 chars)
    
    if len(plate_text) < 7: # Minimum length for Rwandan plates like RAA123B
        return None

    # Try RA[A-Z][0-9]{3}[A-Z] (e.g., RAG123X) - 7 chars
    if plate_text.startswith("RA") and len(plate_text) == 7:
        prefix = plate_text[0:2] # RA
        char2 = plate_text[2]    # Letter
        digits = plate_text[3:6] # 3 Digits
        char6 = plate_text[6]    # Letter
        if char2.isalpha() and digits.isdigit() and char6.isalpha():
            return f"{prefix}{char2}{digits}{char6}"

    # Try R[A-Z]{2}[0-9]{3}[A-Z] (e.g. RAB123C) - 7 chars (this pattern is more general)
    if len(plate_text) == 7 and plate_text[0] == 'R' and \
       plate_text[1:3].isalpha() and \
       plate_text[3:6].isdigit() and \
       plate_text[6].isalpha():
        return plate_text
        
    return None # No valid format matched

# --- Main Application Logic ---
def main_car_exit_loop():
    global gate_arduino, payment_arduino, model, cap
    global gate_status, gate_action_finish_time, last_distance_read_time, distance_read_interval
    global plate_buffer, plate_buffer_time, plate_buffer_timeout

    # --- Initializations ---
    if not initialize_yolo_model(): sys.exit(1)
    if not initialize_camera(CAMERA_INDEX): sys.exit(1) # CAMERA_INDEX from config
    if not initialize_arduinos():
        print("[WARNING] Arduino initialization failed. Proceeding with limited functionality.")
        # Allow script to run for camera feed even if Arduinos fail, for debugging

    if not check_database():
        print("[WARNING] Database check/setup failed. DB operations might not work.")

    # Blank frames for display consistency
    blank_feed_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(blank_feed_frame, "No Camera Signal / Error", (30, 230), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    blank_plate_frame = np.zeros((100, 300, 3), dtype=np.uint8) # Example size
    cv2.putText(blank_plate_frame, "No Plate", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 1)
    
    # Window setup
    cv2.namedWindow("Exit Webcam Feed", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Plate", cv2.WINDOW_AUTOSIZE)
    cv2.namedWindow("Processed", cv2.WINDOW_AUTOSIZE)
    cv2.namedWindow("System Status", cv2.WINDOW_AUTOSIZE)
    cv2.resizeWindow("Exit Webcam Feed", 800, 600)
    cv2.resizeWindow("System Status", 800, 100) # Height for 2 lines of text

    distance = MAX_DISTANCE + 10 # Initialize out of range
    frame_count = 0
    running = True

    # --- Main Loop ---
    print("[INFO] Car Exit System Ready. Press 'q' to quit.")
    while running:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            running = False
            break
        elif key == ord('r'):
            plate_buffer.clear()
            print("[INFO] Plate buffer cleared by user.")

        current_time = time.time()

        # --- Handle Gate Auto-Close ---
        if gate_status == "OPEN" and current_time >= gate_action_finish_time:
            control_gate("CLOSE", gate_arduino)

        # --- Read Camera Frame ---
        ret, frame = cap.read()
        if not ret or frame is None:
            # print("[WARNING] Failed to grab frame from camera.")
            annotated_display_frame = blank_feed_frame
            plate_img_display = blank_plate_frame
            processed_plate_display = blank_plate_frame
            time.sleep(0.05) # Don't spin too fast on camera failure
        else:
            annotated_display_frame = frame.copy() # Default to current frame
            plate_img_display = blank_plate_frame # Default until plate detected
            processed_plate_display = blank_plate_frame # Default until plate processed

            # --- Read Distance Sensor ---
            if current_time - last_distance_read_time > distance_read_interval:
                sensor_reading = read_distance_non_blocking(gate_arduino)
                if sensor_reading is not None:
                    distance = sensor_reading
                # If sensor_reading is None, distance retains its previous value
                # print(f"[SENSOR_DEBUG] Current Distance: {distance} cm")
                last_distance_read_time = current_time
            
            # --- ANPR and Core Logic (if vehicle detected and gate is not already dealing with a car) ---
            if distance is not None and MIN_DISTANCE <= distance <= MAX_DISTANCE and gate_status == "CLOSED":
                try:
                    results = model(frame, verbose=False, conf=0.6) # Added confidence
                    if results and results[0].boxes:
                        annotated_display_frame = results[0].plot() # Update with detections
                        for box in results[0].boxes:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            plate_img_crop = frame[y1:y2, x1:x2]

                            if plate_img_crop.size > 0:
                                plate_img_display = plate_img_crop.copy() # For display
                                gray = cv2.cvtColor(plate_img_crop, cv2.COLOR_BGR2GRAY)
                                blur = cv2.GaussianBlur(gray, (5,5), 0)
                                _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                                processed_plate_display = thresh.copy() # For display

                                plate_text_raw = pytesseract.image_to_string(thresh, config=OCR_CONFIG).strip()
                                plate_text = validate_plate_format(plate_text_raw)

                                if plate_text:
                                    print(f"[PLATE_DETECTED] {plate_text} (Raw: {plate_text_raw})")
                                    plate_buffer.append(plate_text)
                                    plate_buffer_time = current_time # Reset buffer timeout

                                    if len(plate_buffer) >= CAPTURE_THRESHOLD:
                                        most_common_plate = Counter(plate_buffer).most_common(1)[0][0]
                                        plate_buffer.clear()
                                        print(f"[PLATE_CONFIRMED] Exit attempt for: {most_common_plate}")
                                        
                                        # Check if payment is required or already handled
                                        if handle_exit(most_common_plate): # True if already paid/no record
                                            print(f"[ACCESS_GRANTED] {most_common_plate} already paid or no record.")
                                            control_gate("OPEN", gate_arduino)
                                        else: # Payment is required
                                            print(f"[PAYMENT_PROCESS] Initiating for {most_common_plate}")
                                            if process_vehicle_payment(most_common_plate): # This function handles RFID
                                                print(f"[PAYMENT_SUCCESS] {most_common_plate}.")
                                                control_gate("OPEN", gate_arduino)
                                            else:
                                                print(f"[PAYMENT_FAIL] {most_common_plate}.")
                                                control_gate("ALARM", gate_arduino)
                                        # To prevent immediate re-triggering for the same car
                                        time.sleep(5) # Brief pause after processing a car
                                        distance = MAX_DISTANCE + 10 # Move "car" out of range virtually
                                break # Process only the first detected plate in a frame
                except Exception as e_anpr:
                    print(f"[ERROR_ANPR_LOOP] {e_anpr}")
        
        # --- Update Status Display ---
        frame_count += 1
        if frame_count % 10 == 0: # Update status display less frequently
            status_frame.fill(0) 
            s_gate_arduino = "OK" if gate_arduino and gate_arduino.is_open else "ERR"
            s_payment_arduino = "OK" if payment_arduino and payment_arduino.is_open else "ERR"
            s_camera = "OK" if cap and cap.isOpened() else "ERR"
            
            status_text1 = f"GateArd: {s_gate_arduino} | PayArd: {s_payment_arduino} | Cam: {s_camera}"
            status_text2 = f"Dist: {distance:.1f}cm | Gate: {gate_status} | F#: {frame_count}"
            cv2.putText(status_frame, status_text1, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0),1)
            cv2.putText(status_frame, status_text2, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0),1)
        
        # --- Display Frames ---
        try:
            cv2.imshow("Exit Webcam Feed", annotated_display_frame)
            cv2.imshow("Plate", plate_img_display)
            cv2.imshow("Processed", processed_plate_display)
            cv2.imshow("System Status", status_frame)
        except cv2.error as e:
            print(f"[ERROR_CV_SHOW] {e}")
            # Attempt to re-initialize windows if they were closed by user
            # This is often problematic, better to restart script if user closes windows.
            if "NULL window" in str(e) or "NULL picture" in str(e):
                 print("[INFO] OpenCV window might have been closed. Trying to recreate.")
                 # Recreate windows (may not always work as expected)
                 try:
                    cv2.namedWindow("Exit Webcam Feed", cv2.WINDOW_NORMAL)
                    cv2.namedWindow("Plate", cv2.WINDOW_AUTOSIZE)
                    cv2.namedWindow("Processed", cv2.WINDOW_AUTOSIZE)
                    cv2.namedWindow("System Status", cv2.WINDOW_AUTOSIZE)
                    cv2.resizeWindow("Exit Webcam Feed", 800, 600)
                    cv2.resizeWindow("System Status", 800, 100)
                 except Exception as e_recreate:
                    print(f"[ERROR] Failed to recreate windows: {e_recreate}")
                    running = False # Stop if windows can't be managed

    # --- End of Main Loop ---
    print("[INFO] Main loop exited.")

# --- Cleanup Function ---
def cleanup_resources():
    global cap, gate_arduino, payment_arduino
    print("[CLEANUP] Releasing resources...")
    if cap:
        cap.release()
        print("[INFO] Camera released.")
    if gate_arduino and gate_arduino.is_open:
        try:
            gate_arduino.write(GATE_CLOSE_COMMAND) # Ensure gate is closed
            gate_arduino.close()
            print("[INFO] Gate Arduino closed.")
        except Exception as e: print(f"[ERROR_CLEANUP] Closing Gate Arduino: {e}")
    if payment_arduino and payment_arduino.is_open and payment_arduino != gate_arduino: # Avoid double close
        try:
            payment_arduino.close()
            print("[INFO] Payment Arduino closed.")
        except Exception as e: print(f"[ERROR_CLEANUP] Closing Payment Arduino: {e}")
    cv2.destroyAllWindows()
    print("[INFO] OpenCV windows destroyed.")
    print("[EXIT] Program terminated.")


if __name__ == "__main__":
    try:
        main_car_exit_loop()
    except KeyboardInterrupt:
        print("\n[EXIT] KeyboardInterrupt detected by main thread. Exiting gracefully...")
    except Exception as e_global:
        print(f"[CRITICAL_GLOBAL_ERROR] An unhandled exception occurred: {e_global}")
    finally:
        cleanup_resources()