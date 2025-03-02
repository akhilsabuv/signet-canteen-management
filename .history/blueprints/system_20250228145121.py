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
    allowed_shifts = []

    try:
        if request.method == 'POST':
            print("\n========== SAVE OPERATION START ==========")
            try:
                # Define form_data at the start
                form_data = dict(request.form)
                print("\nForm data received:", form_data)

                cursor.execute("BEGIN TRANSACTION")
                print("\n1. Started Transaction")

                # Get existing timings
                print("\n2. Fetching existing timings...")
                query = "SELECT id, canteen_name FROM canteen_timings"
                print(f"QUERY: {query}")
                cursor.execute(query)
                existing_timings = {row.canteen_name: row.id for row in cursor.fetchall()}
                print(f"Existing timings: {existing_timings}")

                # Process form data
                canteen_names = request.form.getlist('canteen_name[]')
                start_times = request.form.getlist('start_time[]')
                end_times = request.form.getlist('end_time[]')
                descriptions = request.form.getlist('description[]')

                print("\nReceived form arrays:")
                print(f"Canteen names: {canteen_names}")
                print(f"Start times: {start_times}")
                print(f"End times: {end_times}")
                print(f"Descriptions: {descriptions}")

                processed_timing_ids = set()

                for i in range(len(canteen_names)):
                    print(f"\n3. Processing Row {i}")
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

                    print(f"\nProcessing: {canteen_name} ({start_time} - {end_time})")
                    print(f"Selected shifts: {selected_shifts}")

                    if canteen_name in existing_timings:
                        timing_id = existing_timings[canteen_name]
                        processed_timing_ids.add(timing_id)

                        # Update existing timing
                        update_query = """
                            UPDATE canteen_timings 
                            SET start_time = ?, end_time = ?, description = ?
                            WHERE id = ?
                        """
                        params = (start_time, end_time, description, timing_id)
                        print(f"\nUPDATE QUERY:")
                        print(f"SQL: {update_query}")
                        print(f"Parameters: {params}")
                        cursor.execute(update_query, params)

                        # Delete existing shifts
                        delete_shifts_query = "DELETE FROM canteen_timing_shifts WHERE timing_id = ?"
                        print(f"\nDELETE SHIFTS QUERY:")
                        print(f"SQL: {delete_shifts_query}")
                        print(f"Parameter: {timing_id}")
                        cursor.execute(delete_shifts_query, (timing_id,))

                    else:
                        # Insert new timing
                        insert_query = """
                            INSERT INTO canteen_timings 
                            (canteen_name, start_time, end_time, description)
                            OUTPUT INSERTED.id
                            VALUES (?, ?, ?, ?)
                        """
                        params = (canteen_name, start_time, end_time, description)
                        print(f"\nINSERT QUERY:")
                        print(f"SQL: {insert_query}")
                        print(f"Parameters: {params}")
                        cursor.execute(insert_query, params)
                        timing_id = cursor.fetchone()[0]
                        processed_timing_ids.add(timing_id)
                        print(f"New timing ID: {timing_id}")

                    # Insert shifts
                    if selected_shifts:
                        insert_shifts_query = """
                            INSERT INTO canteen_timing_shifts 
                            (timing_id, shift_name)
                            VALUES (?, ?)
                        """
                        print(f"\nINSERT SHIFTS QUERIES:")
                        print(f"SQL: {insert_shifts_query}")
                        for shift in selected_shifts:
                            print(f"Parameters: ({timing_id}, {shift})")
                            cursor.execute(insert_shifts_query, (timing_id, shift))

                # Handle deleted timings
                timing_ids_to_delete = set(existing_timings.values()) - processed_timing_ids
                if timing_ids_to_delete:
                    print("\n4. Deleting removed timings")
                    for timing_id in timing_ids_to_delete:
                        delete_shifts_query = "DELETE FROM canteen_timing_shifts WHERE timing_id = ?"
                        delete_timing_query = "DELETE FROM canteen_timings WHERE id = ?"
                        
                        print(f"\nDELETE QUERIES for timing {timing_id}:")
                        print(f"SQL 1: {delete_shifts_query}")
                        print(f"SQL 2: {delete_timing_query}")
                        
                        cursor.execute(delete_shifts_query, (timing_id,))
                        cursor.execute(delete_timing_query, (timing_id,))

                print("\n5. Committing transaction...")
                conn.commit()
                print("Transaction committed successfully")
                print("\n========== SAVE OPERATION END ==========")
                
                flash("Canteen timings updated successfully!", "success")
                return redirect(url_for('system.edit_canteen_timings'))

            except Exception as e:
                print("\nERROR OCCURRED:")
                print(str(e))
                cursor.execute("ROLLBACK")
                print("Transaction rolled back")
                flash(f"Error: {str(e)}", "error")
                return redirect(url_for('system.edit_canteen_timings'))

        # GET request handling
        print("\n=== Processing GET request ===")
        
        # Get existing timings
        print("\nFetching existing timings...")
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
        print(f"Retrieved {len(timings)} timings")

        # Get shifts
        print("\nFetching shifts...")
        cursor.execute("SELECT DISTINCT shift_name FROM shifts ORDER BY shift_name")
        allowed_shifts = [row.shift_name for row in cursor.fetchall()]
        print(f"Available shifts: {allowed_shifts}")

        # Build timing data with shifts
        print("\nBuilding timing data with shifts...")
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
            print(f"Processed timing: {timing_info}")

    except Exception as e:
        print(f"Error: {str(e)}")
        flash(f"Error: {str(e)}", "error")

    finally:
        conn.close()
        print("Database connection closed")

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


