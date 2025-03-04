import time
import pyodbc
from flask import Blueprint, render_template, session, redirect, url_for, current_app, jsonify

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

# Simple in-memory cache to avoid repeated DB connections
CACHE_DURATION = 30  # seconds
cached_status = {
    "timestamp": 0,
    "logger_tables": None,
    "main_db_status": None
}

def check_logger_db_uncached():
    """
    Connect to the Logger DB using MSSQL configuration values from Flask's config.
    For each expected table (sig_users, sig_transactions, sig_logs, sig_udevice),
    check if it exists; if not, create the table using a sample schema.
    Returns a list of dictionaries with the display name and a status (True if exists).
    """
    config = current_app.config
    host = config.get('LOGGER_DB_HOST')
    port = config.get('LOGGER_DB_PORT')  # Not used if default port
    username = config.get('LOGGER_DB_USERNAME')
    password = config.get('LOGGER_DB_PASSWORD')
    dbname = config.get('LOGGER_DB_NAME')
    
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"  # Omit port if using default
        f"DATABASE={dbname};"
        f"UID={username};PWD={password}"
    )
    
    # Define the tables and their sample CREATE TABLE statements
    tables_to_check = {
        "Users Table": {
            "table_name": "sig_users",
            "create_sql": """
                CREATE TABLE sig_users (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at DATETIME DEFAULT GETDATE()
                );
            """
        },
        "Transactions Table": {
            "table_name": "sig_transactions",
            "create_sql": """
                CREATE TABLE sig_transactions (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    usrid INT NOT NULL,
                    event_dt DATETIME NOT NULL,
                    event_time TIME NOT NULL,
                    latest_entry DATETIME NOT NULL,
                    shift_start_time TIME NOT NULL,
                    status TINYINT NOT NULL CHECK (status IN (0, 1, 2)),
                    description NVARCHAR(255) NULL
                );
            """
        },
        "Logs Table": {
            "table_name": "sig_logs",
            "create_sql": """
                CREATE TABLE sig_logs (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    log_message VARCHAR(255),
                    log_date DATETIME DEFAULT GETDATE()
                );
            """
        },
        "Device Table": {
            "table_name": "sig_devices",
            "create_sql": """
                CREATE TABLE sig_devices (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    devid VARCHAR(50) NOT NULL,
                    nm VARCHAR(255) NOT NULL,
                    device_type VARCHAR(50) NOT NULL,
                    saved_at DATETIME DEFAULT GETDATE()
                );
            """
        }
    }
    
    results = []
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        for display_name, table_info in tables_to_check.items():
            table_name = table_info["table_name"]
            # Check if the table exists
            cursor.execute("SELECT COUNT(*) FROM sys.tables WHERE name = ?", table_name)
            count = cursor.fetchone()[0]
            if count == 0:
                # Table does not exist; create it
                try:
                    cursor.execute(table_info["create_sql"])
                    conn.commit()
                    print(f"Created table: {table_name}")
                    count = 1  # Mark as existing now
                except Exception as ce:
                    print(f"Error creating table {table_name}: {ce}")
                    count = 0
            results.append({"name": display_name, "status": count > 0})
        conn.close()
    except Exception as e:
        print("Logger DB connection error:", e)
        results = [{"name": k, "status": False} for k in tables_to_check.keys()]
    return results


def check_main_db_uncached():
    """
    Connects to the Main DB using MSSQL configuration values and executes a simple query.
    Returns True if connection and query succeed; otherwise, returns False.
    """
    config = current_app.config
    host = config.get('MAIN_DB_HOST')
    port = config.get('MAIN_DB_PORT')
    username = config.get('MAIN_DB_USERNAME')
    password = config.get('MAIN_DB_PASSWORD')
    dbname = config.get('MAIN_DB_NAME')
    
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host},{port};"
        f"DATABASE={dbname};"
        f"UID={username};PWD={password}"
    )
    try:
        conn = pyodbc.connect(conn_str, timeout=3)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        return True
    except Exception as e:
        print("Main DB connection error:", e)
        return False

def get_status():
    """
    Returns cached status if it is still fresh; otherwise, refreshes the status by 
    checking the databases and caches the results.
    """
    global cached_status
    current_time = time.time()
    if current_time - cached_status["timestamp"] < CACHE_DURATION:
        return cached_status["logger_tables"], cached_status["main_db_status"]
    
    logger_tables = check_logger_db_uncached()
    main_db_status = check_main_db_uncached()
    cached_status["logger_tables"] = logger_tables
    cached_status["main_db_status"] = main_db_status
    cached_status["timestamp"] = current_time
    return logger_tables, main_db_status

@dashboard_bp.route('/')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    logger_tables, main_db_status = get_status()
    return render_template('dashboard.html',
                           logger_tables=logger_tables,
                           main_db_status=main_db_status)

@dashboard_bp.route('/status')
def dashboard_status():
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 403
    logger_tables, main_db_status = get_status()
    return jsonify({
        'logger_tables': logger_tables,
        'main_db_status': main_db_status
    })
