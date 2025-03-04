import re
import datetime
import pytz
import pyodbc
from flask import Blueprint, jsonify, current_app, session, redirect, url_for
import win32print

monitored_tables_bp = Blueprint('monitored_tables', __name__, url_prefix='/dashboard')

# Global variable to store previous row counts for monitored tables
previous_monitored_counts = {}

###############################################
# MAIN_DB Monitored Tables Query
###############################################
def get_main_db_monitored_tables():
    """
    Queries the MAIN_DB for tables whose names match TABLE_PREFIX followed by exactly six digits.
    Returns a list of dictionaries with table_name and row_count.
    """
    config = current_app.config
    host = config.get('MAIN_DB_HOST')
    username = config.get('MAIN_DB_USERNAME')
    password = config.get('MAIN_DB_PASSWORD')
    dbname = config.get('MAIN_DB_NAME')
    table_prefix = config.get('TABLE_PREFIX', 't_lg')
    
    # Build connection string for MAIN_DB (omit port if not needed)
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
        print("Error retrieving monitored tables from MAIN_DB:", e)
        return []

###############################################
# LOGGER_DB Connection Helper
###############################################
def get_logger_db_conn():
    """
    Returns a pyodbc connection to LOGGER_DB using current_app.config values.
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
    return pyodbc.connect(conn_str, timeout=5)

###############################################
# Device Registration Helpers
###############################################
def get_canteen_device_ids():
    """
    Retrieve all 'devid' values from LOGGER_DB's sig_devices table where device_type = 'canteen'.
    Returns a set of devid values as strings.
    """
    device_ids = set()
    try:
        conn = get_logger_db_conn()
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
    Retrieve all 'devid' values from LOGGER_DB's sig_devices table where device_type = 'entry'.
    Returns a set of devid values as strings.
    """
    device_ids = set()
    try:
        conn = get_logger_db_conn()
        cursor = conn.cursor()
        query = "SELECT devid FROM sig_devices WHERE device_type = 'entry'"
        cursor.execute(query)
        for row in cursor.fetchall():
            device_ids.add(str(row.devid))
        conn.close()
    except Exception as e:
        print("Error retrieving entry device IDs:", e)
    return device_ids

###############################################
# Candidate Generation Helper
###############################################
def get_closest_candidate(event_local, shift_time, tz, delta_range=(-1, 0, 1)):
    """
    Given an event's local datetime (event_local) and a shift start time (a TIME object),
    generate candidate datetimes by combining shift_time with event_local's date offset by each delta in delta_range.
    Returns the candidate datetime that minimizes the absolute difference from event_local.
    """
    candidates = []
    for delta in delta_range:
        candidate_date = event_local.date() + datetime.timedelta(days=delta)
        candidate_naive = datetime.datetime.combine(candidate_date, shift_time)
        candidate_dt = tz.localize(candidate_naive)
        candidates.append(candidate_dt)
    best = min(candidates, key=lambda d: abs((event_local - d).total_seconds()))
    return best

###############################################
# Latest Attendance Event Retrieval
###############################################
def get_latest_entry_event_time(usrid):
    """
    Retrieves the latest attendance event time (SRVDT) for the given user (USRID)
    by searching all MAIN_DB tables whose name matches TABLE_PREFIX + 6 digits,
    and where DEVUID is in the entry device list.
    
    Returns a timezone-aware datetime in the configured TIME_ZONE, or None if no event is found.
    """
    config = current_app.config
    table_prefix = config.get('TABLE_PREFIX', 't_lg')
    main_host = config.get('MAIN_DB_HOST')
    main_username = config.get('MAIN_DB_USERNAME')
    main_password = config.get('MAIN_DB_PASSWORD')
    main_dbname = config.get('MAIN_DB_NAME')
    
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={main_host};"
        f"DATABASE={main_dbname};"
        f"UID={main_username};PWD={main_password}"
    )
    
    table_regex = re.compile(f"^{re.escape(table_prefix)}\\d{{6}}$")
    latest_event = None
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sys.tables WHERE name LIKE ?", (table_prefix + '%',))
        tables = [row.name for row in cursor.fetchall() if table_regex.match(row.name)]
        
        entry_ids = get_entry_device_ids()
        if not entry_ids:
            print("No entry device IDs found.")
            conn.close()
            return None
        
        in_clause = ",".join("?" for _ in entry_ids)
        
        for table in tables:
            query = f"""
                SELECT TOP 1 SRVDT 
                FROM {table}
                WHERE USRID = ? AND CAST(DEVUID AS VARCHAR(50)) IN ({in_clause})
                ORDER BY SRVDT DESC
            """
            params = [usrid] + list(entry_ids)
            try:
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row:
                    event_time = row.SRVDT
                    if event_time.tzinfo is None:
                        event_time = pytz.utc.localize(event_time)
                    if (latest_event is None) or (event_time > latest_event):
                        latest_event = event_time
            except Exception as ex:
                print(f"Error querying table {table}: {ex}")
                continue
        conn.close()
        
        if latest_event:
            tz_config = pytz.timezone(config.get("TIME_ZONE", "UTC"))
            latest_event = latest_event.astimezone(tz_config)
        return latest_event
    except Exception as e:
        print("Error retrieving latest entry event time:", e)
        return None

