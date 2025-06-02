#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Flask application for the Parking Management System Dashboard.
This dashboard displays real-time logs of vehicle entries, exits, payments, and system alerts.
"""

import os
import sys
import sqlite3
import datetime
from flask import Flask, render_template, jsonify

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hardware.config import DB_PATH

app = Flask(__name__)

def get_db_connection():
    """Get a connection to the SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn

@app.route('/')
def dashboard():
    """Render the main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/logs')
def get_logs():
    """API endpoint to fetch recent vehicle logs and transactions"""
    try:
        conn = get_db_connection()
        
        # Get recent check-ins (entries without exits)
        check_ins = conn.execute('''
            SELECT plate_number, entry_time 
            FROM parking_log 
            WHERE exit_time IS NULL
            ORDER BY entry_time DESC 
            LIMIT 20
        ''').fetchall()
        
        # Get recent check-outs (completed exits)
        check_outs = conn.execute('''
            SELECT plate_number, entry_time, exit_time, amount_due, payment_status
            FROM parking_log
            WHERE exit_time IS NOT NULL
            ORDER BY exit_time DESC
            LIMIT 20
        ''').fetchall()
        
        # Get recent payment transactions
        payments = conn.execute('''
            SELECT plate_number, transaction_type, amount, transaction_time
            FROM transactions
            WHERE transaction_type IN ('PAYMENT_SUCCESS', 'PAYMENT_FAIL_INSUFFICIENT', 'TOPUP')
            ORDER BY transaction_time DESC
            LIMIT 20
        ''').fetchall()
        
        # Convert data to dictionaries for JSON response
        check_ins_data = [dict(row) for row in check_ins]
        check_outs_data = [dict(row) for row in check_outs]
        payments_data = [dict(row) for row in payments]
        
        conn.close()
        
        # Format timestamps for better readability
        for item in check_ins_data:
            item['entry_time'] = format_timestamp(item['entry_time'])
            
        for item in check_outs_data:
            item['entry_time'] = format_timestamp(item['entry_time'])
            item['exit_time'] = format_timestamp(item['exit_time'])
            
        for item in payments_data:
            item['transaction_time'] = format_timestamp(item['transaction_time'])
        
        return jsonify({
            'check_ins': check_ins_data,
            'check_outs': check_outs_data,
            'payments': payments_data
        })
        
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts')
def get_alerts():
    """API endpoint to fetch system alerts"""
    try:
        conn = get_db_connection()
        
        # Check for unauthorized exit attempts (exit_time present but payment_status is UNPAID)
        unauthorized_exits = conn.execute('''
            SELECT plate_number, exit_time as timestamp
            FROM parking_log
            WHERE exit_time IS NOT NULL AND payment_status = 'UNPAID'
            ORDER BY exit_time DESC
            LIMIT 10
        ''').fetchall()
        
        # Check for failed payments
        failed_payments = conn.execute('''
            SELECT plate_number, transaction_time as timestamp
            FROM transactions
            WHERE transaction_type = 'PAYMENT_FAIL_INSUFFICIENT'
            ORDER BY transaction_time DESC
            LIMIT 10
        ''').fetchall()
        
        conn.close()
        
        # Format the alerts
        alerts = []
        
        for row in unauthorized_exits:
            alerts.append({
                'type': 'UNAUTHORIZED_EXIT',
                'plate_number': row['plate_number'],
                'timestamp': format_timestamp(row['timestamp']),
                'description': 'Vehicle exited without payment'
            })
            
        for row in failed_payments:
            alerts.append({
                'type': 'PAYMENT_FAILURE',
                'plate_number': row['plate_number'],
                'timestamp': format_timestamp(row['timestamp']),
                'description': 'Insufficient funds for payment'
            })
            
        # Sort alerts by timestamp (newest first)
        alerts.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({'alerts': alerts})
        
    except Exception as e:
        print(f"Error fetching alerts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """API endpoint to fetch system statistics"""
    try:
        conn = get_db_connection()
        
        # Count vehicles currently parked (entries without exits)
        current_vehicles = conn.execute('''
            SELECT COUNT(*) as count
            FROM parking_log
            WHERE exit_time IS NULL
        ''').fetchone()['count']
        
        # Calculate total payments today
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        total_payments = conn.execute('''
            SELECT SUM(amount) as total
            FROM transactions
            WHERE transaction_type = 'PAYMENT_SUCCESS'
            AND date(transaction_time) = ?
        ''', (today,)).fetchone()['total'] or 0
        
        # Get total successful transactions today
        transactions_count = conn.execute('''
            SELECT COUNT(*) as count
            FROM transactions
            WHERE date(transaction_time) = ?
        ''', (today,)).fetchone()['count']
        
        conn.close()
        
        return jsonify({
            'current_vehicles': current_vehicles,
            'total_payments_today': total_payments,
            'total_transactions_today': transactions_count,
            # Assuming 50 parking spots total - you can adjust this or make it configurable
            'available_spots': max(0, 50 - current_vehicles)  
        })
        
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return jsonify({'error': str(e)}), 500

def format_timestamp(timestamp):
    """Format a timestamp string to a more readable format"""
    if not timestamp:
        return None
        
    try:
        dt = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        # Return as-is if parsing fails
        return timestamp

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Run the Parking Management Dashboard')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the server on')
    args = parser.parse_args()
    
    app.run(debug=True, port=args.port)
