#!/usr/bin/env python3
"""
RFID Manager Utility

This script provides a menu-driven interface for RFID card management operations, including:
- Reading card UIDs
- Reading card data (plate number and balance)
- Writing/updating card data
- Checking card balances in the database

It also helps users upload the appropriate Arduino sketches for each operation.
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

# Try to import from config.py in the same directory
try:
    from config import DB_PATH
except ImportError:
    # Default path if config import fails
    script_dir = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(script_dir, '..', 'parking_system.db')
    print(f"[WARNING] Couldn't import DB_PATH from config.py, using default: {DB_PATH}")

# Constants
# The sketches are directly in the hardware directory
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
        print(f"❌ Upload FAILED for {sketch_path} to {arduino_port}.")
        print(f"Error: {upload_result.stderr}")
        return False
    
    print(f"✅ Upload SUCCESSFUL for {sketch_path} to {arduino_port}.")
    print(upload_result.stdout)
    time.sleep(2)  # Give Arduino time to reset
    return True

def read_card_uid(port, sketch_relative_path="rfid_unique_id/rfid_unique_id.ino"):
    """Read and display the UID of an RFID card."""
    # Build the absolute path to the sketch
    sketch_path = os.path.join(ARDUINO_SKETCHES_DIR, sketch_relative_path)
    
    print("\n=== Read RFID Card UID ===")
    print(f"This operation requires the {sketch_relative_path} sketch to be uploaded to the Arduino.")
    
    choice = input("Would you like to upload the required sketch now? (y/n): ")
    if choice.lower() == 'y':
        if not compile_and_upload_sketch(sketch_path, port):
            print("[ERROR] Failed to upload sketch. Please check connections and try again.")
            return
    
    print("\nConnecting to Arduino...")
    try:
        # Connect to Arduino at 9600 baud (standard for RFID operations)
        arduino = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)  # Give Arduino time to reset
        arduino.reset_input_buffer()
        
        print("\nPlease present an RFID card to the reader...")
        print("Press Ctrl+C to cancel.")
        
        # Wait for card to be read
        while True:
            if arduino.in_waiting:
                line = arduino.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"\n[CARD UID] {line}")
                    
                    # Ask if user wants to read another card
                    choice = input("\nRead another card? (y/n): ")
                    if choice.lower() != 'y':
                        break
                    print("\nPlease present another RFID card...")
            
            time.sleep(0.1)
        
        arduino.close()
        print("\nArduino connection closed.")
    
    except serial.SerialException as e:
        print(f"[ERROR] Serial connection error: {e}")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        if 'arduino' in locals():
            arduino.close()
            print("Arduino connection closed.")

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

def update_database(plate, balance, uid=None):
    """Update the database with card information.
    Returns True if successful, False otherwise."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if card exists in database
        cursor.execute("SELECT id, card_uid, plate_number, balance FROM rfid_cards WHERE plate_number = ?", (plate,))
        card = cursor.fetchone()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if card:
            # Card exists, update balance
            card_id, existing_uid, plate_number, existing_balance = card
            new_balance = float(balance)
            
            # Update the card record
            cursor.execute("UPDATE rfid_cards SET balance = ?, last_updated = ? WHERE id = ?", 
                           (new_balance, timestamp, card_id))
            
            # Log the transaction
            cursor.execute("""
                INSERT INTO transactions (rfid_card_id, transaction_type, amount, timestamp, description)
                VALUES (?, 'TOP_UP', ?, ?, ?)
            """, (card_id, new_balance - existing_balance, timestamp, f"Balance updated via RFID Manager"))
            
            conn.commit()
            print(f"[DATABASE] Updated card for plate {plate}. New balance: {new_balance} RWF")
            print(f"[DATABASE] Previous balance: {existing_balance} RWF")
        else:
            # New card, insert record
            new_balance = float(balance)
            cursor.execute("""
                INSERT INTO rfid_cards (card_uid, plate_number, balance, created_at, last_updated)
                VALUES (?, ?, ?, ?, ?)
            """, (uid if uid else "UNKNOWN", plate, new_balance, timestamp, timestamp))
            
            card_id = cursor.lastrowid
            
            # Log the transaction
            cursor.execute("""
                INSERT INTO transactions (rfid_card_id, transaction_type, amount, timestamp, description)
                VALUES (?, 'TOP_UP', ?, ?, ?)
            """, (card_id, new_balance, timestamp, "Initial card setup via RFID Manager"))
            
            conn.commit()
            print(f"[DATABASE] Created new card record for plate {plate} with balance {new_balance} RWF")
        
        conn.close()
        return True
    
    except sqlite3.Error as e:
        print(f"[DATABASE ERROR] {e}")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

