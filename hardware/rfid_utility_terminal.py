#!/usr/bin/env python3
"""
RFID Utility Terminal

A comprehensive menu-driven interface for RFID card management operations including:
- Port selection and Arduino sketch management
- Reading card UIDs
- Reading/writing card data (plate number and balance)
- Database operations (check balance, transaction history)

This utility is designed to provide a robust interface for managing RFID cards
in the Intelligent Robotics parking management system.
"""

import os
import sys
import time
import sqlite3
import serial
import serial.tools.list_ports
import platform
from datetime import datetime
import subprocess

# Helper function for Arduino communication
def wait_for_arduino_msg(serial_conn, expected_prefix, timeout_seconds=15, print_all=True):
    """Wait for a specific message from Arduino with timeout"""
    start_time = time.time()
    buffer = ""
    print(f"[DEBUG_WAIT] Waiting for line starting with '{expected_prefix}' for {timeout_seconds}s...")
    
    # Clear any stale data
    if serial_conn.in_waiting > 0:
        serial_conn.reset_input_buffer()
    
    while time.time() - start_time < timeout_seconds:
        if serial_conn.in_waiting > 0:
            try:
                data = serial_conn.read(serial_conn.in_waiting).decode('utf-8', errors='ignore')
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if print_all and line: print(f"[ARDUINO_RAW] {line}")
                    if expected_prefix == "" or line.startswith(expected_prefix):
                        print(f"[DEBUG_WAIT] Found expected line: {line}")
                        return line 
            except Exception as e:
                print(f"[ERROR_READ] Error reading from Arduino: {e}")
                return None # Error during read
        time.sleep(0.05) # Non-blocking short sleep
    print(f"[TIMEOUT_WAIT] Did not find '{expected_prefix}' from Arduino.")
    return None

# Try to import from config.py in the same directory
try:
    from config import DB_PATH
except ImportError:
    # Default path if config import fails
    script_dir = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(script_dir, 'parking_system.db')
    print(f"[WARNING] Couldn't import DB_PATH from config.py, using default: {DB_PATH}")

# Constants
ARDUINO_SKETCHES_DIR = os.path.dirname(os.path.abspath(__file__))

def clear_screen():
    """Clear the terminal screen for better UI"""
    os.system('cls' if platform.system() == 'Windows' else 'clear')

def detect_arduino_ports():
    """Detect available Arduino ports.
    Returns a list of available ports."""
    available_ports = []
    
    for port in serial.tools.list_ports.comports():
        dev = port.device
        if platform.system() == 'Linux' and ('ttyACM' in dev or 'ttyUSB' in dev):
            available_ports.append(dev)
        elif platform.system() == 'Darwin' and ('usbmodem' in dev or 'usbserial' in dev):
            available_ports.append(dev)
        elif platform.system() == 'Windows' and 'COM' in dev:
            available_ports.append(dev)
    
    return available_ports

def select_arduino_port():
    """Prompt user to select an Arduino port.
    Returns the selected port or None."""
    ports = detect_arduino_ports()
    
    if not ports:
        print("[ERROR] No Arduino ports detected. Please connect an Arduino and try again.")
        return None
    
    print("\nAvailable Arduino ports:")
    for i, port in enumerate(ports, 1):
        print(f"  {i}. {port}")
    
    try:
        choice = int(input("\nSelect a port (number) or 0 to cancel: "))
        if choice == 0:
            return None
        if 1 <= choice <= len(ports):
            return ports[choice - 1]
        else:
            print("[ERROR] Invalid selection.")
            return None
    except ValueError:
        print("[ERROR] Please enter a number.")
        return None

