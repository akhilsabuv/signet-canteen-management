import pyodbc
from flask import Blueprint, render_template, session, redirect, url_for, current_app, request, flash

devices_bp = Blueprint('devices', __name__, url_prefix='/devices')

def get_devices():
    """Fetch devices from the Main Database's t_dev table."""
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
    
    query = "SELECT DEVID, NM FROM t_dev ORDER BY NM;"
    
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute(query)
        devices = []
        for row in cursor.fetchall():
            devices.append({
                "DEVID": row.DEVID,
                "NM": row.NM
            })
        conn.close()
        return devices
    except Exception as e:
        print("Error retrieving devices:", e)
        return []

def ensure_logger_device_table():
    """
    Ensure that the Logger Database table for device selections (sig_devices) exists.
    If not, create it.
    """
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
    
    create_table_sql = """
        CREATE TABLE sig_devices (
            id INT IDENTITY(1,1) PRIMARY KEY,
            devid VARCHAR(50) NOT NULL,
            nm VARCHAR(255) NOT NULL,
            device_type VARCHAR(50) NOT NULL,
            saved_at DATETIME DEFAULT GETDATE()
        );
    """
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sys.tables WHERE name = 'sig_devices'")
        count = cursor.fetchone()[0]
        if count == 0:
            cursor.execute(create_table_sql)
            conn.commit()
            print("Created table sig_devices in Logger Database.")
        else:
            print("Table sig_devices already exists.")
        conn.close()
    except Exception as e:
        print("Error ensuring logger device table:", e)

def clear_saved_device_selections():
    """Delete all records from sig_devices in the Logger Database."""
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
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sig_devices")
        conn.commit()
        conn.close()
        print("Cleared previous device selections.")
    except Exception as e:
        print("Error clearing saved device selections:", e)

def save_device_selection(entry_ids, canteen_ids, device_map):
    """
    Save selected devices into the Logger Database.
    Each selection is inserted separately.
    """
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
    
    insert_sql = "INSERT INTO sig_devices (devid, nm, device_type) VALUES (?, ?, ?);"
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        print("Saving Entry Devices:", entry_ids)
        for device_id in entry_ids:
            device_name = device_map.get(device_id, "")
            cursor.execute(insert_sql, (device_id, device_name, "entry"))
            print(f"Inserted Entry: {device_id} - {device_name}")
            
        print("Saving Canteen Devices:", canteen_ids)
        for device_id in canteen_ids:
            device_name = device_map.get(device_id, "")
            cursor.execute(insert_sql, (device_id, device_name, "canteen"))
            print(f"Inserted Canteen: {device_id} - {device_name}")
            
        conn.commit()
        conn.close()
        print("Device selection saved successfully.")
    except Exception as e:
        print("Error saving device selection:", e)

def get_saved_device_selections():
    """
    Retrieve saved device selections from the Logger Database.
    Returns a dictionary mapping device IDs (as strings) to a list of device types.
    """
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
    query = "SELECT devid, device_type FROM sig_devices;"
    saved = {}
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute(query)
        for row in cursor.fetchall():
            key = str(row.devid)
            if key in saved:
                saved[key].append(row.device_type)
            else:
                saved[key] = [row.device_type]
        conn.close()
    except Exception as e:
        print("Error retrieving saved device selections:", e)
    print("Saved selections:", saved)
    return saved

@devices_bp.route('/', methods=['GET', 'POST'])
def devices():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    devices = get_devices()
    
    if request.method == 'POST':
        entry_devices = request.form.getlist('entry_devices')
        canteen_devices = request.form.getlist('canteen_devices')
        # Check for conflict: if the same device is selected for both entry and canteen.
        conflict = set(entry_devices) & set(canteen_devices)
        if conflict:
            flash("Conflict: The same device cannot be selected for both Entry and Canteen.", "error")
            return redirect(url_for('devices.devices'))
        
        device_map = {str(d["DEVID"]): d["NM"] for d in devices}
        
        ensure_logger_device_table()
        clear_saved_device_selections()
        save_device_selection(entry_devices, canteen_devices, device_map)
        
        return redirect(url_for('devices.devices'))
    
    saved_selections = get_saved_device_selections()
    return render_template('devices.html', devices=devices, saved=saved_selections)
