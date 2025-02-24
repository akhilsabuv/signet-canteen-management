import pyodbc
from flask import Blueprint, jsonify, current_app, session, redirect, url_for
import time

monitored_tables_bp = Blueprint('monitored_tables', __name__, url_prefix='/dashboard')

# Global variable to store previous row counts for monitored tables
previous_monitored_counts = {}

def get_main_db_monitored_tables():
    """
    Queries the Main Database for tables whose names match TABLE_PREFIX followed by exactly six digits.
    Returns a list of dictionaries with table_name and row_count.
    """
    config = current_app.config
    host = config.get('MAIN_DB_HOST')
    username = config.get('MAIN_DB_USERNAME')
    password = config.get('MAIN_DB_PASSWORD')
    dbname = config.get('MAIN_DB_NAME')
    table_prefix = config.get('TABLE_PREFIX', 't_lg')
    
    # Build connection string for Main DB (omit port if not needed)
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={username};PWD={password}"
    )
    
    # Build SQL pattern: TABLE_PREFIX followed by exactly six digits.
    pattern = table_prefix + "[0-9][0-9][0-9][0-9][0-9][0-9]"
    
    query = """
        SELECT t.name AS table_name, SUM(p.rows) AS row_count
        FROM sys.tables t
        INNER JOIN sys.partitions p ON t.object_id = p.object_id
        WHERE t.name LIKE ? AND p.index_id < 2
        GROUP BY t.name
        ORDER BY t.name;
    """
    
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute(query, (pattern,))
        results = []
        for row in cursor.fetchall():
            results.append({
                "table_name": row.table_name,
                "row_count": row.row_count
            })
        conn.close()
        return results
    except Exception as e:
        print("Error retrieving monitored tables from Main DB:", e)
        return []

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

def ensure_monitored_counts_table():
    """
    Ensure that the monitored_table_counts table exists in LOGGER_DB.
    This table will store the monitored table name, row count, and timestamp.
    """
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    create_table_sql = """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'monitored_table_counts')
    BEGIN
        CREATE TABLE monitored_table_counts (
            id INT IDENTITY(1,1) PRIMARY KEY,
            table_name VARCHAR(100) NOT NULL,
            row_count BIGINT NOT NULL,
            updated_at DATETIME DEFAULT GETDATE()
        );
    END
    """
    try:
        cursor.execute(create_table_sql)
        conn.commit()
        # print("Ensured table monitored_table_counts exists in LOGGER_DB.")
    except Exception as e:
        print("Error ensuring monitored_table_counts table:", e)
    finally:
        conn.close()

def row_count_change(table_name, previous_count, new_count):
    """
    Triggered when the row count for a monitored table changes.
    Prints the change, retrieves the latest event details (DEVDT, DEVUID, USRID),
    and if the event's DEVUID is registered as a canteen device in LOGGER_DB,
    calls check_elegibility(). Otherwise, it does nothing extra.
    """
    message = f"Row count changed for {table_name}: from {previous_count} to {new_count}"
    print(message)
    
    config = current_app.config
    host = config.get('MAIN_DB_HOST')
    username = config.get('MAIN_DB_USERNAME')
    password = config.get('MAIN_DB_PASSWORD')
    dbname = config.get('MAIN_DB_NAME')
    
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={username};PWD={password}"
    )
    
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        # Retrieve the latest event details from the monitored table (ordered by SRVDT descending)
        query = f"SELECT TOP 1 DEVDT, DEVUID, USRID FROM {table_name} ORDER BY SRVDT DESC"
        cursor.execute(query)
        row = cursor.fetchone()
        if row:
            print(f"Latest event details in {table_name}: DEVDT = {row.DEVDT}, DEVUID = {row.DEVUID}, USRID = {row.USRID}")
            # Retrieve dynamic list of canteen device IDs from LOGGER_DB
            canteen_ids = get_canteen_device_ids()
            if str(row.DEVUID) in canteen_ids:
                check_elegibility(table_name, row.DEVDT, row.DEVUID, row.USRID)
            else:
                print(str(row.DEVUID))
                print(canteen_ids)
                print("Device not registered as canteen; eligibility check not triggered.")
        else:
            print(f"No event details found in {table_name}.")
        conn.close()
    except Exception as e:
        print(f"Error retrieving event details from {table_name}: {e}")

