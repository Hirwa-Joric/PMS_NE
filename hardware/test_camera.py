#!/usr/bin/env python3
import cv2
import sys
import os

# Fix Qt backend issues
os.environ["QT_QPA_PLATFORM"] = "xcb"

def test_camera(camera_index=0):
    print(f"Testing camera at index {camera_index}")
    
    # Try different backends
    backends = [cv2.CAP_ANY]
    
    # Loop through backends
    for backend in backends:
        try:
            print(f"Trying backend: {backend}")
            cap = cv2.VideoCapture(camera_index, backend)
            
            if not cap.isOpened():
                print(f"Failed to open camera with backend {backend}")
                continue
                
            print("Camera opened successfully! Attempting to read frames...")
            
            # Try to read a few frames to ensure camera is working
            success_count = 0
            for i in range(10):
                ret, frame = cap.read()
                if ret:
                    success_count += 1
                    height, width = frame.shape[:2]
                    print(f"Read successful frame {i+1}: size {width}x{height}")
                else:
                    print(f"Failed to read frame {i+1}")
            
            print(f"Successfully read {success_count}/10 frames")
            
            # Display camera feed
            print("Displaying camera feed. Press 'q' to exit.")
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Failed to read frame")
                    break
                    
                # Add text to verify frame is updating
                cv2.putText(frame, f"Frame: {time.time():.1f}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                cv2.imshow("Camera Test", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
            
            cap.release()
            cv2.destroyAllWindows()
            return True
            
        except Exception as e:
            print(f"Error with backend {backend}: {e}")
            if 'cap' in locals() and cap.isOpened():
                cap.release()
    
    return False

def try_all_cameras():
    print("Searching for available cameras...")
    max_to_try = 5  # Try camera indices 0 through 4
    
    for i in range(max_to_try):
        print(f"\nAttempting to open camera {i}")
        cap = cv2.VideoCapture(i)
        
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print(f"✅ Camera {i} is working!")
                cap.release()
                return i
            else:
                print(f"⚠️ Camera {i} opened but couldn't read frames")
        else:
            print(f"❌ Camera {i} failed to open")
        
        cap.release()
    
    print("No working cameras found")
    return -1

if __name__ == "__main__":
    import time
    
    # Check command line args for camera index
    camera_index = 0
    if len(sys.argv) > 1:
        try:
            camera_index = int(sys.argv[1])
            print(f"Using specified camera index: {camera_index}")
        except ValueError:
            print(f"Invalid camera index: {sys.argv[1]}, using default (0)")
    
    # First, try to find a working camera
    working_index = try_all_cameras()
    
    if working_index >= 0:
        print(f"\nFound working camera at index {working_index}")
        test_camera(working_index)
    else:
        print("\n⚠️ No working cameras found. Trying default index as fallback...")
        test_camera(camera_index)
