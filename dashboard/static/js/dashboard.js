/**
 * Dashboard JavaScript for Parking Management System
 * Handles fetching data from API endpoints and updating the dashboard in real-time
 */

// Main data fetching function
async function fetchData() {
    try {
        // Update timestamp
        document.getElementById('last-updated').textContent = 'Last Updated: ' + new Date().toLocaleString();
        
        // Fetch logs (check-ins, check-outs, payments)
        const logsResponse = await fetch('/api/logs');
        if (!logsResponse.ok) {
            throw new Error(`HTTP error ${logsResponse.status}`);
        }
        const logsData = await logsResponse.json();
        
        // Update check-ins table
        updateLogTable('checkin-log-table', logsData.check_ins, [
            { key: 'plate_number', label: 'Plate Number' },
            { key: 'entry_time', label: 'Entry Time' }
        ]);
        
        // Update check-outs table
        updateLogTable('checkout-log-table', logsData.check_outs, [
            { key: 'plate_number', label: 'Plate Number' },
            { key: 'entry_time', label: 'Entry Time' },
            { key: 'exit_time', label: 'Exit Time' },
            { key: 'amount_due', label: 'Amount' },
            { key: 'payment_status', label: 'Status' }
        ]);
        
        // Update payments table
        updateLogTable('payment-log-table', logsData.payments, [
            { key: 'plate_number', label: 'Plate Number' },
            { key: 'transaction_type', label: 'Type' },
            { key: 'amount', label: 'Amount' },
            { key: 'transaction_time', label: 'Time' }
        ]);
        
        // Fetch alerts
        const alertsResponse = await fetch('/api/alerts');
        if (!alertsResponse.ok) {
            throw new Error(`HTTP error ${alertsResponse.status}`);
        }
        const alertsData = await alertsResponse.json();
        
        // Update alerts table
        updateAlertsTable('alert-log-table', alertsData.alerts);
        
        // Fetch statistics
        const statsResponse = await fetch('/api/stats');
        if (!statsResponse.ok) {
            throw new Error(`HTTP error ${statsResponse.status}`);
        }
        const statsData = await statsResponse.json();
        
        // Update statistics
        document.getElementById('current-vehicles').textContent = statsData.current_vehicles;
        document.getElementById('available-spots').textContent = statsData.available_spots;
        document.getElementById('total-payments').textContent = formatCurrency(statsData.total_payments_today);
        document.getElementById('total-transactions').textContent = statsData.total_transactions_today;
        
    } catch (error) {
        console.error('Error fetching data:', error);
    }
}

/**
 * Generic function to update an HTML table with data
 * @param {string} tableId - ID of the table body element
 * @param {Array} dataArray - Array of data objects
 * @param {Array} columns - Array of column definitions with key and label
 */
function updateLogTable(tableId, dataArray, columns) {
    const tableBody = document.getElementById(tableId);
    
    // Clear existing rows
    tableBody.innerHTML = '';
    
    // If no data, show message
    if (!dataArray || dataArray.length === 0) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.setAttribute('colspan', columns.length);
        cell.textContent = 'No data available';
        cell.className = 'text-center';
        row.appendChild(cell);
        tableBody.appendChild(row);
        return;
    }
    
    // Add data rows
    dataArray.forEach(item => {
        const row = document.createElement('tr');
        
        columns.forEach(column => {
            const cell = document.createElement('td');
            let value = item[column.key];
            
            // Format specific values
            if (column.key === 'amount' || column.key === 'amount_due') {
                value = formatCurrency(value);
            } else if (column.key === 'payment_status') {
                // Add colored badge for payment status
                const badge = document.createElement('span');
                badge.textContent = value;
                badge.className = 'badge ' + 
                    (value === 'PAID' ? 'bg-success' : 
                     value === 'UNPAID' ? 'bg-danger' : 'bg-warning');
                cell.appendChild(badge);
                value = null; // We've already set the content
            } else if (column.key === 'transaction_type') {
                // Simplify transaction types for display
                if (value === 'PAYMENT_SUCCESS') value = 'Payment';
                else if (value === 'PAYMENT_FAIL_INSUFFICIENT') value = 'Failed Payment';
                else if (value === 'TOPUP') value = 'Top-up';
            }
            
            if (value !== null) {
                cell.textContent = value || '-';
            }
            
            row.appendChild(cell);
        });
        
        tableBody.appendChild(row);
    });
}

/**
 * Update the alerts table with special formatting for critical alerts
 * @param {string} tableId - ID of the table body element
 * @param {Array} alertsArray - Array of alert objects
 */
function updateAlertsTable(tableId, alertsArray) {
    const tableBody = document.getElementById(tableId);
    
    // Clear existing rows
    tableBody.innerHTML = '';
    
    // If no alerts, show message
    if (!alertsArray || alertsArray.length === 0) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.setAttribute('colspan', '4');
        cell.textContent = 'No alerts at this time';
        cell.className = 'text-center';
        row.appendChild(cell);
        tableBody.appendChild(row);
        return;
    }
    
    // Add alert rows
    alertsArray.forEach(alert => {
        const row = document.createElement('tr');
        
        // Add class for critical alerts
        if (alert.type === 'UNAUTHORIZED_EXIT') {
            row.className = 'table-danger';
        } else if (alert.type === 'PAYMENT_FAILURE') {
            row.className = 'table-warning';
        }
        
        // Create cells for each column
        const typeCell = document.createElement('td');
        const plateCell = document.createElement('td');
        const timeCell = document.createElement('td');
        const descCell = document.createElement('td');
        
        // Create badge for alert type
        const badge = document.createElement('span');
        badge.textContent = alert.type;
        badge.className = 'badge ' + 
            (alert.type === 'UNAUTHORIZED_EXIT' ? 'bg-danger' : 
             alert.type === 'PAYMENT_FAILURE' ? 'bg-warning' : 'bg-secondary');
        typeCell.appendChild(badge);
        
        plateCell.textContent = alert.plate_number || '-';
        timeCell.textContent = alert.timestamp || '-';
        descCell.textContent = alert.description || '-';
        
        // Add cells to row
        row.appendChild(typeCell);
        row.appendChild(plateCell);
        row.appendChild(timeCell);
        row.appendChild(descCell);
        
        // Add row to table
        tableBody.appendChild(row);
    });
}

/**
 * Format a number as currency (RWF)
 * @param {number} amount - Amount to format
 * @returns {string} Formatted amount
 */
function formatCurrency(amount) {
    if (amount === null || amount === undefined) return '-';
    return amount.toLocaleString() + ' RWF';
}

// Initial data fetch
document.addEventListener('DOMContentLoaded', () => {
    fetchData();
    
    // Set up periodic refresh (every 5 seconds)
    setInterval(fetchData, 5000);
});