###############################################
# Canteen Eligibility Checker
###############################################
def check_elegibility(event_dt, devuid, usrid):
    """
    Dynamic meal time eligibility checker that adapts to any changes in canteen_timings table
    """
    print(f"Checking canteen timing eligibility for event: DEVUID={devuid}, USRID={usrid}, Event Time={event_dt}")
    config = current_app.config
    tz = pytz.timezone(config.get("TIME_ZONE", "UTC"))
    event_local = event_dt.astimezone(tz)
    print(f"Event local time for eligibility: {event_local}")
    
    eligible = False
    trigger = None
    
    try:
        conn = get_logger_db_conn()
        cursor = conn.cursor()
        
        # Always gets fresh timing data from database
        # If meal times are changed in database, this will automatically use new timings
        cursor.execute("""
            SELECT 
                canteen_name,
                start_time,
                end_time,
                created_at
            FROM canteen_timings 
            WHERE start_time <= CAST(GETDATE() AS TIME)
            AND end_time >= CAST(GETDATE() AS TIME)
            ORDER BY start_time
        """)
        
        event_time = event_local.time()
        
        for row in cursor.fetchall():
            start_time = row.start_time
            end_time = row.end_time
            
            print(f"Checking {row.canteen_name}: {start_time} - {end_time}")
            print(f"Current event time: {event_time}")
            
            # Dynamic time window check
            if start_time <= event_time <= end_time:
                eligible = True
                trigger = (f"Canteen: {row.canteen_name} "
                         f"({start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')})")
                print(f"Match found: {trigger}")
                break
        
        conn.close()
        
    except Exception as e:
        print("Error checking canteen eligibility:", e)
        return False
    
    if eligible:
        print(f"Timing eligibility met based on {trigger}")
    else:
        print("No eligible timing found")
    
    return eligible

###############################################
# Row Count Change & Overall Eligibility Check
###############################################
def row_count_change(table_name, previous_count, new_count):

    config = current_app.config
    host = config.get("MAIN_DB_HOST")
    username = config.get("MAIN_DB_USERNAME")
    password = config.get("MAIN_DB_PASSWORD")
    dbname = config.get("MAIN_DB_NAME")
    tz = pytz.timezone(config.get("TIME_ZONE", "UTC"))
    
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={username};PWD={password}"
    )
    
    try:
        print(f"Row count changed for {table_name}: from {previous_count} to {new_count}")
    #     conn = pyodbc.connect(conn_str, timeout=5)
    #     cursor = conn.cursor()
    #     query = f"SELECT TOP 1 DEVDT, DEVUID, USRID FROM {table_name} ORDER BY SRVDT DESC"
    #     cursor.execute(query)
    #     row = cursor.fetchone()
    #     if row:
    #         # Convert DEVDT if it's a Unix timestamp.
    #         event_dt = row.DEVDT
    #         if isinstance(event_dt, (int, float)):
    #             event_dt = datetime.datetime.fromtimestamp(event_dt, tz=pytz.utc)
    #         print(f"Latest event in {table_name}: DEVDT={event_dt}, DEVUID={row.DEVUID}, USRID={row.USRID}")
    #         event_devid = str(row.DEVUID)
    #         event_local = event_dt.astimezone(tz)
    #         print(f"Event local time: {event_local}")
            
    #         # Retrieve dynamic device lists.
    #         canteen_ids = get_canteen_device_ids()
    #         entry_ids = get_entry_device_ids()
            
    #         if event_devid in canteen_ids:
    #             print("Device is registered as a canteen device. Checking canteen eligibility...")
    #             if not check_elegibility(event_dt, row.DEVUID, row.USRID):
    #                 print("Canteen timing conditions not met; not eligible.")
    #                 return False
    #             else:
    #                 print("Canteen timing conditions met.")
    #                 latest_entry = get_latest_entry_event_time(row.USRID)
    #                 if latest_entry is None:
    #                     print("No attendance event found; not eligible.")
    #                     return False
    #                 shift_start_str = config.get("SHIFT_START_TIME", "01:00")
    #                 attendance_buffer = config.get("ATTENDANCE_BUFFER_MINUTES", 60)
    #                 try:
    #                     shift_start_time = datetime.datetime.strptime(shift_start_str, "%H:%M").time()
    #                 except Exception as e:
    #                     print("Error parsing SHIFT_START_TIME:", e)
    #                     return False
    #                 allowed_deadline = datetime.datetime.combine(event_local.date(), shift_start_time) + datetime.timedelta(minutes=attendance_buffer)
    #                 allowed_deadline = tz.localize(allowed_deadline)
    #                 print(f"Allowed attendance deadline: {allowed_deadline}")
    #                 print(f"Latest attendance event: {latest_entry}")
                    
    #                 if latest_entry <= allowed_deadline:
    #                     print("Attendance event is within allowed buffer; eligible for canteen service.")
    #                     return True
    #                 else:
    #                     print("Attendance event is too late; not eligible.")
    #                     return False
    #         elif event_devid in entry_ids:
    #             print("Device is registered as an entry device; automatically eligible.")
    #             return True
    #         else:
    #             print("Device not registered as canteen or entry; automatically eligible.")
    #             return True
    #     else:
    #         print(f"No event details found in {table_name}.")
    #         return False
    #     conn.close()
    except Exception as e:
        print(f"Error retrieving event details from {table_name}: {e}")
        return False