def compile_and_upload_sketch(sketch_path, arduino_port, fqbn="arduino:avr:uno"):
    """Compile and upload an Arduino sketch to the specified port.
    Returns True if successful, False otherwise."""
    print(f"\nAttempting to compile and upload {sketch_path} to {arduino_port}...")
    
    # Check if sketch path exists
    if not os.path.exists(sketch_path):
        print(f"[ERROR] Sketch path does not exist: {sketch_path}")
        return False
    
    # Get the sketch directory (folder containing the .ino file)
    sketch_dir = os.path.dirname(sketch_path)
    
    # Compile the sketch - using the correct command syntax
    # Change directory to the sketch directory and run the compile command
    compile_cmd = f'cd "{sketch_dir}" && arduino-cli compile --fqbn {fqbn} .'
    print(f"Executing: {compile_cmd}")
    compile_result = subprocess.run(compile_cmd, shell=True, capture_output=True, text=True)
    
    if compile_result.returncode != 0:
        print(f"❌ Compile FAILED for {sketch_path}.")
        print(f"Error: {compile_result.stderr}")
        return False
    
    print(f"✅ Compile SUCCESSFUL for {sketch_path}.")
    print(compile_result.stdout)
    
    # Upload the sketch - using the correct command syntax
    upload_cmd = f'cd "{sketch_dir}" && arduino-cli upload -p {arduino_port} --fqbn {fqbn} .'
    print(f"Executing: {upload_cmd}")
    upload_result = subprocess.run(upload_cmd, shell=True, capture_output=True, text=True)
    
    if upload_result.returncode != 0:
        print(f"❌ Upload FAILED for {sketch_path}.")
        print(f"Error: {upload_result.stderr}")
        return False
    
    print(f"✅ Upload SUCCESSFUL for {sketch_path}.")
    print(upload_result.stdout)
    
    # Give the Arduino time to reset after upload
    print("Waiting for Arduino to reset...")
    time.sleep(3)
    
    return True

def read_card_uid(port, sketch_relative_path="rfid_unique_id/rfid_unique_id.ino"):
    """Read and display the UID of an RFID card."""
    sketch_path = os.path.join(ARDUINO_SKETCHES_DIR, sketch_relative_path)
    
    # Check if the sketch exists
    if not os.path.exists(sketch_path):
        print(f"\n[ERROR] Sketch not found at: {sketch_path}")
        return
    
    # Prompt user to upload the sketch
    print(f"\nTo read card UIDs, we need to upload the {sketch_relative_path} sketch to the Arduino.")
    upload = input("\nDo you want to upload the sketch now? (y/n): ").strip().lower()
    
    if upload == 'y':
        print(f"\nUploading sketch to {port}...")
        if not compile_and_upload_sketch(sketch_path, port):
            print("\n[ERROR] Failed to upload sketch.")
            return
        print("\nSketch uploaded successfully!")
    else:
        print("\nSkipping sketch upload. Make sure the correct sketch is already uploaded.")
    
    print("\nConnecting to Arduino...")
    arduino = None
    try:
        arduino = serial.Serial(port, 9600, timeout=0.5)  # Shorter timeout for better responsiveness
        time.sleep(2.5)  # Wait for Arduino to reset
        
        # Clear input buffer
        arduino.reset_input_buffer()
        
        # Wait for the Arduino to send the ready message
        ready_msg = wait_for_arduino_msg(arduino, "RFID_UID_READER_READY", timeout_seconds=10)
        if not ready_msg:
            print("\n[ERROR] Arduino RFID reader did not initialize correctly.")
            return
        
        print("\nPlease present an RFID card to the reader...")
        print("Press Ctrl+C to exit.\n")
        
        # Reset any previously detected card
        arduino.write(b'R')
        
        uid = None
        start_time = time.time()
        timeout_seconds = 60  # Overall operation timeout
        
        # Read until user interrupts or timeout
        while time.time() - start_time < timeout_seconds:
            try:
                if arduino.in_waiting > 0:
                    line = arduino.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        continue
                        
                    print(f"[ARDUINO] {line}")
                    
                    # Check for card detection message
                    if line == "CARD_DETECTED":
                        # Next line should contain the UID
                        uid_line = wait_for_arduino_msg(arduino, "UID:", timeout_seconds=3)
                        if uid_line and uid_line.startswith("UID:"):
                            uid = uid_line[4:].strip().upper()  # Remove "UID:" prefix
                            print(f"\n[UID DETECTED] {uid}")
                            
                            # Check if this UID exists in the database
                            conn = sqlite3.connect(DB_PATH)
                            cursor = conn.cursor()
                            cursor.execute("SELECT plate_number, balance FROM rfid_cards WHERE uid = ?", (uid,))
                            result = cursor.fetchone()
                            conn.close()
                            
                            if result:
                                plate, balance = result
                                print(f"\n[DATABASE] UID: {uid}")
                                print(f"[DATABASE] Plate Number: {plate}")
                                print(f"[DATABASE] Balance: {balance} RWF")
                            else:
                                print(f"\n[DATABASE] UID {uid} not found in database")
                                
                            # Wait for the "ready for next card" message
                            wait_for_arduino_msg(arduino, "READER_READY_FOR_NEXT_CARD", timeout_seconds=3)
                            print("\nReady for next card. Press Ctrl+C to exit.")
                            
                time.sleep(0.1)  # Short sleep to prevent CPU hogging
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                break
        
        if time.time() - start_time >= timeout_seconds and not uid:
            print("\n[TIMEOUT] Operation timed out. No card detected.")
            
    except serial.SerialException as e:
        print(f"\n[ERROR] Serial communication error: {e}")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")
    finally:
        if arduino and arduino.is_open:
            arduino.close()
            print("\nArduino connection closed.")