def write_to_card(port, db_path, sketch_relative_path="writing_on_rfid/writing_on_rfid.ino"):
    """Write plate number and balance data to an RFID card and update database."""
    # Build the absolute path to the sketch
    sketch_path = os.path.join(ARDUINO_SKETCHES_DIR, sketch_relative_path)
    
    print("\n=== Write/Top-Up RFID Card ===")
    print(f"This operation requires the {sketch_relative_path} sketch to be uploaded to the Arduino.")
    
    choice = input("Would you like to upload the required sketch now? (y/n): ")
    if choice.lower() == 'y':
        if not compile_and_upload_sketch(sketch_path, port):
            print("[ERROR] Failed to upload sketch. Please check connections and try again.")
            return
    
    # Prompt for plate number and balance
    plate = input("\nEnter plate number (e.g., RAD123M): ").strip().upper()
    if not plate:
        print("[ERROR] Plate number cannot be empty.")
        return
    
    try:
        balance = float(input("Enter balance amount (RWF): "))
        if balance < 0:
            print("[ERROR] Balance cannot be negative.")
            return
    except ValueError:
        print("[ERROR] Please enter a valid number for balance.")
        return
    
    print("\nConnecting to Arduino...")
    try:
        # Connect to Arduino at 9600 baud (standard for RFID operations)
        arduino = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)  # Give Arduino time to reset
        arduino.reset_input_buffer()
        
        print("\nPlease present an RFID card to write data...")
        print("Press Ctrl+C to cancel.")
        
        # Wait for Arduino to indicate it's ready
        ready = False
        card_uid = None
        
        while not ready:
            if arduino.in_waiting:
                line = arduino.readline().decode('utf-8', errors='ignore').strip()
                print(f"[ARDUINO] {line}")
                
                if "Ready to write" in line or "Present card" in line:
                    ready = True
                elif "Card UID:" in line:
                    card_uid = line.split("Card UID:")[1].strip()
                    print(f"[CARD UID] Detected: {card_uid}")
            
            time.sleep(0.1)
        
        # Send data to Arduino
        data_to_send = f"{plate},{balance}\n"
        print(f"[SENDING] Data to Arduino: {data_to_send.strip()}")
        arduino.write(data_to_send.encode())
        
        # Wait for confirmation
        success = False
        timeout = time.time() + 15  # 15 seconds timeout
        
        while time.time() < timeout and not success:
            if arduino.in_waiting:
                line = arduino.readline().decode('utf-8', errors='ignore').strip()
                print(f"[ARDUINO] {line}")
                
                if "Write successful" in line:
                    success = True
                    
                    # Update database with card information
                    if update_database(plate, balance, card_uid):
                        print("[SUCCESS] Card programmed and database updated successfully!")
                    else:
                        print("[WARNING] Card programmed but database update failed.")
                
                elif "Write failed" in line or "Error" in line:
                    print("[ERROR] Failed to write data to card.")
                    break
            
            time.sleep(0.1)
        
        if not success and time.time() >= timeout:
            print("[ERROR] Timeout waiting for Arduino confirmation.")
        
        arduino.close()
        print("\nArduino connection closed.")
    
    except serial.SerialException as e:
        print(f"[ERROR] Serial connection error: {e}")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        if 'arduino' in locals():
            arduino.close()
            print("Arduino connection closed.")

