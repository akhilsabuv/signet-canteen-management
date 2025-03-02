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
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    timing_data = []

    try:
        if request.method == 'POST':
            print("\n=== Form Data ===")
            print(dict(request.form))
            
            # Get form data arrays
            timing_ids = request.form.getlist('timing_id[]')
            canteen_names = request.form.getlist('canteen_name[]')
            start_times = request.form.getlist('start_time[]')
            end_times = request.form.getlist('end_time[]')
            descriptions = request.form.getlist('description[]')

            try:
                cursor.execute("BEGIN TRANSACTION")
                
                # Truncate existing data
                print("Truncating existing data...")
                cursor.execute("DELETE FROM canteen_timing_shifts")
                cursor.execute("DELETE FROM canteen_timings")
                
                # Process each row
                for i in range(len(canteen_names)):
                    canteen_name = canteen_names[i].strip()
                    start_time = start_times[i].strip()
                    end_time = end_times[i].strip()
                    description = descriptions[i].strip()
                    selected_shifts = request.form.getlist(f'shifts_{i}')
                    
                    print(f"\nProcessing row {i}:")
                    print(f"Canteen: {canteen_name}")
                    print(f"Times: {start_time} - {end_time}")
                    print(f"Selected shifts: {selected_shifts}")

                    # Insert new timing
                    cursor.execute("""
                        INSERT INTO canteen_timings 
                        (canteen_name, start_time, end_time, description)
                        OUTPUT INSERTED.id
                        VALUES (?, ?, ?, ?)
                    """, (canteen_name, start_time, end_time, description))
                    
                    timing_id = cursor.fetchone()[0]

                    # Insert shifts
                    if selected_shifts:
                        for shift_id in selected_shifts:
                            cursor.execute("""
                                INSERT INTO canteen_timing_shifts (timing_id, shift_name)
                                SELECT ?, shift_name 
                                FROM shifts 
                                WHERE id = ?
                            """, (timing_id, shift_id))

                conn.commit()
                print("Changes committed successfully")
                flash("Canteen timings updated successfully!", "success")
                return redirect(url_for('system.edit_canteen_timings'))

            except Exception as e:
                print(f"Error during save: {str(e)}")
                cursor.execute("ROLLBACK")
                flash(f"Error: {str(e)}", "error")
                return redirect(url_for('system.edit_canteen_timings'))

        # GET request - Fetch existing data
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

        # Get all shifts
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

        # Build timing data with shifts
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
            
            timing_data.append({
                'id': timing.id,
                'canteen_name': timing.canteen_name,
                'start_time': timing.start_time,
                'end_time': timing.end_time,
                'description': timing.description,
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
        print(f"Error: {str(e)}")
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
    
    print("Method:", request.method)  # Debug print
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        print("POST request received")  # Debug print
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


