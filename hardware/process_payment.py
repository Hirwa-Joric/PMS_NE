import serial
import time
import serial.tools.list_ports
import platform
import sqlite3
import os.path
from datetime import datetime

# Import configuration from config.py
from config import DB_PATH, PAYMENT_RATE_PER_HOUR

# Configuration
RATE_PER_HOUR = PAYMENT_RATE_PER_HOUR  # 500 RWF per hour from config
RATE_PER_MINUTE = round(RATE_PER_HOUR / 60, 2)  # Approx 8.33 RWF per minute


def detect_arduino_port():
    ports = list(serial.tools.list_ports.comports())
    system = platform.system()
    for port in ports:
        if system == "Linux":
            if "ttyUSB" in port.device or "ttyACM" in port.device:
                return port.device
        elif system == "Darwin":
            if "usbmodem" in port.device or "usbserial" in port.device:
                return port.device
        elif system == "Windows":
            if "COM" in port.device:
                return port.device
    return None


def parse_arduino_data(line):
    try:
        parts = line.strip().split(',')
        print(f"[ARDUINO] Parsed parts: {parts}")
        if len(parts) != 2:
            return None, None
        plate = parts[0].strip()

        # Clean the balance string by removing non-digit characters
        balance_str = ''.join(c for c in parts[1] if c.isdigit())
        print(f"[ARDUINO] Cleaned balance: {balance_str}")

        if balance_str:
            balance = int(balance_str)
            return plate, balance
        else:
            return None, None
    except ValueError as e:
        print(f"[ERROR] Value error in parsing: {e}")
        return None, None


