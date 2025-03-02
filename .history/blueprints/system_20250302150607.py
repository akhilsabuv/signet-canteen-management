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
def edit_canteen_timings():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        # cursor.execute("DELETE FROM canteen_timings")
        try:
            # Retrieve lists from the form
            canteen_names = request.form.getlist('canteen_name')
            start_times = request.form.getlist('start_time')
            end_times = request.form.getlist('end_time')
            descriptions = request.form.getlist('description')
            record_ids = request.form.getlist('id')  # 'id' values from the form; may include 'NULL' for new records
            # First, get the existing IDs from your database
            cursor.execute("SELECT id FROM canteen_timings")
            existing_ids = {str(row[0]) for row in cursor.fetchall()}  # use a set for fast lookup and convert to strings
            # Get the submitted IDs (ignoring new records marked as 'NULL')
            submitted_ids = {record_id for record_id in record_ids if record_id != 'NULL'}
            # Determine which IDs exist in the database but weren't submitted in the form
            ids_to_delete = existing_ids - submitted_ids
            # Delete the removed items
            for record_id in ids_to_delete:
                cursor.execute("DELETE FROM canteen_timings WHERE id = ?", (record_id,))
            # Now process the submitted rows: update existing ones and insert new ones
            for canteen_name, start_time, end_time, description, record_id in zip(canteen_names, start_times, end_times, descriptions, record_ids):
                if canteen_name and start_time and end_time:
                    if record_id != 'NULL':
                        # Update existing record
                        cursor.execute("""
                            UPDATE canteen_timings 
                            SET canteen_name = ?, start_time = ?, end_time = ?, description = ? 
                            WHERE id = ?
                        """, (canteen_name, start_time, end_time, description, record_id))
                    else:
                        # Insert new record
                        cursor.execute("""
                            INSERT INTO canteen_timings (canteen_name, start_time, end_time, description)
                            VALUES (?, ?, ?, ?)
                        """, (canteen_name, start_time, end_time, description))

            # Commit the changes
            conn.commit()
            flash("Canteen timings updated successfully.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error updating canteen timings: {str(e)}", "error")
    try:
        cursor.execute("""
            SELECT id, canteen_name,
            CONVERT(varchar, start_time, 108) as start_time, 
            CONVERT(varchar, end_time, 108) as end_time,description
            FROM canteen_timings 
            ORDER BY id
        """)
        timings = cursor.fetchall()
    except Exception as e:
        shifts = []
        flash(f"Error retrieving shifts: {str(e)}", "error")
    finally:
        conn.close()
    
    return render_template('edit_canteen_timings.html', timings=timings)

@system_bp.route('/edit_shifts', methods=['GET', 'POST'])
def edit_shifts():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
        
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        try:
            print(request.form)
            shift_name = request.form.getlist('shift_name')
            shift_start = request.form.getlist('shift_start')
            shift_end = request.form.getlist('shift_end')
            record_ids = request.form.getlist('id')  # 'id' values from the form; may include 'NULL' for new records
            # First, get the existing IDs from your database
            cursor.execute("SELECT id FROM shifts")
            existing_ids = {str(row[0]) for row in cursor.fetchall()}  # use a set for fast lookup and convert to strings
            # Get the submitted IDs (ignoring new records marked as 'NULL')
            submitted_ids = {record_id for record_id in record_ids if record_id != 'NULL'}
            # Determine which IDs exist in the database but weren't submitted in the form
            ids_to_delete = existing_ids - submitted_ids
            # Delete the removed items
            for record_id in ids_to_delete:
                cursor.execute("DELETE FROM shifts WHERE id = ?", (record_id,))
            # Now process the submitted rows: update existing ones and insert new ones
            for shift_name, shift_start, shift_end, record_id in zip(shift_name, shift_start, shift_end, record_ids):
                if shift_name and shift_start and shift_end:
                    if record_id != 'NULL':
                        # Update existing record
                        cursor.execute("""
                            UPDATE shifts 
                            SET shift_name = ?, start_time = ?, end_time = ? 
                            WHERE id = ?
                        """, (shift_name, shift_start, shift_end, record_id))
                    else:
                        # Insert new record
                        cursor.execute("""
                            INSERT INTO shifts (shift_name, start_time, end_time)
                            VALUES (?, ?, ?)
                        """, (shift_name, shift_start, shift_end))

            # Commit the changes
            conn.commit()
            flash("Canteen timings updated successfully.", "success")

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

@system_bp.route('/assign_canteen_to_shift', methods=['GET', 'POST'])
def assign_canteen_to_shift():
    # Check if the user is logged in. Adjust the session check as needed.
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        try:
            # Process the form data. You can access form fields via request.form.
            form_data = request.form
            # For example, printing the form data to the console
            print("Form Data:", form_data)
            
            # Here, you can iterate through the form data to extract the canteen_id[] and shift_ids[] values,
            # or process your combinations on the client side (as logged in the browser console).
            flash("Canteen assignments updated successfully!", "success")
            return redirect(url_for('system.assign_canteen_to_shift'))
        except Exception as e:
            flash(f"Error processing form data: {str(e)}", "error")
            return redirect(url_for('system.assign_canteen_to_shift'))
    
    # For GET requests, fetch the shifts and canteen timings from the database.
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    try:
        # Query to get all shifts
        cursor.execute("""
            SELECT id, shift_name, start_time, end_time
            FROM shifts
            ORDER BY shift_name
        """)
        shifts = cursor.fetchall()

        # Query to get all canteen timings
        cursor.execute("""
            SELECT id, canteen_name, start_time, end_time
            FROM canteen_timings
            ORDER BY canteen_name
        """)
        canteen_timings = cursor.fetchall()
    except Exception as e:
        shifts = []
        canteen_timings = []
        flash(f"Error retrieving data: {str(e)}", "error")
    finally:
        conn.close()

    return render_template('assign_canteen_to_shift.html', shifts=shifts, canteen_timings=canteen_timings)


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
