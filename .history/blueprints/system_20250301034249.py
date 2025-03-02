from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash, jsonify
import pyodbc
import logging

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
@system_bp.route('/edit_canteen_timings', methods=['GET', 'POST'])
def edit_canteen_timings():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    timing_data = []
    allowed_shifts = []
    
    try:
        if request.method == 'POST':
            current_app.logger.debug("\n=== Starting POST request processing ===")
            current_app.logger.debug("Form data received: %s", dict(request.form))
            
            try:
                # Begin a single transaction for deletions and inserts
                cursor.execute("BEGIN TRANSACTION")
                
                # Clear existing data
                current_app.logger.debug("Clearing existing data...")
                cursor.execute("DELETE FROM canteen_timing_shifts")
                cursor.execute("DELETE FROM canteen_timings")
                
                # Retrieve form arrays
                canteen_names = request.form.getlist('canteen_name[]')
                start_times = request.form.getlist('start_time[]')
                end_times = request.form.getlist('end_time[]')
                descriptions = request.form.getlist('description[]')

                current_app.logger.debug("Processing %d rows", len(canteen_names))

                # Process each row from the form
                for i in range(len(canteen_names)):
                    canteen_name = canteen_names[i].strip()
                    # Append ":00" to times if needed (to form HH:MM:SS)
                    start_time = start_times[i].strip() + ":00"
                    end_time = end_times[i].strip() + ":00"
                    description = descriptions[i].strip()
                    
                    current_app.logger.debug("Inserting row %d: %s, %s - %s, %s", i + 1, canteen_name, start_time, end_time, description)

                    # Insert timing record and get the new ID
                    insert_query = """
                        INSERT INTO canteen_timings 
                        (canteen_name, start_time, end_time, description)
                        OUTPUT INSERTED.id
                        VALUES (?, ?, ?, ?)
                    """
                    cursor.execute(insert_query, (canteen_name, start_time, end_time, description))
                    timing_id_row = cursor.fetchone()
                    if timing_id_row is None:
                        raise Exception("Failed to retrieve inserted timing id for row %d" % (i + 1))
                    timing_id = timing_id_row[0]
                    current_app.logger.debug("Inserted timing with ID: %d", timing_id)

                    # Retrieve selected shifts for this row (using the name shifts_i[])
                    shifts = request.form.getlist(f'shifts_{i}[]')
                    current_app.logger.debug("Processing shifts for row %d: %s", i, shifts)

                    # Insert selected shifts for this timing
                    if shifts:
                        for shift_id in shifts:
                            cursor.execute("""
                                INSERT INTO canteen_timing_shifts (timing_id, shift_name)
                                SELECT ?, shift_name 
                                FROM shifts 
                                WHERE id = ?
                            """, (timing_id, shift_id))
                            current_app.logger.debug("Inserted shift %s for timing %d", shift_id, timing_id)

                # Commit all changes if everything is successful
                conn.commit()
                current_app.logger.debug("All changes committed successfully")
                flash("Canteen timings updated successfully!", "success")
                return redirect(url_for('system.edit_canteen_timings'))

            except Exception as e:
                current_app.logger.error("Error during save: %s", e, exc_info=True)
                cursor.execute("ROLLBACK")
                flash(f"Error: {str(e)}", "error")
                return redirect(url_for('system.edit_canteen_timings'))

        # GET request: Retrieve existing canteen timings (same as before)
        cursor.execute("""
            SELECT 
                ct.id,
                ct.canteen_name,
                CONVERT(varchar(5), ct.start_time, 108) as start_time,
                CONVERT(varchar(5), ct.end_time, 108) as end_time,
                ISNULL(ct.description, '') as description
            FROM canteen_timings ct
            ORDER BY ct.start_time
        """)
        timings = cursor.fetchall()

        # Retrieve all allowed shifts
        cursor.execute("""
            SELECT 
                id,
                shift_name,
                CONVERT(varchar(5), start_time, 108) as start_time,
                CONVERT(varchar(5), end_time, 108) as end_time
            FROM shifts 
            ORDER BY shift_name
        """)
        allowed_shifts = cursor.fetchall()

        # For each timing, retrieve its associated shifts and build a list of shift names
        for timing in timings:
            cursor.execute("""
                SELECT 
                    cts.id as timing_shift_id,
                    cts.timing_id,
                    cts.shift_name,
                    s.id as shift_id,
                    s.shift_name,
                    CONVERT(varchar(5), s.start_time, 108) as start_time,
                    CONVERT(varchar(5), s.end_time, 108) as end_time
                FROM canteen_timing_shifts cts
                JOIN shifts s ON cts.shift_name = s.shift_name
                WHERE cts.timing_id = ?
            """, (timing.id,))
            timing_shifts = cursor.fetchall()
            
            # Create a list of selected shift names for pre-checking checkboxes in the template
            selected_shifts = [shift.shift_name for shift in timing_shifts]
            
            timing_data.append({
                'id': timing.id,
                'canteen_name': timing.canteen_name,
                'start_time': timing.start_time,
                'end_time': timing.end_time,
                'description': timing.description,
                'selected_shifts': selected_shifts,
                'timing_shifts': [{
                    'id': shift.timing_shift_id,
                    'timing_id': shift.timing_id,
                    'shift_name': shift.shift_name,
                    'shift_details': {
                        'id': shift.shift_id,
                        'shift_name': shift.shift_name,
                        'start_time': shift.start_time,
                        'end_time': shift.end_time
                    }
                } for shift in timing_shifts]
            })

    except Exception as e:
        current_app.logger.error("Error in edit_canteen_timings: %s", e, exc_info=True)
        flash(f"Error: {str(e)}", "error")
    finally:
        conn.close()

    return render_template('edit_canteen_timings.html', 
                           timings=timing_data,
                           allowed_shifts=allowed_shifts)



@system_bp.route('/edit_shifts', methods=['GET', 'POST'])
def edit_shifts():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    print("Method:", request.method)
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        print("POST request received")
        try:
            # Delete existing records from the shifts table
            cursor.execute("DELETE FROM shifts")
            
            # Process each shift entry from the form
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
    
    # GET request: Retrieve all shifts
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

        # Get current time for debugging
        cursor.execute("SELECT CAST(GETDATE() AS time)")
        current_time = cursor.fetchone()[0]
        print(f"Current time: {current_time}")

        # Retrieve active canteen timings based on the current time
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
        print("Active timings query result:", active_timings)

        current_timings = []
        if active_timings:
            for row in active_timings:
                current_timings.append({
                    'canteen': row.canteen_name,
                    'start_time': row.formatted_start,
                    'end_time': row.formatted_end
                })
        else:
            # Fallback if no active timings
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