def process_payment(plate, balance, ser, db_path=DB_PATH):
    """
    Process a payment for a vehicle exit using RFID card
    
    Args:
        plate (str): The license plate number from the RFID card
        balance (int): The current balance on the RFID card
        ser (serial.Serial): Serial connection to the Arduino
        db_path (str, optional): Path to SQLite database
        
    Returns:
        dict: Result with success status and info about the transaction
    """
    result = {
        'success': False,
        'message': '',
        'plate': plate,
        'amount_paid': 0,
        'new_balance': balance,
        'rfid_uid': None
    }
    
    # Check if database exists
    if not os.path.exists(db_path):
        result['message'] = f"Database not found at {db_path}"
        print(f"[ERROR] {result['message']}")
        return result
        
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Find unpaid parking session for this plate
        cursor.execute("""
            SELECT log_id, plate_number, entry_time, rfid_uid 
            FROM parking_log 
            WHERE plate_number = ? AND payment_status = 'UNPAID' 
            ORDER BY entry_time DESC LIMIT 1
        """, (plate,))
        
        unpaid_session = cursor.fetchone()
        
        if not unpaid_session:
            result['message'] = "No unpaid parking session found for this plate"
            print(f"[PAYMENT] {result['message']}")
            conn.close()
            return result
            
        log_id, db_plate, entry_time_str, rfid_uid = unpaid_session
        result['rfid_uid'] = rfid_uid
        
        # Calculate time spent and amount due
        entry_time = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')
        exit_time = datetime.now()
        minutes_spent = int((exit_time - entry_time).total_seconds() / 60) + 1
        amount_due = round(minutes_spent * RATE_PER_MINUTE)
        
        print(f"[PAYMENT] Time spent: {minutes_spent} minutes, Amount due: {amount_due} RWF")
        
        # Check if card has sufficient balance
        if balance < amount_due:
            result['message'] = f"Insufficient balance. Required: {amount_due} RWF, Available: {balance} RWF"
            print(f"[PAYMENT] {result['message']}")
            ser.write(b'I\n')
            
            # Log failed payment attempt in transactions
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                INSERT INTO transactions (rfid_uid, plate_number, transaction_type, amount, transaction_time) 
                VALUES (?, ?, ?, ?, ?)
            """, (rfid_uid, plate, 'PAYMENT_FAIL_INSUFFICIENT', amount_due, now))
            conn.commit()
            conn.close()
            return result
        
        # Calculate new balance
        new_balance = balance - amount_due
        result['amount_paid'] = amount_due
        result['new_balance'] = new_balance
        
        # Wait for Arduino to send "READY"
        print("[WAIT] Waiting for Arduino to be READY...")
        start_time = time.time()
        while True:
            if ser.in_waiting:
                arduino_response = ser.readline().decode().strip()
                print(f"[ARDUINO] {arduino_response}")
                if arduino_response == "READY":
                    break
            if time.time() - start_time > 5:
                result['message'] = "Timeout waiting for Arduino READY signal"
                print(f"[ERROR] {result['message']}")
                conn.close()
                return result
        
        # Send new balance to Arduino
        ser.write(f"{new_balance}\r\n".encode())
        print(f"[PAYMENT] Sent new balance {new_balance} RWF")
        
        # Wait for confirmation with timeout
        start_time = time.time()
        print("[WAIT] Waiting for Arduino confirmation...")
        payment_success = False
        
        while True:
            if ser.in_waiting:
                confirm = ser.readline().decode().strip()
                print(f"[ARDUINO] {confirm}")
                if "DONE" in confirm:
                    print("[ARDUINO] Write confirmed")
                    payment_success = True
                    break
            
            # Add timeout condition
            if time.time() - start_time > 10:
                result['message'] = "Timeout waiting for Arduino confirmation"
                print(f"[ERROR] {result['message']}")
                conn.close()
                return result
            
            # Small delay to avoid CPU spinning
            time.sleep(0.1)
        
        if payment_success:
            # Update database
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Update parking_log
            cursor.execute("""
                UPDATE parking_log 
                SET exit_time = ?, amount_due = ?, payment_status = 'PAID' 
                WHERE log_id = ?
            """, (now, amount_due, log_id))
            
            # Update rfid_cards if we have the card_uid
            if rfid_uid:
                cursor.execute("""
                    UPDATE rfid_cards 
                    SET balance = ?, last_updated = ? 
                    WHERE card_uid = ?
                """, (new_balance, now, rfid_uid))
            
            # Insert transaction record
            cursor.execute("""
                INSERT INTO transactions (rfid_uid, plate_number, transaction_type, amount, transaction_time) 
                VALUES (?, ?, ?, ?, ?)
            """, (rfid_uid, plate, 'PAYMENT_SUCCESS', amount_due, now))
            
            conn.commit()
            result['success'] = True
            result['message'] = f"Payment of {amount_due} RWF successful. New balance: {new_balance} RWF"
            print(f"[PAYMENT] {result['message']}")
        
        conn.close()
        return result

    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def main():
    port = detect_arduino_port()
    if not port:
        print("[ERROR] Arduino not found")
        return

    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"[WARNING] Database not found at {DB_PATH}")
        create_db = input("Would you like to create the database now? (y/n): ")
        if create_db.lower() == 'y':
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("database_setup", 
                                                           os.path.join(os.path.dirname(DB_PATH), "database_setup.py"))
                db_setup = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(db_setup)
                db_setup.main()
                print(f"[INFO] Created database at {DB_PATH}")
            except Exception as e:
                print(f"[ERROR] Failed to create database: {e}")

    try:
        ser = serial.Serial(port, 9600, timeout=1)
        print(f"[CONNECTED] Listening on {port}")
        time.sleep(2)

        # Flush any previous data
        ser.reset_input_buffer()

        print("[INFO] Waiting for RFID card data...")
        print(f"[INFO] Payment rate: {RATE_PER_HOUR} RWF/hour ({RATE_PER_MINUTE} RWF/minute)")

        while True:
            if ser.in_waiting:
                line = ser.readline().decode().strip()
                print(f"[SERIAL] Received: {line}")
                plate, balance = parse_arduino_data(line)
                if plate and balance is not None:
                    result = process_payment(plate, balance, ser, DB_PATH)
                    if result['success']:
                        print(f"[SUCCESS] Payment processed for plate {plate}")
                    else:
                        print(f"[FAILED] Payment failed: {result['message']}")

    except KeyboardInterrupt:
        print("[EXIT] Program terminated")
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        if 'ser' in locals():
            ser.close()


if __name__ == "__main__":
    main()