def check_db_balance(db_path):
    """Check card balance in the database by plate number or card UID."""
    print("\n=== Check Card Balance in Database ===")
    
    # Check if database exists
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        return
    
    search_type = input("Search by (1) Plate Number or (2) Card UID? (1/2): ")
    
    if search_type not in ['1', '2']:
        print("[ERROR] Invalid selection.")
        return
    
    if search_type == '1':
        search_term = input("Enter plate number: ").strip().upper()
        search_column = "plate_number"
    else:
        search_term = input("Enter card UID: ").strip()
        search_column = "card_uid"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        query = f"SELECT id, card_uid, plate_number, balance, last_updated FROM rfid_cards WHERE {search_column} = ?"
        cursor.execute(query, (search_term,))
        cards = cursor.fetchall()
        
        if not cards:
            print(f"[INFO] No cards found for {search_column} = {search_term}")
            return
        
        print("\n=== Database Results ===")
        for card in cards:
            card_id, uid, plate, balance, last_updated = card
            print(f"Card ID: {card_id}")
            print(f"Card UID: {uid}")
            print(f"Plate Number: {plate}")
            print(f"Balance: {balance} RWF")
            print(f"Last Updated: {last_updated}")
            
            # Get transaction history for this card
            cursor.execute("""
                SELECT transaction_type, amount, timestamp, description 
                FROM transactions 
                WHERE rfid_card_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 5
            """, (card_id,))
            transactions = cursor.fetchall()
            
            if transactions:
                print("\nRecent Transactions:")
                for txn in transactions:
                    txn_type, amount, timestamp, description = txn
                    print(f"  {timestamp} | {txn_type} | {amount} RWF | {description}")
            
            print("-" * 50)
        
        conn.close()
    
    except sqlite3.Error as e:
        print(f"[DATABASE ERROR] {e}")
    except Exception as e:
        print(f"[ERROR] {e}")

def main_rfid_manager():
    """Main function for the RFID Manager utility."""
    arduino_port = None
    
    while True:
        clear_screen()
        print("=" * 60)
        print("              RFID MANAGEMENT UTILITY")
        print("=" * 60)
        print(f"Current Arduino Port: {arduino_port or 'Not selected'}")
        print(f"Database Path: {DB_PATH}")
        print("-" * 60)
        print("1. Select Arduino Port")
        print("2. Read Card UID")
        print("3. Read Card Data (Plate & Balance)")
        print("4. Write/Top-up Card")
        print("5. Check Balance from Database")
        print("6. Exit")
        print("-" * 60)
        
        choice = input("Enter your choice (1-6): ")
        
        if choice == '1':
            arduino_port = select_arduino_port()
            if arduino_port:
                print(f"\nSelected Arduino port: {arduino_port}")
                input("Press Enter to continue...")
        
        elif choice == '2':
            if not arduino_port:
                print("\n[ERROR] Please select an Arduino port first (Option 1).")
                input("Press Enter to continue...")
                continue
            
            read_card_uid(arduino_port)
            input("\nPress Enter to return to the main menu...")
        
        elif choice == '3':
            if not arduino_port:
                print("\n[ERROR] Please select an Arduino port first (Option 1).")
                input("Press Enter to continue...")
                continue
            
            read_card_data(arduino_port)
            input("\nPress Enter to return to the main menu...")
        
        elif choice == '4':
            if not arduino_port:
                print("\n[ERROR] Please select an Arduino port first (Option 1).")
                input("Press Enter to continue...")
                continue
            
            write_to_card(arduino_port, DB_PATH)
            input("\nPress Enter to return to the main menu...")
        
        elif choice == '5':
            check_db_balance(DB_PATH)
            input("\nPress Enter to return to the main menu...")
        
        elif choice == '6':
            print("\nExiting RFID Manager. Goodbye!")
            break
        
        else:
            print("\n[ERROR] Invalid choice. Please enter a number between 1 and 6.")
            input("Press Enter to continue...")

if __name__ == "__main__":
    main_rfid_manager()
