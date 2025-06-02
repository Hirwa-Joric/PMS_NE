#!/usr/bin/env python3
import os
import sqlite3
from config import DB_PATH

print(f"=== Database Access Test ===")
print(f"Database path: {DB_PATH}")
print(f"Database exists: {os.path.exists(DB_PATH)}")
print(f"Database directory exists: {os.path.exists(os.path.dirname(DB_PATH))}")
print(f"Current working directory: {os.getcwd()}")

try:
    # Test database connection
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables in database: {[table[0] for table in tables]}")
    
    # Get entry count
    cursor.execute("SELECT COUNT(*) FROM parking_log")
    count = cursor.fetchone()[0]
    print(f"Entries in parking_log: {count}")
    
    # Close connection
    conn.close()
    print("✅ Database access successful!")
except Exception as e:
    print(f"❌ Database access failed: {e}")