def update_monitored_table_counts():
    """
    Retrieves monitored table row counts from the Main DB and saves them to the LOGGER_DB.
    Clears the monitored_table_counts table first, then inserts fresh data.
    If any table's row count has changed compared to the previous snapshot,
    the function row_count_change() is called.
    """
    global previous_monitored_counts
    monitored_tables = get_main_db_monitored_tables()
    if not monitored_tables:
        print("No monitored tables data retrieved.")
        return {"error": "No data retrieved"}
    
    # Check for row count changes.
    for entry in monitored_tables:
        table_name = entry["table_name"]
        new_count = entry["row_count"]
        previous_count = previous_monitored_counts.get(table_name)
        if previous_count is None or previous_count != new_count:
            row_count_change(table_name, previous_count, new_count)
    # Update the snapshot.
    previous_monitored_counts = {entry["table_name"]: entry["row_count"] for entry in monitored_tables}
    
    # Ensure the LOGGER_DB table exists.
    ensure_monitored_counts_table()
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM monitored_table_counts")
        insert_sql = """
            INSERT INTO monitored_table_counts (table_name, row_count)
            VALUES (?, ?)
        """
        for entry in monitored_tables:
            cursor.execute(insert_sql, (entry["table_name"], entry["row_count"]))
        conn.commit()
        # print("Updated monitored_table_counts in LOGGER_DB.")
        return {"status": "success", "data": monitored_tables}
    except Exception as e:
        print("Error updating monitored_table_counts:", e)
        return {"error": str(e)}
    finally:
        conn.close()

@monitored_tables_bp.route('/monitored-tables', methods=['GET'])
def get_monitored_tables_route():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    monitored = get_main_db_monitored_tables()
    return jsonify(monitored)

@monitored_tables_bp.route('/update_monitored_counts', methods=['GET'])
def update_monitored_counts_route():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    result = update_monitored_table_counts()
    return jsonify(result)


def check_elegibility(table_name, devdt, devuid, usrid):
    """
    This function is triggered when an event is detected from a canteen device table.
    """
    message = (
        f"Checking eligibility for canteen device event:\n"
        f"Table: {table_name}\n"
        f"DEVDT: {devdt}\n"
        f"DEVUID: {devuid}\n"
        f"USRID: {usrid}"
    )
    print(message)


def get_canteen_device_ids():
    """
    Retrieve all DEVID values from the LOGGER_DB sig_devices table
    where device_type is 'canteen'. Returns a set of DEVUID values as strings.
    """
    device_ids = set()
    try:
        conn = get_logger_db_conn()  # Ensure this returns a valid connection to LOGGER_DB.
        cursor = conn.cursor()
        query = "SELECT devid FROM sig_devices WHERE device_type = 'canteen'"
        cursor.execute(query)
        for row in cursor.fetchall():
            device_ids.add(str(row.devid))
        conn.close()
    except Exception as e:
        print("Error retrieving canteen device IDs:", e)
    return device_ids

def get_entry_device_ids():
    """
    Retrieve all devid values from the LOGGER_DB sig_devices table
    where device_type is 'entry'. Returns a set of devid values as strings.
    """
    device_ids = set()
    try:
        conn = get_logger_db_conn()  # Assumes get_logger_db_conn() returns a valid connection to LOGGER_DB.
        cursor = conn.cursor()
        query = "SELECT devid FROM sig_devices WHERE device_type = 'entry'"
        cursor.execute(query)
        for row in cursor.fetchall():
            device_ids.add(str(row.devid))
        conn.close()
    except Exception as e:
        print("Error retrieving entry device IDs:", e)
    return device_ids
