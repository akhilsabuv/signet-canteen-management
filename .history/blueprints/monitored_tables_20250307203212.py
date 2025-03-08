import re
import datetime
from datetime import timedelta, timezone
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
# MAIN_DB Connection Helper
###############################################
def get_main_db_conn():
    """
    Returns a pyodbc connection to LOGGER_DB using current_app.config values.
    """
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
# Latest Attendance Event Retrieval
###############################################
def get_latest_entry_event_time(usrid):
    """
    Retrieves the latest attendance event time (SRVDT) for the given user (USRID)
    by searching all MAIN_DB tables whose name matches TABLE_PREFIX + 6 digits,
    and where DEVUID is in the entry device list.
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
                        event_time = row
                    if (latest_event is None) or (event_time > latest_event):
                        latest_event = row
            except Exception as ex:
                print(f"Error querying table {table}: {ex}")
                continue
        conn.close()

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
    eligible = False
    trigger = None    
    try:
        conn = get_logger_db_conn()
        cursor = conn.cursor()
    
        cursor.execute("""
            SELECT
                ct.id AS TimingID,
                ct.canteen_name,
                ct.start_time AS CanteenStartTime,
                ct.end_time AS CanteenEndTime,
                s.id AS ShiftID,
                s.shift_name,
                s.start_time AS ShiftStartTime,
                s.end_time AS ShiftEndTime,
                CAST(GETDATE() AS TIME) AS currentTime
            FROM [signet_log].[dbo].[canteen_timings] AS ct
            JOIN [signet_log].[dbo].[canteen_timing_shifts] AS cts
            ON ct.id = cts.timing_id
            JOIN [signet_log].[dbo].[shifts] AS s
            ON cts.shift_name = s.id 
            WHERE ct.start_time <= CAST(GETDATE() AS TIME)
            AND ct.end_time >= CAST(GETDATE() AS TIME)
            ORDER BY ct.start_time;
        """)
        all_rows = cursor.fetchall()
        total_count = len(all_rows)
        index=0
        for row in all_rows:
            index=index+1
            start_time = row.CanteenStartTime
            end_time = row.CanteenEndTime
            shift_start_time=row.ShiftStartTime
            currentTime=row.currentTime

    #         # Dynamic time window check

            if start_time <= currentTime <= end_time:
                trigger = (f"Canteen: {row.canteen_name} "
                         f"({start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')})")
                print(f"Match found: {trigger}")
                latest_entry_dt_tm = get_latest_entry_event_time(usrid)
                latest_entry = latest_entry_dt_tm[0] 

                if isinstance(latest_entry, str):
                    latest_entry = datetime.datetime.strptime(latest_entry, "%Y-%m-%d %H:%M:%S")  # Adjust format if needed
 
                print("Latest entry:", latest_entry)


                latest_start = latest_entry - timedelta(hours=1)
                latest_end = latest_entry + timedelta(hours=1)

                event_dt = event_dt.replace(tzinfo=timezone.utc) 
                latest_entry = latest_entry.replace(tzinfo=timezone.utc) 
                time_difference = abs(event_dt-latest_entry)

                if time_difference < timedelta(hours=24):  # Same as timedelta(days=1)
                    print(index,"/",total_count)

                    print("Canteen Timings Start", row.CanteenStartTime)
                    print("Canteen Timings End", row.CanteenEndTime)

                    print("Shift Start",row.ShiftStartTime)


                    print("Entry Timing START(1hr back)", latest_start.time())
                    print("Entry Timing", latest_entry)
                    print("Entry Timing END(1hr front)", latest_end.time())

                    
                    print("Canteen Timing", event_dt)
                    
                    print("Canteen Timing type", type(event_dt))

                    print("Canteen Timing date", event_dt.date())

                    print("Canteen id", row.TimingID)


                    if latest_start.time() <= shift_start_time <= latest_end.time():

                        if(coupon_elegible(usrid, event_dt, row.TimingID)):
                            savetodb(usrid, event_dt, event_dt.time(), latest_entry, shift_start_time, 1, "New coupon added", row.TimingID, row.canteen_name)
                        else:
                            savetodb(usrid, event_dt, event_dt.time(), latest_entry, shift_start_time, 0, "The user has already taken the coupon", row.TimingID, row.canteen_name)
                        break
                    else:
                        if(index==total_count):
                            savetodb(usrid, event_dt, event_dt.time(), latest_entry, shift_start_time, 0, "Shift start time is NOT within the range.", row.TimingID, row.canteen_name)
                        else:
                            pass

                else:
                    savetodb(usrid, event_dt, event_dt.time(), latest_entry, shift_start_time, 2, "The user got entered more than 24 hrs ago", row.TimingID, row.canteen_name)
        
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
# Define Save to DB Elegibility
###############################################
def savetodb(usrid, event_dt, event_time, latest_entry, shift_start_time, status, description, canteenId, canteenName):    # event_timestamp = latest_entry[0]  # Extract the datetime object from the Row

    sql = """
        INSERT INTO sig_transactions  (
            usrid,
            event_dt,
            event_time,
            latest_entry,
            shift_start_time,
            status,
            description,
            canteenId,
            canteenName
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    

    params= (int(usrid), event_dt, event_time, latest_entry, shift_start_time, status, description, canteenId, canteenName)

    conn = get_logger_db_conn()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()

    cursor.close()
    conn.close()

    print("Row inserted successfully.")
    pass

###############################################
# Check if elegible for coupon
###############################################

def coupon_elegible(usrid, event_dt, timing):
    print("evx",event_dt.date())
    conn = get_logger_db_conn()
    cursor_check = conn.cursor()
    output = cursor_check.execute("""
                SELECT * 
                FROM [signet_log].[dbo].[sig_transactions] 
                WHERE usrid = ? 
                AND CONVERT(DATE, event_dt) = ? 
                AND canteenid = ? AND status = '1'
            """, (usrid, str(event_dt.date()), timing))
    print((usrid, str(event_dt.date()), timing))
    results = output.fetchall()
    if results:
        return False
    else:
        return True

    # print("Eligibility:", eligible)

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
        # print(f"Row count changed for {table_name}: from {previous_count} to {new_count}")
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        query = f"SELECT TOP 1 SRVDT, DEVDT, DEVUID, USRID FROM {table_name} ORDER BY SRVDT DESC"
        cursor.execute(query)
        row = cursor.fetchone()
        if row:
            # Convert DEVDT if it's a Unix timestamp.
            event_dt = row.SRVDT
            if isinstance(event_dt, (int, float)):
                event_dt = datetime.datetime.fromtimestamp(event_dt, tz=pytz.utc)
                print("asv",event_dt)
            print(f"Latest event in {table_name}: DEVDT={event_dt}, DEVUID={row.DEVUID}, USRID={row.USRID}")
            event_devid = str(row.DEVUID)
            
    #         # Retrieve dynamic device lists.
            canteen_ids = get_canteen_device_ids()

            if event_devid in canteen_ids:
                # print("Device is registered as a canteen device. Checking canteen eligibility...")
                if not check_elegibility(event_dt, row.DEVUID, row.USRID):
                    return False
                else:
                    print("Canteen timing conditions met.")
        else:
            print(f"No event details found in {table_name}.")
            return False
        conn.close()
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
# Update monitored table count(repetedly working every 2 seconds)
###############################################

def  update_monitored_table_counts():
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

