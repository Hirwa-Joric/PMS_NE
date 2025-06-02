#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Intelligent Robotics Parking Management System with RFID Payment Integration
Main orchestrator script that provides a unified interface for running all components.
"""

import os
import sys
import time
import argparse
import threading
import signal
import logging
from datetime import datetime

# Import configuration
try:
    from config import *
except ImportError:
    print("[ERROR] Could not import config.py. Make sure it exists in the same directory.")
    sys.exit(1)

# Setup logging
def setup_logging(log_file='logs/parking_system.log', debug=False):
    """Configure logging for the application."""
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    
    level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('ParkingSystem')

# Parse command line arguments
def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Intelligent Robotics Parking Management System')
    parser.add_argument('--mode', choices=['entry', 'exit', 'topup', 'all'], default='all',
                      help='Operating mode: entry, exit, topup, or all (default)')
    parser.add_argument('--db', default=DB_PATH, help=f'Path to SQLite database (default: {DB_PATH})')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--log', default='logs/parking_system.log', help='Path to log file')
    parser.add_argument('--camera', type=int, default=CAMERA_INDEX, help='Camera index')
    return parser.parse_args()

# Entry system module
def run_entry_system(args, logger):
    """Run the entry system as a separate process."""
    logger.info("Starting entry system...")
    try:
        from car_entry import car_entry_main
        car_entry_thread = threading.Thread(
            target=car_entry_main,
            args=(args.db, args.camera, args.debug),
            daemon=True
        )
        car_entry_thread.start()
        return car_entry_thread
    except ImportError:
        logger.error("Failed to import car_entry module. Entry system not started.")
        return None

# Exit system module
def run_exit_system(args, logger):
    """Run the exit system as a separate process."""
    logger.info("Starting exit system...")
    try:
        from car_exit import car_exit_main
        car_exit_thread = threading.Thread(
            target=car_exit_main,
            args=(args.db, args.camera, args.debug),
            daemon=True
        )
        car_exit_thread.start()
        return car_exit_thread
    except ImportError:
        logger.error("Failed to import car_exit module. Exit system not started.")
        return None

# Top-up system module
def run_topup_system(args, logger):
    """Start the top-up system interface."""
    logger.info("Starting RFID top-up interface...")
    try:
        import top_up_rfid
        print("\n===== RFID Card Top-up System =====")
        print("Please follow the prompts to add credit to an RFID card.")
        top_up_rfid.main(args.db)
        logger.info("Top-up session completed.")
    except ImportError:
        logger.error("Failed to import top_up_rfid module. Top-up system not started.")
    except Exception as e:
        logger.error(f"Error in top-up system: {e}")

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    """Handle Ctrl+C and other signals for clean shutdown."""
    logger.info("Shutdown signal received. Stopping all systems...")
    # Set shutdown flag for threads to detect
    global running
    running = False
    time.sleep(1)  # Give threads time to clean up
    logger.info("Shutdown complete.")
    sys.exit(0)

# Modify car_entry.py and car_exit.py to include main functions
def add_main_functions():
    """Add main functions to entry and exit modules if needed."""
    # Check car_entry.py for main function
    try:
        from car_entry import car_entry_main
    except ImportError:
        logger.warning("car_entry.py doesn't have a car_entry_main function. Adding compatibility...")
        try:
            with open('car_entry.py', 'r') as f:
                content = f.read()
            
            # Add main function if not present
            if "def car_entry_main" not in content:
                with open('car_entry.py', 'a') as f:
                    f.write("""
# Main function added for compatibility with parking_system.py
def car_entry_main(db_path=None, camera_index=0, debug=False):
    \"\"\"Main entry point when run as a module from parking_system.py\"\"\"
    global DB_PATH, CAMERA_INDEX
    if db_path:
        DB_PATH = db_path
    CAMERA_INDEX = camera_index
    # The rest of the script runs as normal when imported
""")
        except Exception as e:
            logger.error(f"Error adding main function to car_entry.py: {e}")
    
    # Check car_exit.py for main function
    try:
        from car_exit import car_exit_main
    except ImportError:
        logger.warning("car_exit.py doesn't have a car_exit_main function. Adding compatibility...")
        try:
            with open('car_exit.py', 'r') as f:
                content = f.read()
            
            # Add main function if not present
            if "def car_exit_main" not in content:
                with open('car_exit.py', 'a') as f:
                    f.write("""
# Main function added for compatibility with parking_system.py
def car_exit_main(db_path=None, camera_index=0, debug=False):
    \"\"\"Main entry point when run as a module from parking_system.py\"\"\"
    global DB_PATH, CAMERA_INDEX
    if db_path:
        DB_PATH = db_path
    CAMERA_INDEX = camera_index
    # The rest of the script runs as normal when imported
""")
        except Exception as e:
            logger.error(f"Error adding main function to car_exit.py: {e}")

# Main function
def main():
    """Main entry point for the parking system."""
    args = parse_args()
    global logger
    logger = setup_logging(args.log, args.debug)
    
    logger.info("=== Intelligent Robotics Parking System Starting ===")
    logger.info(f"Mode: {args.mode}, Database: {args.db}")
    
    # Check database
    if not check_database():
        logger.error("Database setup failed. Exiting.")
        return 1
    
    # Add main functions to modules if needed
    add_main_functions()
    
    # Setup signal handlers for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    global running
    running = True
    
    # Run appropriate subsystems based on mode
    active_threads = []
    
    try:
        if args.mode in ['entry', 'all']:
            entry_thread = run_entry_system(args, logger)
            if entry_thread:
                active_threads.append(entry_thread)
        
        if args.mode in ['exit', 'all']:
            exit_thread = run_exit_system(args, logger)
            if exit_thread:
                active_threads.append(exit_thread)
        
        if args.mode == 'topup':
            run_topup_system(args, logger)
            # Top-up runs in the main thread, so return after completion
            return 0
        
        # If we have active threads, wait for them
        if active_threads:
            logger.info(f"System running with {len(active_threads)} active components. Press Ctrl+C to exit.")
            # Keep main thread alive to handle keyboard interrupts
            while running:
                time.sleep(0.5)
                # Check if threads are still running
                active_threads = [t for t in active_threads if t.is_alive()]
                if not active_threads and running:
                    logger.error("All subsystems have stopped. Exiting.")
                    break
        else:
            logger.error("No subsystems were started successfully. Exiting.")
    
    except Exception as e:
        logger.error(f"Error in main parking system: {e}")
        return 1
    
    logger.info("Parking system shutdown complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
