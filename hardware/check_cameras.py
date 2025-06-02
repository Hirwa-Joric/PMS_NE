# import cv2
#
# for i in range(5):
#     cap = cv2.VideoCapture(i)
#     if cap.read()[0]:
#         print(f"Camera index {i} is available.")
#     cap.release()

import cv2

print("[DEBUG] Attempting to open camera...")
cap = cv2.VideoCapture(0)

if cap.isOpened():
    print("[DEBUG] Camera opened successfully.")
else:
    print("[ERROR] Failed to open camera.")
    exit()

print("[SYSTEM] Ready. Press 'q' to exit.")
while True:
    ret, frame = cap.read()
    if not ret:
        print("[ERROR] Failed to grab frame from camera.")
        break
    cv2.imshow("Live Feed", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
