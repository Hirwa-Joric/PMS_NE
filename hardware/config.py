#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Configuration module for Intelligent Robotics Parking Management System.
This module centralizes all configuration settings for the various components.
"""

import os
import sys
import platform

# Base paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARDWARE_DIR = os.path.join(ROOT_DIR, 'hardware')
MODEL_DIR = os.path.join(ROOT_DIR, 'model_dev')

# Database configuration
DB_FILENAME = 'parking_system.db'
DB_PATH = os.path.join(HARDWARE_DIR, DB_FILENAME)

# Model configuration
MODEL_PATH = os.path.join(MODEL_DIR, 'runs/detect/train/weights/best.pt')

# Serial communication
GATE_BAUD_RATE = 115200  # For distance sensor and gate control
RFID_BAUD_RATE = 9600    # For RFID reader/writer

# RFID and Payment settings
PAYMENT_RATE_PER_HOUR = 500  # RWF per hour
PAYMENT_RATE_PER_MINUTE = PAYMENT_RATE_PER_HOUR / 60
DEFAULT_INITIAL_BALANCE = 5000  # RWF for new cards

# Parking system settings
ENTRY_COOLDOWN = 300      # seconds between same vehicle entries
MAX_DISTANCE = 50         # cm - maximum distance for sensor detection
MIN_DISTANCE = 0          # cm - minimum distance for sensor detection
CAPTURE_THRESHOLD = 3     # number of consistent reads before logging a plate
GATE_OPEN_TIME = 15       # seconds to keep gate open after RFID authorization
PAYMENT_GRACE_PERIOD = 5  # minutes allowed to exit after payment

# Gate control commands
GATE_OPEN_COMMAND = b'1'
GATE_CLOSE_COMMAND = b'0'
ALERT_COMMAND = b'2'

# Arduino configuration
USE_SINGLE_ARDUINO = False  # Set to False for initial testing with separate Arduinos for gate and payment

# Auto-detect Arduino serial ports
def detect_arduino_ports():
    """
    Auto-detect available Arduino ports.
    Returns a tuple of (gate_arduino_port, payment_arduino_port)
    """
    try:
        import serial.tools.list_ports
        
        available_ports = []
        
        for port in serial.tools.list_ports.comports():
            dev = port.device
            if platform.system() == 'Linux' and ('ttyACM' in dev or 'ttyUSB' in dev):
                available_ports.append(dev)
            elif platform.system() == 'Darwin' and ('usbmodem' in dev or 'usbserial' in dev):
                available_ports.append(dev)
            elif platform.system() == 'Windows' and 'COM' in dev:
                available_ports.append(dev)
        
        if not available_ports:
            return None, None
        
        if len(available_ports) == 1 or USE_SINGLE_ARDUINO:
            # Use the same port for both gate control and payment if only one is available
            return available_ports[0], available_ports[0]
        else:
            # If multiple Arduino ports are available, use the first two
            return available_ports[0], available_ports[1]
            
    except ImportError:
        print("[ERROR] pyserial not installed. Cannot detect Arduino ports.")
        return None, None

# OCR configuration
OCR_CONFIG = '--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

# Camera and display settings
CAMERA_INDEX = 0
WEBCAM_WINDOW_SIZE = (800, 600)

# Plate image directory
SAVE_DIR = os.path.join(HARDWARE_DIR, 'plates')
os.makedirs(SAVE_DIR, exist_ok=True)

# Debug level
DEBUG = True  # Set to False in production

def check_database():
    """
    Check if database exists and offer to create it if missing
    """
    if not os.path.exists(DB_PATH):
        print(f"[WARNING] Database not found at {DB_PATH}")
        create_db = input("Would you like to create the database now? (y/n): ")
        if create_db.lower() == 'y':
            try:
                from database_setup import main as setup_db
                setup_db()
                print(f"[INFO] Created database at {DB_PATH}")
                return True
            except ImportError:
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        "database_setup", 
                        os.path.join(HARDWARE_DIR, "database_setup.py")
                    )
                    db_setup = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(db_setup)
                    db_setup.main()
                    print(f"[INFO] Created database at {DB_PATH}")
                    return True
                except Exception as e:
                    print(f"[ERROR] Failed to create database: {e}")
                    return False
        else:
            print("[INFO] Continuing without database.")
            return False
    return True
