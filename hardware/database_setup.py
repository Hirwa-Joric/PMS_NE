#!/usr/bin/env python3
import sqlite3
import os
import datetime
import argparse

# Import configuration
from config import DB_PATH, HARDWARE_DIR

def create_database(db_path):
    """
    Create a new SQLite database file if it doesn't exist
    Returns the connection to the database
    """
    conn = sqlite3.connect(db_path)
    print(f"Created/connected to database: {db_path}")
    return conn

def create_tables(conn):
    """
    Create the necessary tables for the parking system
    """
    cursor = conn.cursor()
    
    # Create rfid_cards table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rfid_cards (
        card_uid TEXT PRIMARY KEY,
        current_plate TEXT NOT NULL,
        balance INTEGER NOT NULL,
        last_updated TIMESTAMP NOT NULL
    )
    ''')
    
    # Create parking_log table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS parking_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT NOT NULL,
        entry_time TIMESTAMP NOT NULL,
        exit_time TIMESTAMP,
        rfid_uid TEXT,
        amount_due INTEGER,
        payment_status TEXT DEFAULT 'UNPAID',
        FOREIGN KEY(rfid_uid) REFERENCES rfid_cards(card_uid)
    )
    ''')
    
    # Create transactions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rfid_uid TEXT,
        plate_number TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        amount INTEGER NOT NULL,
        transaction_time TIMESTAMP NOT NULL,
        FOREIGN KEY(rfid_uid) REFERENCES rfid_cards(card_uid)
    )
    ''')
    
    conn.commit()
    print("Tables created successfully")

def insert_test_data(conn, include_test_data=False):
    """
    Insert test data into the database (optional)
    """
    if not include_test_data:
        return
    
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    one_hour_ago = (datetime.datetime.now() - datetime.timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    
    # Insert test RFID cards
    test_cards = [
        ('AA11BB22', 'RAG123X', 5000, now),
        ('CC33DD44', 'KGL789Y', 3000, now)
    ]
    cursor.executemany(
        'INSERT OR REPLACE INTO rfid_cards (card_uid, current_plate, balance, last_updated) VALUES (?, ?, ?, ?)',
        test_cards
    )
    
    # Insert test parking entries
    test_entries = [
        ('RAG123X', one_hour_ago, None, 'AA11BB22', None, 'UNPAID'),
        ('KGL789Y', one_hour_ago, None, 'CC33DD44', None, 'UNPAID')
    ]
    cursor.executemany(
        'INSERT INTO parking_log (plate_number, entry_time, exit_time, rfid_uid, amount_due, payment_status) VALUES (?, ?, ?, ?, ?, ?)',
        test_entries
    )
    
    conn.commit()
    print("Test data inserted successfully")

def main():
    parser = argparse.ArgumentParser(description="Initialize the parking system database")
    parser.add_argument('--db_path', type=str, default=DB_PATH,
                        help='Path to the database file')
    parser.add_argument('--include_test_data', action='store_true',
                        help='Include test data in the database')
    args = parser.parse_args()
    
    # Create database directory if it doesn't exist
    db_dir = os.path.dirname(args.db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    
    # Create database and tables
    conn = create_database(args.db_path)
    create_tables(conn)
    
    # Insert test data if requested
    insert_test_data(conn, args.include_test_data)
    
    # Close connection
    conn.close()
    print(f"Database setup complete: {args.db_path}")

if __name__ == "__main__":
    main()
