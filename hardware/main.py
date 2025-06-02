import platform
import cv2
import numpy as np
from ultralytics import YOLO
import pytesseract
import os
import time
import serial
import serial.tools.list_ports
import csv
import logging
from collections import Counter
from datetime import datetime
import re
import argparse
import threading


class PlateRecognitionSystem:
    """Main class for license plate recognition and gate control system."""

    def __init__(self, config):
        """Initialize the system with configuration."""
        self.config = config
        self.setup_logging()
        self.logger.info("Initializing Plate Recognition System")

        # Ensure directories exist
        os.makedirs(config['save_dir'], exist_ok=True)
        os.makedirs(os.path.dirname(config['log_file']), exist_ok=True)

        # Initialize components
        self.init_csv()
        self.load_model()
        self.connect_arduino()
        self.init_camera()

        # State variables
        self.plate_buffer = []
        self.last_saved_plate = None
        self.last_entry_time = 0
        self.entry_count = self.get_entry_count()
        self.running = False

        self.logger.info("System initialization complete")

    def setup_logging(self):
        """Configure logging for the application."""
        log_dir = os.path.dirname(self.config['log_file'])
        os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config['log_file']),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('PlateRecognition')

    def init_csv(self):
        """Initialize CSV log file if it doesn't exist."""
        if not os.path.exists(self.config['csv_file']):
            try:
                with open(self.config['csv_file'], 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['no', 'entry_time', 'exit_time', 'car_plate', 'due_payment', 'payment_status'])
                self.logger.info(f"Created new log file: {self.config['csv_file']}")
            except IOError as e:
                self.logger.error(f"Failed to create CSV file: {e}")
                raise

    def load_model(self):
        """Load the YOLO model for plate detection."""
        try:
            self.logger.info(f"Loading model from {self.config['model_path']}")
            self.model = YOLO(self.config['model_path'])
            self.logger.info("Model loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")
            raise

    def detect_arduino_port(self):
        """Auto-detect Arduino serial port based on the operating system."""
        ports = list(serial.tools.list_ports.comports())
        system = platform.system()

        for port in ports:
            port_desc = f"{port.device} - {port.description}"
            self.logger.debug(f"Found port: {port_desc}")

            if system == "Linux" and ("ttyUSB" in port.device or "ttyACM" in port.device):
                self.logger.info(f"Detected Arduino port on Linux: {port.device}")
                return port.device
            elif system == "Darwin" and ("usbmodem" in port.device or "usbserial" in port.device):
                self.logger.info(f"Detected Arduino port on macOS: {port.device}")
                return port.device
            elif system == "Windows" and "COM" in port.device:
                self.logger.info(f"Detected Arduino port on Windows: {port.device}")
                return port.device

        self.logger.warning("No Arduino port detected")
        return None

    def connect_arduino(self):
        """Connect to Arduino for gate control and distance sensing."""
        self.arduino = None

        if not self.config['use_arduino']:
            self.logger.info("Arduino disabled in configuration")
            return

        try:
            arduino_port = self.detect_arduino_port()
            if arduino_port:
                self.arduino = serial.Serial(arduino_port, 9600, timeout=1)
                time.sleep(2)  # Wait for connection to stabilize
                self.logger.info(f"Connected to Arduino on {arduino_port}")
            else:
                self.logger.warning("Arduino not detected, running in simulation mode")
        except serial.SerialException as e:
            self.logger.error(f"Failed to connect to Arduino: {e}")
            self.logger.warning("Running in simulation mode")

    def init_camera(self):
        """Initialize the webcam for video capture."""
        try:
            self.logger.info(f"Connecting to camera on device {self.config['camera_device']}")
            self.cap = cv2.VideoCapture(self.config['camera_device'])

            if not self.cap.isOpened():
                self.logger.error(f"Failed to open camera on device {self.config['camera_device']}")
                raise IOError("Could not open camera")

            # Set camera properties if specified
            if self.config['camera_width'] and self.config['camera_height']:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config['camera_width'])
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config['camera_height'])

            self.logger.info("Camera initialized successfully")
        except Exception as e:
            self.logger.error(f"Camera initialization error: {e}")
            raise

    def read_distance(self):
        """Read distance value from Arduino or simulate if not available."""
        if self.arduino and self.arduino.is_open and self.arduino.in_waiting > 0:
            try:
                line = self.arduino.readline().decode('utf-8').strip()
                distance = float(line)
                self.logger.debug(f"Read distance from Arduino: {distance}cm")
                return distance
            except (ValueError, serial.SerialException) as e:
                self.logger.warning(f"Error reading from Arduino: {e}")

        # Return simulated distance if Arduino unavailable
        distance = self.mock_ultrasonic_distance()
        self.logger.debug(f"Using simulated distance: {distance}cm")
        return distance

    def mock_ultrasonic_distance(self):
        """Generate a simulated distance value for testing."""
        import random
        return random.choice([random.randint(10, 40)] + [random.randint(60, 150)] * 10)

    def control_gate(self, open_gate=True):
        """Control the gate via Arduino."""
        if not self.arduino or not self.arduino.is_open:
            self.logger.info(f"Gate {'opening' if open_gate else 'closing'} (SIMULATED)")
            return

        try:
            command = b'1' if open_gate else b'0'
            self.arduino.write(command)
            state = "Opening" if open_gate else "Closing"
            self.logger.info(f"Gate {state.lower()} (sent '{command.decode()}')")

            if open_gate:
                # Start a timer to close the gate after the configured duration
                threading.Timer(
                    self.config['gate_open_duration'],
                    self.control_gate,
                    [False]
                ).start()

        except serial.SerialException as e:
            self.logger.error(f"Failed to control gate: {e}")

    def process_plate_image(self, plate_img):
        """Process the plate image for better OCR accuracy."""
        if plate_img.size == 0:
            self.logger.warning("Empty plate image received")
            return None

        try:
            # Convert to grayscale
            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)

            # Apply adaptive thresholding
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 11, 2
            )

            # Noise removal
            kernel = np.ones((1, 1), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            thresh = cv2.medianBlur(thresh, 3)

            return thresh
        except Exception as e:
            self.logger.error(f"Error processing plate image: {e}")
            return None

    def extract_plate_text(self, processed_img):
        """Extract plate text using OCR."""
        if processed_img is None:
            return None

        try:
            # Get OCR options from config
            config = self.config['tesseract_config']

            # Run OCR
            plate_text = pytesseract.image_to_string(
                processed_img, config=config
            ).strip().replace(" ", "")

            return plate_text
        except Exception as e:
            self.logger.error(f"OCR error: {e}")
            return None

    def validate_plate(self, plate_text):
        """Validate the plate format and return normalized plate if valid."""
        if not plate_text:
            return None

        # Define the expected pattern for your plates
        plate_pattern = self.config['plate_regex']

        # Look for the pattern in the OCR result
        matches = re.findall(plate_pattern, plate_text)
        if matches:
            valid_plate = matches[0]
            self.logger.info(f"Valid plate detected: {valid_plate}")
            return valid_plate

        return None

    def save_plate_entry(self, plate_number):
        """Save plate entry to CSV file."""
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with open(self.config['csv_file'], 'a', newline='') as f:
                writer = csv.writer(f)
                self.entry_count += 1
                writer.writerow([
                    self.entry_count,
                    current_time,
                    '',  # exit_time (blank for now)
                    plate_number,
                    '',  # due_payment (blank for now)
                    0  # payment_status (0 = unpaid)
                ])

            self.logger.info(f"Recorded entry for plate {plate_number}")

            # Save plate image if configured
            if self.config['save_plate_images']:
                filename = f"{plate_number}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(os.path.join(self.config['save_dir'], filename), self.current_plate_img)
                self.logger.debug(f"Saved plate image to {filename}")

            return True
        except IOError as e:
            self.logger.error(f"Failed to save plate entry: {e}")
            return False

    def get_entry_count(self):
        """Get the current entry count from the CSV file."""
        try:
            with open(self.config['csv_file'], 'r') as f:
                return sum(1 for _ in f) - 1  # Subtract header row
        except IOError:
            return 0

    def process_frame(self, frame):
        """Process a single frame for plate detection."""
        if frame is None or frame.size == 0:
            self.logger.warning("Empty frame received")
            return frame

        try:
            # Get distance from sensor
            distance = self.read_distance()
            self.logger.debug(f"Current distance: {distance}cm")

            # Only process if vehicle is close enough
            if distance <= self.config['detection_distance']:
                # Run object detection
                results = self.model(frame)

                # Process detection results
                for result in results:
                    for box in result.boxes:
                        # Extract box coordinates
                        x1, y1, x2, y2 = map(int, box.xyxy[0])

                        # Extract plate image
                        plate_img = frame[y1:y2, x1:x2]
                        self.current_plate_img = plate_img.copy()

                        # Process plate image for OCR
                        processed_img = self.process_plate_image(plate_img)
                        if processed_img is None:
                            continue

                        # Extract text with OCR
                        plate_text = self.extract_plate_text(processed_img)
                        if not plate_text:
                            continue

                        # Validate plate format
                        valid_plate = self.validate_plate(plate_text)
                        if valid_plate:
                            self.handle_valid_plate(valid_plate)

                            # Display plate images if in debug mode
                            if self.config['debug_mode']:
                                cv2.imshow("Plate", plate_img)
                                cv2.imshow("Processed", processed_img)

                # Return annotated frame
                return results[0].plot()

            # Return original frame if no vehicle detected
            return frame

        except Exception as e:
            self.logger.error(f"Error processing frame: {e}")
            return frame

    def handle_valid_plate(self, plate_number):
        """Handle a validated license plate."""
        # Add to detection buffer
        self.plate_buffer.append(plate_number)

        # Decision after collecting enough samples
        if len(self.plate_buffer) >= self.config['min_plate_detections']:
            # Get most common plate from buffer (consensus)
            plate_counts = Counter(self.plate_buffer)
            most_common = plate_counts.most_common(1)[0][0]
            most_common_count = plate_counts.most_common(1)[0][1]

            # Check if we have a strong consensus
            buffer_size = len(self.plate_buffer)
            consensus_ratio = most_common_count / buffer_size

            if consensus_ratio >= self.config['min_consensus_ratio']:
                self.logger.info(f"Strong consensus ({consensus_ratio:.2f}) for plate {most_common}")
                current_time = time.time()

                # Check for duplicate entry within cooldown period
                if (most_common != self.last_saved_plate or
                        (current_time - self.last_entry_time) > self.config['entry_cooldown']):

                    # Save plate entry to CSV
                    if self.save_plate_entry(most_common):
                        # Open gate
                        self.control_gate(open_gate=True)

                        # Update state
                        self.last_saved_plate = most_common
                        self.last_entry_time = current_time
                else:
                    self.logger.info(f"Skipped duplicate entry for {most_common} within cooldown period")
            else:
                self.logger.warning(f"Weak consensus ({consensus_ratio:.2f}) for {most_common}, ignoring")

            # Clear buffer after processing
            self.plate_buffer.clear()

    def run(self):
        """Main processing loop."""
        self.logger.info("Starting plate recognition system")
        self.running = True

        try:
            while self.running:
                # Capture frame
                ret, frame = self.cap.read()
                if not ret:
                    self.logger.warning("Failed to capture frame")
                    time.sleep(0.1)
                    continue

                # Process the frame
                processed_frame = self.process_frame(frame)

                # Display frame
                cv2.imshow('Plate Recognition System', processed_frame)

                # Check for exit command
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self.logger.info("Exit requested by user")
                    break

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error(f"Runtime error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up resources")

        if self.cap and self.cap.isOpened():
            self.cap.release()

        if self.arduino and self.arduino.is_open:
            try:
                # Close the gate before exiting
                self.arduino.write(b'0')
                time.sleep(0.5)
                self.arduino.close()
            except serial.SerialException as e:
                self.logger.error(f"Error closing Arduino connection: {e}")

        cv2.destroyAllWindows()
        self.logger.info("System shutdown complete")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='License Plate Recognition System')

    parser.add_argument('--model', type=str, default='../model_dev/runs/detect/train/weights/best.pt',
                        help='Path to the YOLO model')
    parser.add_argument('--camera', type=int, default=0,
                        help='Camera device index')
    parser.add_argument('--arduino', action='store_true', default=True,
                        help='Enable Arduino integration')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode')
    parser.add_argument('--save-images', action='store_true',
                        help='Save detected plate images')

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_arguments()

    # Configuration
    config = {
        'model_path': args.model,
        'camera_device': args.camera,
        'camera_width': 1280,
        'camera_height': 720,
        'use_arduino': args.arduino,
        'debug_mode': args.debug,
        'save_plate_images': args.save_images,

        'save_dir': 'plates',
        'csv_file': 'db.csv',
        'log_file': 'logs/plate_recognition.log',

        'detection_distance': 50,  # cm
        'entry_cooldown': 300,  # seconds (5 minutes)
        'gate_open_duration': 15,  # seconds
        'min_plate_detections': 3,
        'min_consensus_ratio': 0.7,
        'plate_regex': r'(RA[A-Z]\d{3}[A-Z])',  # Regex for plates starting with RA + letter + 3 digits + letter  # Adjust pattern for your plates
        'tesseract_config': '--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    }

    # Create and run the system
    system = PlateRecognitionSystem(config)
    system.run()


if __name__ == "__main__":
    main()