def read_card_data(port, sketch_relative_path="reading_on_rfid/reading_on_rfid.ino"):
    """Read and display plate number and balance data from an RFID card."""
    # Build the absolute path to the sketch
    sketch_path = os.path.join(ARDUINO_SKETCHES_DIR, sketch_relative_path)
    
    print("\n=== Read RFID Card Data (Plate & Balance) ===")
    print(f"This operation requires the {sketch_relative_path} sketch to be uploaded to the Arduino.")
    
    choice = input("Would you like to upload the required sketch now? (y/n): ")
    if choice.lower() == 'y':
        if not compile_and_upload_sketch(sketch_path, port):
            print("[ERROR] Failed to upload sketch. Please check connections and try again.")
            return
    
    print("\nConnecting to Arduino...")
    arduino = None
    try:
        arduino = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)
        arduino.reset_input_buffer()
        
        while True: # Loop for reading multiple cards
            print("\nPlease present an RFID card to the reader (Ctrl+C to cancel this card)...")
            card_info_block = []
            card_read_success = False
            start_read_time = time.time()
            
            # Wait for "Card detected!"
            detected_card = False
            while time.time() - start_read_time < 15 and not detected_card: # 15s timeout for card detection
                if arduino.in_waiting:
                    line = arduino.readline().decode('utf-8', errors='ignore').strip()
                    if line: 
                        print(f"[ARDUINO] {line}")
                        if "Card detected!" in line:
                            detected_card = True
                            card_info_block.append(line) # Start collecting block
                            break # Move to collect rest of info
                time.sleep(0.05)

            if not detected_card:
                print("No card detected or timeout.")
            else: # Card was detected, now collect the rest of the info block
                while time.time() - start_read_time < 20: # Overall 20s timeout for full block
                    if arduino.in_waiting:
                        line = arduino.readline().decode('utf-8', errors='ignore').strip()
                        if line:
                            print(f"[ARDUINO] {line}")
                            card_info_block.append(line)
                            if "=====================" in line: # End of block marker
                                card_read_success = True
                                break
                    time.sleep(0.05)
            
            if card_read_success:
                print("\n--- Parsed Card Data ---")
                plate_found = "N/A"
                balance_found = "N/A"
                for item in card_info_block:
                    if "Car Plate :" in item:
                        plate_found = item.split("Car Plate :")[1].strip()
                    if "Balance    :" in item:
                        balance_found = item.split("Balance    :")[1].strip()
                print(f"Plate: {plate_found}")
                print(f"Balance: {balance_found}")
                print("------------------------")
            elif detected_card: # Detected but didn't get full block
                print("[WARNING] Card detected but full data block not received.")

            cont = input("\nRead another card? (y/n): ").lower()
            if cont != 'y':
                break
            arduino.reset_input_buffer() # Clear buffer for next read

    except serial.SerialException as e:
        print(f"[ERROR] Serial connection error: {e}")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    finally:
        if arduino and arduino.is_open:
            arduino.close()
            print("Arduino connection closed.")

