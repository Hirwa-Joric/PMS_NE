#!/usr/bin/env python3
"""
Test script to verify all required components for the Intelligent Robotics project.
This script checks:
1. Python environment and package versions
2. Camera access
3. Arduino communication
4. Tesseract OCR functionality
5. YOLO model loading
"""

import os
import sys
import platform
import importlib
import pkg_resources
import subprocess
import time

def print_section(title):
    """Print a section header."""
    print("\n" + "="*80)
    print(f" {title} ".center(80, "="))
    print("="*80)

def check_packages():
    """Check if all required packages are installed and print their versions."""
    print_section("CHECKING PYTHON PACKAGES")
    
    required_packages = [
        "opencv-python", 
        "numpy", 
        "ultralytics", 
        "pytesseract", 
        "pyserial", 
        "python-dateutil", 
        "tqdm"
    ]
    
    python_version = sys.version
    print(f"Python Version: {python_version}")
    
    for package in required_packages:
        try:
            version = pkg_resources.get_distribution(package).version
            print(f"✅ {package}: {version}")
        except pkg_resources.DistributionNotFound:
            print(f"❌ {package}: Not installed")

def check_tesseract():
    """Check if Tesseract OCR is installed and working."""
    print_section("CHECKING TESSERACT OCR")
    
    try:
        import pytesseract
        tesseract_path = pytesseract.pytesseract.tesseract_cmd
        print(f"PyTesseract path: {tesseract_path}")
        
        result = subprocess.run(["tesseract", "--version"], 
                              capture_output=True, text=True)
        version = result.stdout.strip().split("\n")[0]
        print(f"✅ Tesseract OCR: {version}")
    except Exception as e:
        print(f"❌ Tesseract OCR error: {str(e)}")

def check_camera():
    """Check if camera is accessible."""
    print_section("CHECKING CAMERA ACCESS")
    
    try:
        import cv2
        camera_index = 0
        print(f"Attempting to access camera at index {camera_index}...")
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            print(f"❌ Failed to open camera at index {camera_index}")
            return
        
        ret, frame = cap.read()
        if ret:
            print(f"✅ Successfully captured frame from camera {camera_index}")
            print(f"Frame dimensions: {frame.shape[1]}x{frame.shape[0]}")
            
            # Save a test image
            test_image_path = "camera_test.jpg"
            cv2.imwrite(test_image_path, frame)
            print(f"Saved test image to {test_image_path}")
        else:
            print(f"❌ Failed to capture frame from camera {camera_index}")
        
        cap.release()
    except Exception as e:
        print(f"❌ Camera access error: {str(e)}")

def check_arduino():
    """Check if Arduino is connected and list available serial ports."""
    print_section("CHECKING ARDUINO CONNECTION")
    
    try:
        import serial
        import serial.tools.list_ports
        
        ports = list(serial.tools.list_ports.comports())
        
        if not ports:
            print("❌ No serial ports found")
            return
        
        print("Available serial ports:")
        for i, port in enumerate(ports):
            print(f"  {i+1}. {port.device} - {port.description}")
        
        # Try to detect Arduino port based on name patterns
        system = platform.system()
        arduino_port = None
        
        for port in ports:
            if system == "Linux" and ("ttyUSB" in port.device or "ttyACM" in port.device):
                arduino_port = port.device
                break
            elif system == "Darwin" and ("usbmodem" in port.device or "usbserial" in port.device):
                arduino_port = port.device
                break
            elif system == "Windows" and "COM" in port.device:
                arduino_port = port.device
                break
        
        if arduino_port:
            print(f"✅ Detected potential Arduino port: {arduino_port}")
            
            # Try to open the port (don't send any commands)
            try:
                ser = serial.Serial(arduino_port, 9600, timeout=2)
                print(f"✅ Successfully opened serial port {arduino_port}")
                ser.close()
            except Exception as e:
                print(f"❌ Failed to open serial port: {str(e)}")
        else:
            print("❌ No Arduino port detected based on naming patterns")
            
    except Exception as e:
        print(f"❌ Arduino detection error: {str(e)}")

def check_yolo_model():
    """Check if YOLO model can be loaded."""
    print_section("CHECKING YOLO MODEL")
    
    try:
        from ultralytics import YOLO
        
        # Look for model in expected locations
        model_paths = [
            "../model_dev/runs/detect/train/weights/best.pt",
            "../model_dev/runs01/detect/train/weights/best.pt",
            "model_dev/runs/detect/train/weights/best.pt",
            "model_dev/runs01/detect/train/weights/best.pt"
        ]
        
        model_found = False
        for path in model_paths:
            if os.path.exists(path):
                print(f"Found model at: {path}")
                print(f"Attempting to load model...")
                model = YOLO(path)
                print(f"✅ Successfully loaded YOLO model")
                model_found = True
                break
        
        if not model_found:
            print("❌ No YOLO model found in expected locations")
            
    except Exception as e:
        print(f"❌ YOLO model loading error: {str(e)}")

def main():
    """Run all checks."""
    print_section("ENVIRONMENT TEST FOR INTELLIGENT ROBOTICS PROJECT")
    
    print(f"System: {platform.system()} {platform.release()}")
    print(f"Current directory: {os.getcwd()}")
    
    check_packages()
    check_tesseract()
    check_camera()
    check_arduino()
    check_yolo_model()
    
    print_section("ENVIRONMENT TEST COMPLETE")

if __name__ == "__main__":
    main()
