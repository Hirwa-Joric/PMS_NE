import cv2
from ultralytics import YOLO
import pytesseract
import os
import time

# Load YOLOv8 model
model = YOLO('/opt/homebrew/runs/detect/train4/weights/best.pt')  # Absolute path to your best weights

# Create folder to save cropped plates
save_dir = 'plates'
os.makedirs(save_dir, exist_ok=True)

# Initialize webcam
cap = cv2.VideoCapture(0)

plate_count = 0  # Counter for saved plates

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Run YOLO inference
    results = model(frame)

    # Loop over detections
    for result in results:
        for box in result.boxes:
            # Get coordinates
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            # Crop the detected plate
            plate_img = frame[y1:y2, x1:x2]

            # Save cropped plate
            plate_filename = f'{save_dir}/plate_{plate_count}.jpg'
            cv2.imwrite(plate_filename, plate_img)
            plate_count += 1

            # ===== Plate Image Processing =====
            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

            # ===== OCR Extraction =====
            plate_text = pytesseract.image_to_string(thresh, config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

            print(f"[INFO] Extracted Plate Number: {plate_text.strip()}")

            # Show extracted plate image and text
            cv2.imshow("Cropped Plate", plate_img)
            cv2.imshow("Processed Plate", thresh)

            time.sleep(1)  # Pause for 1s after each detection to avoid flooding

    # Show webcam feed with detections
    annotated_frame = results[0].plot()
    cv2.imshow('Webcam Detection', annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()