def write_card_data(port, sketch_relative_path="writing_on_rfid/writing_on_rfid.ino"):
    """Write plate number and balance to an RFID card using robust protocol."""
    sketch_path = os.path.join(ARDUINO_SKETCHES_DIR, sketch_relative_path)
    
    # Check if the sketch exists
    if not os.path.exists(sketch_path):
        print(f"\n[ERROR] Sketch not found at: {sketch_path}")
        return
    
    # Prompt user to upload the sketch
    print(f"\nTo write data to RFID cards, we need to upload the {sketch_relative_path} sketch to the Arduino.")
    upload = input("\nDo you want to upload the sketch now? (y/n): ").strip().lower()
    
    if upload == 'y':
        print(f"\nUploading sketch to {port}...")
        if not compile_and_upload_sketch(sketch_path, port):
            print("\n[ERROR] Failed to upload sketch.")
            return
        print("\nSketch uploaded successfully!")
    else:
        print("\nSkipping sketch upload. Make sure the correct sketch is already uploaded.")
    
    # Get card data from user (do this before connecting to avoid timeout issues)
    plate_number = input("\nEnter plate number to write (7 chars, e.g., RAD123A): ").strip().upper()
    if len(plate_number) != 7:  # Strict 7 char validation
        print("\n[ERROR] Invalid plate number. Must be exactly 7 characters.")
        return
    
    try:
        balance_input = input("Enter initial balance (RWF): ").strip()
        balance_val = int(balance_input)  # For validation
        if balance_val < 0:
            print("\n[ERROR] Balance cannot be negative.")
            return
        balance_str = balance_input  # Keep as string for sending
    except ValueError:
        print("\n[ERROR] Balance must be a number.")
        return
    
    print("\nConnecting to Arduino...")
    arduino = None
    try:
        arduino = serial.Serial(port, 9600, timeout=0.5)  # Shorter timeout for better responsiveness
        time.sleep(2.5)  # Increased delay after opening port for Arduino reset
        
        # Clear buffers
        arduino.reset_input_buffer()
        arduino.reset_output_buffer()
        
        print("Waiting for Arduino to be ready (expecting 'CARD_WRITER_READY')...")
        if not wait_for_arduino_msg(arduino, "CARD_WRITER_READY", timeout_seconds=10):
            print("\n[ERROR] Arduino writer sketch did not initialize correctly.")
            return
        
        print("\nPlease present an RFID card to the reader...")
        if not wait_for_arduino_msg(arduino, "Card_Detected", timeout_seconds=30):
            print("\n[ERROR] Card not detected by Arduino within timeout.")
            return
        
        # Send Plate Number
        if not wait_for_arduino_msg(arduino, "Prompt_Plate", timeout_seconds=5):
            print("\n[ERROR] Arduino did not prompt for plate number.")
            return
            
        arduino.write(f"{plate_number}#".encode())
        print(f"Sent plate: {plate_number}#")
        
        # Wait for plate confirmation
        if not wait_for_arduino_msg(arduino, f"Plate_Received:{plate_number}", timeout_seconds=10):
            print(f"\n[ERROR] Arduino did not confirm plate '{plate_number}' reception.")
            return
        
        # Send Balance
        if not wait_for_arduino_msg(arduino, "Prompt_Balance", timeout_seconds=5):
            print("\n[ERROR] Arduino did not prompt for balance.")
            return
            
        arduino.write(f"{balance_str}#".encode())
        print(f"Sent balance: {balance_str}#")
        
        # Wait for balance confirmation
        if not wait_for_arduino_msg(arduino, f"Balance_Received:{balance_str}", timeout_seconds=10):
            print(f"\n[ERROR] Arduino did not confirm balance '{balance_str}' reception.")
            return
        
        print("\nWriting data to card...")
        
        # Monitor for specific success/failure messages for each block write
        block2_success = False
        block4_success = False
        operation_finished = False
        
        log_buffer = []
        op_timeout = time.time() + 20  # 20 seconds for actual card writing
        
        # Wait for the write operation to begin
        if not wait_for_arduino_msg(arduino, "Attempting_Write", timeout_seconds=5):
            print("\n[ERROR] Arduino did not start write operation.")
            return
        
        # Monitor write operation progress
        while time.time() < op_timeout and not operation_finished:
            line = wait_for_arduino_msg(arduino, "", timeout_seconds=1, print_all=True)  # Read any line
            if line:
                log_buffer.append(line)
                if "Write_Block_Success:2" in line: block2_success = True
                if "Write_Block_Success:4" in line: block4_success = True
                if "Auth_Fail" in line or "Write_Block_Fail" in line:
                    print("\n[ERROR_WRITE] Arduino reported a write/auth failure during block operation.")
                    # Continue monitoring - don't break yet
                if "Card_Operation_Finished" in line:
                    operation_finished = True
            else:  # wait_for_arduino_msg returned None (timeout for that short read)
                pass  # Just continue polling
        
        if block2_success and block4_success and operation_finished:
            print("\n[SUCCESS] Card data written successfully to both blocks.")
            
            # Get card UID
            uid = input("\nEnter the UID of the card (from previous reading): ").strip().upper()
            if uid:
                # Update database
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    
                    # Check if card already exists
                    cursor.execute("SELECT id FROM rfid_cards WHERE uid = ?", (uid,))
                    result = cursor.fetchone()
                    
                    if result:
                        # Update existing card
                        card_id = result[0]
                        cursor.execute(
                            "UPDATE rfid_cards SET plate_number = ?, balance = ? WHERE id = ?", 
                            (plate_number, balance_val, card_id)
                        )
                        print(f"\n[DATABASE] Updated card with UID: {uid}")
                        print(f"[DATABASE] New Plate Number: {plate_number}")
                        print(f"[DATABASE] New Balance: {balance_val} RWF")
                    else:
                        # Insert new card
                        cursor.execute(
                            "INSERT INTO rfid_cards (uid, plate_number, balance, created_at) VALUES (?, ?, ?, ?)",
                            (uid, plate_number, balance_val, datetime.now())
                        )
                        print(f"\n[DATABASE] Added new card with UID: {uid}")
                        print(f"[DATABASE] Plate Number: {plate_number}")
                        print(f"[DATABASE] Balance: {balance_val} RWF")
                    
                    conn.commit()
                    conn.close()
                except sqlite3.Error as dbe:
                    print(f"\n[DATABASE_ERROR] {dbe}")
        else:
            print("\n[ERROR] Card write operation failed or was incomplete.")
            print("Collected logs during operation:")
            for l in log_buffer:
                print(f"  {l}")
        
        # Wait for card removal confirmation
        wait_for_arduino_msg(arduino, "Card_Removed", timeout_seconds=20, print_all=True)
        
    except serial.SerialException as e:
        print(f"\n[ERROR] Serial communication error: {e}")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")
    finally:
        if arduino and arduino.is_open:
            arduino.close()
            print("\nArduino connection closed.")

