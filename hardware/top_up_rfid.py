#!/usr/bin/env python3
import serial
import time
import argparse
import serial.tools.list_ports
import platform
import re
import sqlite3
import datetime
import os.path

def detect_arduino_port():
    """
    Auto-detect the Arduino port based on common naming patterns
    Returns the port name if found, None otherwise
    """
    ports = list(serial.tools.list_ports.comports())
    
    # Arduino boards typically appear as /dev/ttyACM* on Linux, 
    # /dev/tty.usbmodem* on macOS, COM* on Windows
    arduino_port = None
    os_type = platform.system()
    
    for port in ports:
        if os_type == "Linux" and re.search(r'(ttyACM\d+|ttyUSB\d+)', port.device):
            arduino_port = port.device
            break
        elif os_type == "Darwin" and re.search(r'(usbmodem|tty.usbserial)', port.device):
            arduino_port = port.device
            break
        elif os_type == "Windows" and re.search(r'COM\d+', port.device):
            arduino_port = port.device
            break
    
    return arduino_port

def top_up_card(port, plate, balance, db_path=None, card_uid=None):
    """
    Communicate with Arduino to write plate number and balance to RFID card
    Returns True if successful, False otherwise
    """
    try:
        # Open serial connection
        ser = serial.Serial(port, 9600, timeout=5)
        print(f"Connected to Arduino on {port}")
        time.sleep(2)  # Wait for Arduino to initialize
        
        # Clear any initial buffer
        if ser.in_waiting:
            initial_output = ser.read(ser.in_waiting).decode(errors='ignore')
            print(initial_output)
        
        print("\n🔍 Waiting for card detection and prompts from Arduino...")
        print("💡 Please place your RFID card on the reader when prompted")
        
        # Wait for any output from Arduino and pass through to user
        waiting_for_card = True
        card_detected = False
        waiting_for_plate = False
        waiting_for_balance = False
        success = False
        full_response = ""
        
        timeout = time.time() + 60  # 1 minute timeout
        
        while time.time() < timeout:
            if ser.in_waiting:
                response = ser.read(ser.in_waiting).decode(errors='ignore')
                print(response, end='')
                full_response += response
                
                # Look for key phrases
                if "Card detected" in response:
                    card_detected = True
                    print("\n✅ Card detected! Continuing with programming...")
                
                if "Enter car plate number" in response:
                    waiting_for_plate = True
                    # Arduino is asking for plate number, send it
                    print(f"\n➡️ Sending plate: {plate}#")
                    ser.write(f"{plate}#".encode())
                
                if "Enter balance" in response:
                    waiting_for_balance = True
                    # Arduino is asking for balance, send it
                    print(f"\n➡️ Sending balance: {balance}#")
                    ser.write(f"{str(balance)}#".encode())
                
                # Check for success indicators
                if "Car Plate written" in full_response and "Balance written" in full_response:
                    success = True
                
                if "Please remove the card" in full_response:
                    # End of operation
                    print("\n🔄 Please remove your card from the reader")
                    break
            
            time.sleep(0.1)
        
        # Determine the outcome
        if time.time() >= timeout:
            print("\n⚠️ Operation timed out after 60 seconds")
        
        print("\n--- Card Top-Up Operation Complete ---")
        
        if success:
            print("✅ Top-up successful!")
            if db_path and os.path.exists(db_path):
                update_database(db_path, plate, balance, card_uid, success)
            return True
        else:
            print("❌ Top-up failed.")
            return False

    except serial.SerialException as e:
        print(f"Serial error: {e}")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial port closed.")

def update_database(db_path, plate, balance, card_uid=None, success=False):
    """
    Update the database with the card top-up information
    """
    if not db_path or not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if success:
            # If we have a card_uid, update or insert into rfid_cards
            if card_uid:
                cursor.execute(
                    'INSERT OR REPLACE INTO rfid_cards (card_uid, current_plate, balance, last_updated) VALUES (?, ?, ?, ?)',
                    (card_uid, plate, balance, now)
                )
            else:
                # If we don't have card_uid, try to find by plate number
                cursor.execute('SELECT card_uid FROM rfid_cards WHERE current_plate = ?', (plate,))
                result = cursor.fetchone()
                if result:
                    card_uid = result[0]
                    cursor.execute(
                        'UPDATE rfid_cards SET balance = ?, last_updated = ? WHERE card_uid = ?',
                        (balance, now, card_uid)
                    )
                else:
                    print("Warning: Unable to find card in database by plate number.")
            
            # Log the transaction
            if card_uid:
                cursor.execute(
                    'INSERT INTO transactions (rfid_uid, plate_number, transaction_type, amount, transaction_time) VALUES (?, ?, ?, ?, ?)',
                    (card_uid, plate, 'TOPUP', balance, now)
                )
                print(f"✅ Database updated: Card UID: {card_uid}, Plate: {plate}, Balance: {balance} RWF")
        else:
            print("❌ Card top-up failed, database not updated.")
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Error updating database: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RFID Card Top-Up Utility")
    parser.add_argument("plate", type=str, help="Vehicle plate number (7 characters, e.g., RAG234H)")
    parser.add_argument("balance", type=int, help="Initial balance to load on the card (in RWF)")
    parser.add_argument("--port", type=str, help="Serial port for Arduino (e.g., /dev/ttyACM0 or COM3)")
    parser.add_argument("--db", type=str, default="hardware/parking_system.db", 
                        help="Path to SQLite database (default: hardware/parking_system.db)")
    parser.add_argument("--card_uid", type=str, help="RFID card UID (if known)")
    args = parser.parse_args()

    # Validate plate number (must be exactly 7 characters)
    if len(args.plate) != 7:
        print("Error: Plate number must be exactly 7 characters long.")
        exit(1)
    
    # Auto-detect Arduino port if not specified
    arduino_port = args.port or detect_arduino_port()
    if not arduino_port:
        print("Error: Arduino port not specified and could not be auto-detected.")
        exit(1)
    
    print(f"Attempting top-up on port {arduino_port} for plate {args.plate} with balance {args.balance} RWF")
    print("Waiting for RFID card...")
    
    # Check if database exists
    if not os.path.exists(args.db):
        print(f"Warning: Database file not found at {args.db}")
        create_db = input("Would you like to create the database now? (y/n): ")
        if create_db.lower() == 'y':
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("database_setup", 
                                                           os.path.join(os.path.dirname(args.db), "database_setup.py"))
                db_setup = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(db_setup)
                db_setup.main()
            except Exception as e:
                print(f"Error creating database: {e}")
                print("Continuing without database integration...")
    
    # Perform the top-up
    topup_success = top_up_card(arduino_port, args.plate, args.balance, args.db, args.card_uid)
    
    # Update database
    if topup_success:
        print("Card top-up completed successfully.")
        if os.path.exists(args.db):
            update_database(args.db, args.plate, args.balance, args.card_uid, topup_success)
    else:
        print("Card top-up failed or was incomplete.")
