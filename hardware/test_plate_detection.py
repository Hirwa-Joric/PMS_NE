#!/usr/bin/env python3
import os
import time
import cv2
import numpy as np
import pytesseract
from ultralytics import YOLO
from datetime import datetime
import sqlite3

# Fix Qt platform plugin issue
os.environ["QT_QPA_PLATFORM"] = "xcb"

# Import configuration
from config import DB_PATH, MODEL_PATH, CAMERA_INDEX, OCR_CONFIG, SAVE_DIR

print(f"=== License Plate Detection Test ===")
print(f"Target Plate: RAE327F")
print(f"Model Path: {MODEL_PATH}")
print(f"Camera Index: {CAMERA_INDEX}")
print(f"Database Path: {DB_PATH}")

# Load YOLO model for license plate detection
try:
    model = YOLO(MODEL_PATH)
    print("✅ YOLO model loaded successfully")
except Exception as e:
    print(f"❌ Error loading YOLO model: {e}")
    exit(1)

# Connect to database
try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print("✅ Connected to database successfully")
except Exception as e:
    print(f"❌ Error connecting to database: {e}")
    conn = None

# Initialize camera
try:
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("❌ Failed to open camera")
        exit(1)
    print("✅ Camera initialized successfully")
except Exception as e:
    print(f"❌ Error initializing camera: {e}")
    exit(1)

# Define the buffer for plate readings
CAPTURE_THRESHOLD = 3  # Number of consistent detections before recording
plate_buffer = []
detected_plates = set()
last_detected_time = 0
COOLDOWN_PERIOD = 10  # seconds between detections of the same plate

try:
    print("\nPress 'q' to exit, 's' to save detected plate to database")
    while True:
        # Read frame from camera
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to read frame from camera")
            break
            
        # Detect license plates using YOLO
        results = model(frame, stream=True)
        
        # Process results
        detection_frame = frame.copy()
        detected_text = None
        
        for r in results:
            boxes = r.boxes
            if len(boxes) > 0:
                # Process each detected license plate
                for box in boxes:
                    # Get box coordinates
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # Extract the license plate region
                    plate_region = frame[y1:y2, x1:x2]
                    if plate_region.size == 0:
                        continue
                        
                    # Draw rectangle around the plate
                    cv2.rectangle(detection_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    # Apply OCR to the plate region
                    text = pytesseract.image_to_string(
                        plate_region,
                        config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                    ).strip().replace(' ', '')
                    
                    # Check for the Rwanda plate format (RAxxxA)
                    if text.startswith('RA') and len(text) >= 7:
                        plate = text[:7]
                        pr, dg, su = plate[:2], plate[2:5], plate[5:7]
                        if pr.isalpha() and dg.isdigit() and su.isalpha():
                            # Update display and append to buffer
                            cv2.putText(detection_frame, plate, (x1, y1-10), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                            
                            # Show plate info
                            print(f"🔄 Detected plate: {plate}")
                            plate_buffer.append(plate)
                            detected_text = plate
                        
        # Process buffer to determine consistent detection
        if len(plate_buffer) >= CAPTURE_THRESHOLD:
            # Count occurrences of each plate and get the most common one
            plate_counts = {}
            for p in plate_buffer:
                plate_counts[p] = plate_counts.get(p, 0) + 1
                
            # Find the most common plate
            most_common = max(plate_counts.items(), key=lambda item: item[1])
            detected_plate = most_common[0]
            current_time = time.time()
            
            # Check cooldown to avoid duplicate rapid detections
            if detected_plate not in detected_plates or (current_time - last_detected_time) > COOLDOWN_PERIOD:
                print(f"\n✅ CONFIRMED DETECTION: {detected_plate}")
                detected_plates.add(detected_plate)
                last_detected_time = current_time
                
                # Save the frame with the detected plate
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(SAVE_DIR, f"{detected_plate}_{timestamp}.jpg")
                cv2.imwrite(save_path, frame)
                print(f"📷 Saved plate image to: {save_path}")
                
                # Clear the buffer after processing
                plate_buffer = []
        
        # Display the detection frame
        cv2.imshow("License Plate Detection", detection_frame)
        
        # Check for key presses
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s') and detected_text and conn:
            # Save detected plate to database
            try:
                # Check if plate already has an unpaid record
                cursor.execute(
                    "SELECT log_id FROM parking_log WHERE plate_number = ? AND payment_status = 'UNPAID'", 
                    (detected_text,)
                )
                existing = cursor.fetchone()
                
                if not existing:
                    # Log entry in parking_log table
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    cursor.execute(
                        "INSERT INTO parking_log (plate_number, entry_time, payment_status) VALUES (?, ?, ?)",
                        (detected_text, current_time, 'UNPAID')
                    )
                    conn.commit()
                    print(f"💾 Plate {detected_text} saved to database at {current_time}")
                else:
                    print(f"⚠️ Plate {detected_text} already has an unpaid record in database")
            except Exception as e:
                print(f"❌ Error saving to database: {e}")
                
except KeyboardInterrupt:
    print("\nTest terminated by user")
except Exception as e:
    print(f"\n❌ Error during testing: {e}")
finally:
    # Release resources
    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()
    if conn:
        conn.close()
    print("\n=== Test Complete ===")