def check_card_balance(card_uid=None):
    """Check balance for a specific card or list all cards in the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if card_uid:
            # Check specific card
            cursor.execute(
                "SELECT c.plate_number, c.balance, c.created_at, "
                "(SELECT COUNT(*) FROM transactions t WHERE t.card_id = c.id) as tx_count "
                "FROM rfid_cards c WHERE c.card_uid = ?",
                (card_uid,)
            )
            card = cursor.fetchone()
            
            if card:
                plate, balance, created, tx_count = card
                print(f"\n=== Card Information for UID: {card_uid} ===")
                print(f"Plate Number: {plate}")
                print(f"Current Balance: {balance} RWF")
                print(f"Card Created: {created}")
                print(f"Transaction Count: {tx_count}")
            else:
                print(f"No card found with UID: {card_uid}")
        else:
            # List all cards
            cursor.execute(
                "SELECT c.card_uid, c.plate_number, c.balance, "
                "(SELECT COUNT(*) FROM transactions t WHERE t.card_id = c.id) as tx_count "
                "FROM rfid_cards c ORDER BY c.plate_number"
            )
            cards = cursor.fetchall()
            
            if cards:
                print("\n=== All Cards in Database ===")
                print("{:<15} {:<10} {:<12} {:<10}".format("UID", "Plate", "Balance", "Tx Count"))
                print("-" * 50)
                
                for uid, plate, balance, tx_count in cards:
                    print("{:<15} {:<10} {:<12} {:<10}".format(
                        uid[:12] + "..." if len(uid) > 15 else uid,
                        plate,
                        f"{balance} RWF",
                        tx_count
                    ))
                
                print(f"\nTotal Cards: {len(cards)}")
            else:
                print("No cards found in the database.")
        
        conn.close()
    except sqlite3.Error as e:
        print(f"[DATABASE ERROR] {e}")

def view_transaction_history(plate=None):
    """View transaction history for a specific plate number or recent transactions."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Use dictionary-like rows
        cursor = conn.cursor()
        
        if plate:
            # Find card_id for the plate
            cursor.execute("SELECT id FROM rfid_cards WHERE plate_number = ?", (plate,))
            card = cursor.fetchone()
            
            if not card:
                print(f"No card found with plate number: {plate}")
                conn.close()
                return
            
            card_id = card[0]
            
            # Get transactions for this card
            cursor.execute(
                "SELECT t.id, t.amount, t.transaction_type, t.created_at, t.exit_time, "
                "t.entry_point, t.exit_point, t.duration_minutes "
                "FROM transactions t "
                "WHERE t.card_id = ? "
                "ORDER BY t.created_at DESC LIMIT 20",
                (card_id,)
            )
        else:
            # Get recent transactions
            cursor.execute(
                "SELECT t.id, r.plate_number, t.amount, t.transaction_type, "
                "t.created_at, t.exit_time, t.entry_point, t.exit_point, t.duration_minutes "
                "FROM transactions t "
                "JOIN rfid_cards r ON t.card_id = r.id "
                "ORDER BY t.created_at DESC LIMIT 20"
            )
        
        transactions = cursor.fetchall()
        
        if transactions:
            print("\n=== Transaction History ===" + (f" for {plate}" if plate else ""))
            
            if plate:
                print("{:<5} {:<12} {:<15} {:<19} {:<15} {:<10}".format(
                    "ID", "Amount", "Type", "Date/Time", "Duration", "Exit Point"
                ))
                print("-" * 80)
                
                for tx in transactions:
                    print("{:<5} {:<12} {:<15} {:<19} {:<15} {:<10}".format(
                        tx['id'],
                        f"{tx['amount']} RWF",
                        tx['transaction_type'],
                        tx['created_at'],
                        f"{tx['duration_minutes']} min" if tx['duration_minutes'] else "N/A",
                        tx['exit_point'] or "N/A"
                    ))
            else:
                print("{:<5} {:<10} {:<12} {:<15} {:<19} {:<10}".format(
                    "ID", "Plate", "Amount", "Type", "Date/Time", "Exit Point"
                ))
                print("-" * 80)
                
                for tx in transactions:
                    print("{:<5} {:<10} {:<12} {:<15} {:<19} {:<10}".format(
                        tx['id'],
                        tx['plate_number'],
                        f"{tx['amount']} RWF",
                        tx['transaction_type'],
                        tx['created_at'],
                        tx['exit_point'] or "N/A"
                    ))
            
            print(f"\nShowing {len(transactions)} transaction(s)")
        else:
            print("No transactions found.")
        
        conn.close()
    except sqlite3.Error as e:
        print(f"[DATABASE ERROR] {e}")