###############################################
# Monitored Counts Table Update
###############################################
def ensure_monitored_counts_table():
    """
    Ensure that the monitored_table_counts table exists in LOGGER_DB.
    This table stores the monitored table name, row count, and timestamp.
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
    except Exception as e:
        print("Error ensuring monitored_table_counts table:", e)
    finally:
        conn.close()

    
###############################################
# Print Token Helpers
###############################################

def print_canteen_token(user_id, meal_name, meal_time):
    """
    Enhanced token printing with error handling and formatting
    """
    try:
        CONFIG_FILE = "config.json"
        from utils import load_config, log_event, print_token, validate_printer
        
        # Load configuration
        config = load_config(CONFIG_FILE)
        printer_name = config.get("selected_printer", win32print.GetDefaultPrinter())

        # Validate printer
        if not validate_printer(printer_name):
            log_event(f"Invalid printer: {printer_name}")
            return False

        # Print token
        success = print_token(printer_name, user_id, meal_name, meal_time)
        
        if success:
            log_event(f"Token Printed Successfully - User: {user_id} | {meal_name} | {meal_time}")
        else:
            log_event(f"Token Printing Failed - User: {user_id} | {meal_name} | {meal_time}")
        
        return success

    except Exception as e:
        log_event(f"Token Printing Error: {str(e)}")
        print(f"Error printing token: {str(e)}")
        return False
    





###############################################
# 
###############################################

def update_monitored_table_counts():
    """
    Retrieves monitored table row counts from MAIN_DB and saves them to LOGGER_DB.
    Clears the monitored_table_counts table first, then inserts fresh data.
    For any table with a changed row count (compared to the previous snapshot),
    calls row_count_change() to process the event.
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
    previous_monitored_counts = {entry["table_name"]: entry["row_count"] for entry in monitored_tables}
    
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
        return {"status": "success", "data": monitored_tables}
    except Exception as e:
        print("Error updating monitored_table_counts:", e)
        return {"error": str(e)}
    finally:
        conn.close()



###############################################
# 
###############################################


def canteenandshiftchecker():
    try:
        conn = get_logger_db_conn()
        cursor = conn.cursor()
        cursor.execute("""SELECT ct.id AS TimingID, ct.canteen_name, ct.start_time AS CanteenStartTime, ct.end_time AS CanteenEndTime, s.id AS ShiftID,
        s.shift_name, s.start_time AS ShiftStartTime FROM [signet_log].[dbo].[canteen_timings] AS ct JOIN [signet_log].[dbo].[canteen_timing_shifts] AS cts ON ct.id = cts.timing_id JOIN [signet_log].[dbo].[shifts] AS s ON cts.shift_name = s.id;
        """)
    except Exception as e:
        return False














###############################################
# Route Endpoints
###############################################
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

