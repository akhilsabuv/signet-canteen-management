from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash, jsonify
import pyodbc
from datetime import datetime
import logging
import traceback

system_bp = Blueprint('system', __name__, url_prefix='/system')

# Set up logging
logging.basicConfig(
    filename='canteen_system.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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

@system_bp.route('/edit_canteen_timings', methods=['GET', 'POST'])
def edit_canteen_timings():
    logging.info("=== Starting edit_canteen_timings function ===")
    
    if not session.get('logged_in'):
        logging.warning("User not logged in, redirecting to login")
        return redirect(url_for('auth.login'))

    try:
        conn = get_logger_db_conn()
        cursor = conn.cursor()
        logging.info("Database connection established")
        
        # Log database info
        db_name = conn.getinfo(pyodbc.SQL_DATABASE_NAME)
        logging.info(f"Connected to database: {db_name}")

        if request.method == 'POST':
            logging.info("Processing POST request")
            try:
                cursor.execute("BEGIN TRANSACTION")
                form_data = dict(request.form)
                logging.info(f"Form data received: {form_data}")

                # Log form data details
                canteen_names = request.form.getlist('canteen_name[]')
                start_times = request.form.getlist('start_time[]')
                end_times = request.form.getlist('end_time[]')
                descriptions = request.form.getlist('description[]')

                logging.info(f"Number of canteens: {len(canteen_names)}")
                logging.info(f"Canteen names: {canteen_names}")
                logging.info(f"Start times: {start_times}")
                logging.info(f"End times: {end_times}")
                logging.info(f"Descriptions: {descriptions}")

                # Get existing timings
                cursor.execute("SELECT id, canteen_name FROM canteen_timings")
                existing_timings = {row.canteen_name: row.id for row in cursor.fetchall()}
                logging.info(f"Existing timings: {existing_timings}")

                for i in range(len(canteen_names)):
                    logging.info(f"\nProcessing row {i}")
                    canteen_name = canteen_names[i].strip()
                    start_time = start_times[i].strip()
                    end_time = end_times[i].strip()
                    description = descriptions[i].strip()

                    # Get shifts for this timing
                    selected_shifts = []
                    shift_keys = [k for k in form_data.keys() if k.startswith(f'shifts_{i}')]
                    for key in shift_keys:
                        shift_values = request.form.getlist(key)
                        selected_shifts.extend(shift_values)

                    logging.info(f"Row {i} details:")
                    logging.info(f"  Canteen: {canteen_name}")
                    logging.info(f"  Times: {start_time} - {end_time}")
                    logging.info(f"  Description: {description}")
                    logging.info(f"  Selected shifts: {selected_shifts}")

                    try:
                        if canteen_name in existing_timings:
                            timing_id = existing_timings[canteen_name]
                            logging.info(f"Updating existing timing ID: {timing_id}")
                            
                            # Log the update query
                            update_query = """
                                UPDATE canteen_timings 
                                SET start_time = ?, end_time = ?, description = ?
                                WHERE id = ?
                            """
                            logging.info(f"Update query: {update_query}")
                            logging.info(f"Parameters: {(start_time, end_time, description, timing_id)}")
                            
                            cursor.execute(update_query, (start_time, end_time, description, timing_id))
                            
                            # Delete existing shifts
                            cursor.execute("DELETE FROM canteen_timing_shifts WHERE timing_id = ?", (timing_id,))
                            logging.info(f"Deleted existing shifts for timing ID: {timing_id}")
                        else:
                            # Insert new timing
                            insert_query = """
                                INSERT INTO canteen_timings 
                                (canteen_name, start_time, end_time, description)
                                OUTPUT INSERTED.id
                                VALUES (?, ?, ?, ?)
                            """
                            logging.info(f"Insert query: {insert_query}")
                            logging.info(f"Parameters: {(canteen_name, start_time, end_time, description)}")
                            
                            cursor.execute(insert_query, (canteen_name, start_time, end_time, description))
                            timing_id = cursor.fetchone()[0]
                            logging.info(f"Inserted new timing with ID: {timing_id}")

                        # Insert shifts
                        for shift in selected_shifts:
                            shift_insert_query = """
                                INSERT INTO canteen_timing_shifts 
                                (timing_id, shift_name)
                                VALUES (?, ?)
                            """
                            logging.info(f"Inserting shift: {shift} for timing {timing_id}")
                            cursor.execute(shift_insert_query, (timing_id, shift))

                    except Exception as row_error:
                        logging.error(f"Error processing row {i}:")
                        logging.error(traceback.format_exc())
                        raise

                conn.commit()
                logging.info("Transaction committed successfully")
                flash("Canteen timings updated successfully!", "success")
                return redirect(url_for('system.edit_canteen_timings'))

            except Exception as e:
                cursor.execute("ROLLBACK")
                logging.error("Error during save operation:")
                logging.error(traceback.format_exc())
                flash(f"Error: {str(e)}", "error")
                return redirect(url_for('system.edit_canteen_timings'))

        # GET request handling
        logging.info("Processing GET request")
        
        # Get existing timings
        select_query = """
            SELECT 
                ct.id,
                ct.canteen_name,
                CONVERT(varchar(5), ct.start_time, 108) as start_time,
                CONVERT(varchar(5), ct.end_time, 108) as end_time,
                ISNULL(ct.description, '') as description
            FROM canteen_timings ct
            ORDER BY ct.start_time
        """
        logging.info(f"Executing timing select query: {select_query}")
        cursor.execute(select_query)
        timings = cursor.fetchall()
        logging.info(f"Retrieved {len(timings)} timings")

        # Get shifts
        cursor.execute("SELECT DISTINCT shift_name FROM shifts ORDER BY shift_name")
        allowed_shifts = [row.shift_name for row in cursor.fetchall()]
        logging.info(f"Retrieved shifts: {allowed_shifts}")

        # Build timing data with shifts
        timing_data = []
        for timing in timings:
            cursor.execute("""
                SELECT shift_name 
                FROM canteen_timing_shifts 
                WHERE timing_id = ?
            """, (timing.id,))
            shifts = [row.shift_name for row in cursor.fetchall()]
            
            timing_info = {
                'id': timing.id,
                'canteen_name': timing.canteen_name,
                'start_time': timing.start_time,
                'end_time': timing.end_time,
                'description': timing.description,
                'shifts': shifts
            }
            timing_data.append(timing_info)
            logging.info(f"Processed timing: {timing_info}")

    except Exception as e:
        logging.error("Unexpected error:")
        logging.error(traceback.format_exc())
        flash(f"Error: {str(e)}", "error")

    finally:
        if 'conn' in locals():
            conn.close()
            logging.info("Database connection closed")

    logging.info("=== Ending edit_canteen_timings function ===\n")
    return render_template('edit_canteen_timings.html', 
                         timings=timing_data,
                         allowed_shifts=allowed_shifts)

@system_bp.route('/edit_shifts', methods=['GET', 'POST'])
def edit_shifts():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    print("Method:", request.method)  # Debug print
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        print("POST request received")  # Debug print
        print("Form data:", request.form)  # Debug print
        try:
            # Delete existing records
            cursor.execute("DELETE FROM shifts")
            
            # Handle all entries
            for key in request.form:
                if key.startswith("shift_name"):
                    index = key.split("_")[-1]
                    shift_name = request.form.get(f"shift_name_{index}")
                    start_time = request.form.get(f"shift_start_{index}")
                    end_time = request.form.get(f"shift_end_{index}")
                    
                    if shift_name and start_time and end_time:
                        cursor.execute("""
                            INSERT INTO shifts (shift_name, start_time, end_time)
                            VALUES (?, ?, ?)
                        """, (shift_name, start_time, end_time))
            
            conn.commit()
            flash("Shifts updated successfully.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error updating shifts: {str(e)}", "error")
        finally:
            conn.close()
        return redirect(url_for('system.edit_shifts'))
    
    # GET request
    try:
        cursor.execute("""
            SELECT id, shift_name, 
                   CONVERT(varchar, start_time, 108) as start_time, 
                   CONVERT(varchar, end_time, 108) as end_time
            FROM shifts 
            ORDER BY id
        """)
        shifts = cursor.fetchall()
    except Exception as e:
        shifts = []
        flash(f"Error retrieving shifts: {str(e)}", "error")
    finally:
        conn.close()
    
    return render_template('edit_shifts.html', shifts=shifts)

@system_bp.route('/live')
def live():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    return render_template('live.html')

@system_bp.route('/live/data')
def live_data():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_logger_db_conn()
        cursor = conn.cursor()

        # Debug: Print current time
        cursor.execute("SELECT CAST(GETDATE() AS time)")
        current_time = cursor.fetchone()[0]
        print(f"Current time: {current_time}")

        # Get current active canteen timing with formatted time
        cursor.execute("""
            SELECT 
                canteen_name,
                CONVERT(varchar(5), start_time, 108) as formatted_start,
                CONVERT(varchar(5), end_time, 108) as formatted_end
            FROM canteen_timings 
            WHERE CAST(GETDATE() AS time) BETWEEN start_time AND end_time
            ORDER BY start_time
        """)
        
        active_timings = cursor.fetchall()
        print("Active timings query result:", active_timings)  # Debug print

        current_timings = []
        if active_timings:
            for row in active_timings:
                current_timings.append({
                    'canteen': row.canteen_name,
                    'start_time': row.formatted_start,
                    'end_time': row.formatted_end
                })
        else:
            # Debug: Query all timings to see what's available
            cursor.execute("""
                SELECT 
                    canteen_name,
                    CONVERT(varchar(5), start_time, 108) as formatted_start,
                    CONVERT(varchar(5), end_time, 108) as formatted_end
                FROM canteen_timings
                ORDER BY start_time
            """)
            all_timings = cursor.fetchall()
            print("All available timings:", all_timings)  # Debug print
            
            current_timings = [{
                'canteen': 'No Active Canteen',
                'start_time': '--:--',
                'end_time': '--:--'
            }]

        return jsonify({
            'stats': {
                'total_meals': 0,
                'active_users': 0,
                'current_timings': current_timings
            },
            'recent_users': [],
            'canteen_stats': []
        })
        
    except Exception as e:
        print(f"Error in live_data: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