def initialize_database():
    """Initialize the database with required tables if they don't exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create rfid_cards table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS rfid_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_uid TEXT UNIQUE NOT NULL,
            plate_number TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create transactions table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            transaction_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            entry_time TIMESTAMP,
            exit_time TIMESTAMP,
            entry_point TEXT,
            exit_point TEXT,
            duration_minutes INTEGER,
            FOREIGN KEY (card_id) REFERENCES rfid_cards (id)
        )
        ''')
        
        conn.commit()
        conn.close()
 https://github.com/Hirwa-Joric/PMS_NE.git
    while True:
        clear_screen()
        print("\n==================================================")
        print("       RFID UTILITY TERMINAL - MAIN MENU       ")
        print("==================================================\n")
        print("1. Read Card UID")
        print("2. Read Card Data (Plate & Balance)")
        print("3. Write Card Data")
        print("4. Check Card Balance")
        print("5. View Transaction History")
        print("6. Initialize/Check Database")
        print("0. Exit")
        print("\n--------------------------------------------------")
        
        choice = input("\nEnter your choice (0-6): ")
        
        if choice == '0':
            print("\nExiting RFID Utility Terminal. Goodbye!")
            break
        
        elif choice == '1':
            port = select_arduino_port()
            if port:
                read_card_uid(port)
                input("\nPress Enter to continue...")
        
        elif choice == '2':
            port = select_arduino_port()
            if port:
                read_card_data(port)
                input("\nPress Enter to continue...")
        
        elif choice == '3':
            port = select_arduino_port()
            if port:
                write_card_data(port)
                input("\nPress Enter to continue...")
        
        elif choice == '4':
            clear_screen()
            print("\n=== Check Card Balance ===")
            print("1. Check specific card by UID")
            print("2. List all cards")
            subchoice = input("\nEnter your choice (1-2): ")
            
            if subchoice == '1':
                uid = input("Enter card UID: ").strip()
                if uid:
                    check_card_balance(uid)
                else:
                    print("[ERROR] Invalid UID.")
            elif subchoice == '2':
                check_card_balance()
            else:
                print("[ERROR] Invalid choice.")
            
            input("\nPress Enter to continue...")
        
        elif choice == '5':
            clear_screen()
            print("\n=== View Transaction History ===")
            print("1. View transactions for a specific plate number")
            print("2. View recent transactions")
            subchoice = input("\nEnter your choice (1-2): ")
            
            if subchoice == '1':
                plate = input("Enter plate number: ").strip().upper()
                if plate:
                    view_transaction_history(plate)
                else:
                    print("[ERROR] Invalid plate number.")
            elif subchoice == '2':
                view_transaction_history()
            else:
                print("[ERROR] Invalid choice.")
            
            input("\nPress Enter to continue...")
        
        elif choice == '6':
            initialize_database()
            input("\nPress Enter to continue...")
        
        else:
            print("[ERROR] Invalid choice. Please enter a number between 0 and 6.")
            input("\nPress Enter to continue...")

if __name__ == "__main__":
    # Initialize database when script starts
    initialize_database()
    # Start the main menu
    main_menu()
