#!/usr/bin/env python3
import serial
import time
import sqlite3
import os
from datetime import datetime

# Constants
PLATE_NUMBER = "RAG234H"
BALANCE = "500"
ARDUINO_PORT = "/dev/ttyACM0"
DB_PATH = "parking_system.db"

def main():
    try:
        # Connect to Arduino
        print(f"Connecting to Arduino on {ARDUINO_PORT}...")
        ser = serial.Serial(ARDUINO_PORT, 9600, timeout=1)
        print("✅ Connected to Arduino")
        
        # Wait for Arduino to initialize
        time.sleep(2)
        
        # Read any initial output
        if ser.in_waiting:
            initial = ser.read(ser.in_waiting).decode(errors='ignore')
            print(f"Arduino says: {initial}")
        
        print("\n=== RFID Card Top-Up Process ===")
        print(f"🔹 Plate Number: {PLATE_NUMBER}")
        print(f"🔹 Amount to add: {BALANCE} RWF")
        print("🔹 Please place your RFID card on the reader when prompted")
        
        # Wait loop for card detection and programming
        timeout = time.time() + 120  # 2 minute timeout
        card_detected = False
        plate_sent = False
        balance_sent = False
        write_success = False
        
        while time.time() < timeout:
            # Check for Arduino output
            if ser.in_waiting:
                output = ser.read(ser.in_waiting).decode(errors='ignore')
                print(output, end='')
                
                # Check for key prompts
                if "Card detected" in output and not card_detected:
                    card_detected = True
                    print("\n✅ Card detected!")
                
                if "Enter car plate number" in output and not plate_sent:
                    print(f"\n➡️ Sending plate: {PLATE_NUMBER}#")
                    ser.write(f"{PLATE_NUMBER}#".encode())
                    plate_sent = True
                
                if "Enter balance" in output and not balance_sent:
                    print(f"\n➡️ Sending balance: {BALANCE}#")
                    ser.write(f"{BALANCE}#".encode())
                    balance_sent = True
                
                # Check for success indicators
                if "Car Plate written" in output and "Balance written" in output:
                    write_success = True
                
                # Check for completion
                if "Please remove the card" in output:
                    break
            
            time.sleep(0.1)
        
        # Process results
        if write_success:
            print("\n✅ Card programming successful!")
            
            # Update database if it exists
            if os.path.exists(DB_PATH):
                try:
                    print("\n📊 Updating database...")
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    
                    # Get current time
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Try to find card by plate number
                    cursor.execute('SELECT card_uid, balance FROM rfid_cards WHERE current_plate = ?', (PLATE_NUMBER,))
                    card_result = cursor.fetchone()
                    
                    if card_result:
                        card_uid, current_balance = card_result
                        new_balance = float(current_balance) + float(BALANCE)
                        
                        # Update card balance
                        cursor.execute(
                            'UPDATE rfid_cards SET balance = ?, last_updated = ? WHERE card_uid = ?',
                            (new_balance, now, card_uid)
                        )
                        
                        # Log transaction
                        cursor.execute(
                            'INSERT INTO transactions (rfid_uid, plate_number, transaction_type, amount, transaction_time) VALUES (?, ?, ?, ?, ?)',
                            (card_uid, PLATE_NUMBER, 'TOPUP', BALANCE, now)
                        )
                        
                        print(f"✅ Updated card {card_uid} balance to {new_balance} RWF")
                    else:
                        # Insert new card with unknown UID
                        cursor.execute(
                            'INSERT INTO rfid_cards (card_uid, current_plate, balance, last_updated) VALUES (?, ?, ?, ?)',
                            ('UNKNOWN', PLATE_NUMBER, BALANCE, now)
                        )
                        
                        # Log transaction with unknown UID
                        cursor.execute(
                            'INSERT INTO transactions (rfid_uid, plate_number, transaction_type, amount, transaction_time) VALUES (?, ?, ?, ?, ?)',
                            ('UNKNOWN', PLATE_NUMBER, 'TOPUP', BALANCE, now)
                        )
                        
                        print("✅ Added new card to database with placeholder UID")
                    
                    conn.commit()
                    conn.close()
                    print("✅ Database updated successfully")
                    
                except sqlite3.Error as e:
                    print(f"❌ Database error: {e}")
            else:
                print("⚠️ Database not found. Card programmed but database not updated.")
        else:
            print("\n❌ Card programming may have failed or timed out")
        
        # Close the connection
        ser.close()
        print("\n=== Operation Complete ===")
        
    except serial.SerialException as e:
        print(f"❌ Serial connection error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
