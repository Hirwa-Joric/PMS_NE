import csv
import os

csv_file = 'db.csv'

def mark_payment_success(plate_number):
    if not os.path.exists(csv_file):
        print("[ERROR] Log file does not exist.")
        return

    updated = False
    rows = []

    # Read existing data
    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            # Match the plate with unpaid status
            if row[0] == plate_number and row[1] == '0':
                row[1] = '1'  # Mark as paid
                updated = True
            rows.append(row)

    if updated:
        # Write back updated data
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        print(f"[UPDATED] Payment status set to 1 for {plate_number}")
    else:
        print(f"[INFO] No unpaid record found for {plate_number}")

# ==== TESTING USAGE ====
if __name__ == "__main__":
    plate = input("Enter plate number to mark as paid: ").strip().upper()
    mark_payment_success(plate)