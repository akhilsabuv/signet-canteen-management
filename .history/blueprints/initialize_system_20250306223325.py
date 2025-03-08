import os
import csv
import pyodbc
from flask import current_app

def ensure_system_tables():
    """
    Ensure that the system tables exist in LOGGER_DB.
    """
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    
    try:
        # First, check if canteen_timings exists
        # cursor.execute(""" 
        #     IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'canteen_timings')
        #     BEGIN
        #         CREATE TABLE canteen_timings (
        #             id INT IDENTITY(1,1) PRIMARY KEY,
        #             canteen_name VARCHAR(100) NOT NULL,
        #             start_time TIME NOT NULL,
        #             end_time TIME NOT NULL,
        #             description VARCHAR(255)
        #         )
        #     END
        # """)

        # Create shifts table if it doesn't exist
        # cursor.execute("""
        #     IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'shifts')
        #     BEGIN
        #         CREATE TABLE shifts (
        #             id INT IDENTITY(1,1) PRIMARY KEY,
        #             shift_name VARCHAR(50) NOT NULL,
        #             start_time TIME NOT NULL,
        #             end_time TIME NOT NULL
        #         )
        #     END
        # """)

        # Add default shifts if the table is empty
        # cursor.execute("SELECT COUNT(*) FROM shifts")
        # shift_count = cursor.fetchone()[0]
        
        # if shift_count == 0:
        #     cursor.execute("""
        #         INSERT INTO shifts (shift_name, start_time, end_time)
        #         VALUES 
        #         ('Breakfast', '06:00', '10:00'),
        #         ('Lunch', '12:00', '15:00'),
        #         ('Dinner', '18:00', '22:00'),
        #         ('Snacks', '16:00', '18:00')
        #     """)
        #     print("Default shifts added")

        # Drop existing canteen_timing_shifts if it exists
        # cursor.execute("""
        #     IF EXISTS (SELECT * FROM sys.tables WHERE name = 'canteen_timing_shifts')
        #     BEGIN
        #         DROP TABLE canteen_timing_shifts
        #     END
        # """)

        # Create canteen_timing_shifts without foreign key constraints
        # cursor.execute("""
        #     IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'canteen_timing_shifts')
        #     BEGIN
        #     (
        #         CREATE TABLE canteen_timing_shifts (
        #         id INT IDENTITY(1,1) PRIMARY KEY,
        #         timing_id INT NOT NULL,
        #         shift_name VARCHAR(50) NOT NULL
        #         -- Foreign key constraint removed)
        #     )
        #     END
        # """)

        # Create index for better performance
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_CanteenTimingShifts_TimingId')
            BEGIN
                CREATE INDEX IX_CanteenTimingShifts_TimingId 
                ON canteen_timing_shifts(timing_id)
            END
        """)

        conn.commit()
        print("Tables created/updated successfully")
        
    except Exception as e:
        print(f"Error ensuring system tables: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

def get_logger_db_conn():
    config = current_app.config
    host = config.get('LOGGER_DB_HOST')
    username = config.get('LOGGER_DB_USERNAME')
    password = config.get('LOGGER_DB_PASSWORD')
    dbname = config.get('LOGGER_DB_NAME')
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={username};PWD={password}"
    )
    return pyodbc.connect(conn_str, timeout=5)

def load_data_from_csv(table, csv_filename):
    """
    Reads data from a CSV file (located in the static folder) and inserts it into the given table.
    For canteen_timings, maps:
        CSV "Shift" -> canteen_name,
        CSV "StartTime" -> start_time,
        CSV "EndTime" -> end_time,
        and uses description as empty string if not present.
    For shifts, maps:
        CSV "ShiftName" -> shift_name,
        CSV "StartTime" -> start_time,
        CSV "EndTime" -> end_time.
    Rows missing required fields are skipped.
    """
    # Base directory: go up one level then into static folder.
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
    csv_path = os.path.join(base_dir, csv_filename)
    
    if not os.path.exists(csv_path):
        print(f"CSV file not found: {csv_path}")
        return
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    rows_inserted = 0
    try:
        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if table == "canteen_timings":
                    # Map CSV column names to expected column names:
                    # CSV "Shift" will be used as canteen_name,
                    # "StartTime" as start_time, "EndTime" as end_time.
                    canteen_name = row.get('Shift')
                    start_time = row.get('StartTime')
                    end_time = row.get('EndTime')
                    # Optionally, you might get a description column if available; otherwise, default to empty string.
                    description = row.get('description', '')
                    
                    # Validate required fields.
                    if not canteen_name or not start_time or not end_time:
                        print("Skipping row in canteen_timings.csv due to missing required fields:", row)
                        continue
                    
                    insert_sql = """
                        INSERT INTO canteen_timings (canteen_name, start_time, end_time, description)
                        VALUES (?, ?, ?, ?)
                    """
                    cursor.execute(insert_sql, (canteen_name, start_time, end_time, description))
                
                elif table == "shifts":
                    # For shifts CSV, map:
                    # "ShiftName" -> shift_name, "StartTime" -> start_time, "EndTime" -> end_time.
                    shift_name = row.get('ShiftName')
                    start_time = row.get('StartTime')
                    end_time = row.get('EndTime')
                    
                    if not shift_name or not start_time or not end_time:
                        print("Skipping row in shifts.csv due to missing required fields:", row)
                        continue
                    
                    insert_sql = """
                        INSERT INTO shifts (shift_name, start_time, end_time)
                        VALUES (?, ?, ?)
                    """
                    cursor.execute(insert_sql, (shift_name, start_time, end_time))
                rows_inserted += 1
            conn.commit()
            print(f"Inserted {rows_inserted} rows into {table} from {csv_filename}.")
    except Exception as e:
        print(f"Error loading data from {csv_filename} into {table}: {e}")
    finally:
        conn.close()


def initialize_system(app):
    """
    Initialize system tables and load CSV data if tables are empty.
    Call this function within an app context.
    """
    with app.app_context():
        ensure_system_tables()
        
        # Optionally, check if tables are empty before loading data.
        conn = get_logger_db_conn()
        cursor = conn.cursor()
        for table, csv_file in [("canteen_timings", "canteen_timings.csv"), ("shifts", "shifts.csv")]:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                if count == 0:
                    load_data_from_csv(table, csv_file)
                else:
                    print(f"Table {table} already has data ({count} rows).")
            except Exception as e:
                print(f"Error checking table {table}: {e}")
        conn.close()

# Call the function to ensure tables exist
if __name__ == "__main__":
    ensure_system_tables()
