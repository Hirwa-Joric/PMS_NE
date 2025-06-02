import cv2
from ultralytics import YOLO
import pytesseract
import os
import time
import re

# Load YOLOv8 model (update path if needed)
model = YOLO('/opt/homebrew/runs/detect/train4/weights/best.pt')

# Create folder to save cropped plates
save_dir = 'plates'
os.makedirs(save_dir, exist_ok=True)

# Initialize webcam
cap = cv2.VideoCapture(0)
plate_count = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Run YOLO inference
    results = model(frame)

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            # Crop detected plate
            plate_img = frame[y1:y2, x1:x2]

            # Save cropped plate
            plate_filename = f'{save_dir}/plate_{plate_count}.jpg'
            cv2.imwrite(plate_filename, plate_img)
            plate_count += 1

            # ===== COOL Plate Processing =====
            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

            # ===== OCR Extraction =====
            plate_text = pytesseract.image_to_string(
                thresh,
                config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            ).strip()

            # ===== Validation Logic =====
            match = re.search(r'RA[A-Z0-9 ]*', plate_text.upper())
            if match:
                plate_candidate = match.group()
                plate_clean = plate_candidate.replace(" ", "")

                if len(plate_clean) == 7:
                    first_three = plate_clean[:3]
                    digits_part = plate_clean[3:6]
                    last_char = plate_clean[6]

                    if first_three.isalpha() and digits_part.isdigit() and last_char.isalpha():
                        print(f"✅ Valid Plate: {plate_clean}")
                    else:
                        print(f"❌ Invalid Format: {plate_clean}")
                else:
                    print(f"❌ Incorrect Length after cleaning: {plate_clean}")
            else:
                print(f"❌ No valid RA plate found in: '{plate_text}'")

            # Show processed images
            cv2.imshow("Cropped Plate", plate_img)
            cv2.imshow("Processed Plate", thresh)
            time.sleep(1)

    # Show annotated webcam frame
    annotated_frame = results[0].plot()
    cv2.imshow('Webcam Detection', annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()