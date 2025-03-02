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
    timing_data = []
    
    try:
        if request.method == 'POST':
            print("\n=== Starting POST request processing ===")
            form_data = dict(request.form)
            print("Form data received:", form_data)
            
            try:
                # Start transaction
                cursor.execute("BEGIN TRANSACTION")
                
                # Disable foreign key constraints
                print("Disabling foreign key constraints...")
                cursor.execute("ALTER TABLE canteen_timings NOCHECK CONSTRAINT ALL;")
                
                # Truncate existing data
                print("Truncating existing data...")
                truncate_query = "TRUNCATE TABLE canteen_timings"
                print(f"Executing query: {truncate_query}")
                cursor.execute(truncate_query)
                
                # Get form data arrays
                canteen_names = request.form.getlist('canteen_name[]')
                start_times = request.form.getlist('start_time[]')
                end_times = request.form.getlist('end_time[]')
                descriptions = request.form.getlist('description[]')
                
                # print(f"Processing {len(canteen_names)} rows")
                
                # Insert new data
                # for i in range(len(canteen_names)):
                #     canteen_name = canteen_names[i].strip()
                #     start_time = start_times[i].strip()
                #     end_time = end_times[i].strip()
                #     description = descriptions[i].strip() if descriptions[i] else ''
                    
                #     print(f"Inserting row {i + 1}: {canteen_name}, {start_time}, {end_time}, {description}")
                #     insert_query = """
                #         INSERT INTO canteen_timings 
                #         (canteen_name, start_time, end_time, description)
                #         VALUES (?, ?, ?, ?)
                #     """
                #     cursor.execute(insert_query, 
                #                    (canteen_name, start_time, end_time, description))
                
                # # Commit the transaction
                # conn.commit()
                # print("Changes committed successfully")
                
                # Re-enable foreign key constraints
                print("Re-enabling foreign key constraints...")
                cursor.execute("ALTER TABLE canteen_timings CHECK CONSTRAINT ALL;")
                
                # Verify the inserted data
                cursor.execute("SELECT * FROM canteen_timings")
                inserted_rows = cursor.fetchall()
                print("Inserted rows after commit:", inserted_rows)
                
                flash("Canteen timings updated successfully!", "success")
                return redirect(url_for('system.edit_canteen_timings'))
                
            except Exception as e:
                print(f"Error during save: {str(e)}")
                cursor.execute("ROLLBACK")
                flash(f"Error: {str(e)}", "error")
                return redirect(url_for('system.edit_canteen_timings'))
        
        # GET request - fetch existing data
        select_query = """
            SELECT 
                id,
                canteen_name,
                CONVERT(varchar(5), start_time, 108) as start_time,
                CONVERT(varchar(5), end_time, 108) as end_time,
                ISNULL(description, '') as description
            FROM canteen_timings
            ORDER BY start_time
        """
        print(f"Executing query: {select_query}")
        cursor.execute(select_query)
        
        rows = cursor.fetchall()
        for row in rows:
            timing_data.append({
                'id': row.id,
                'canteen_name': row.canteen_name,
                'start_time': row.start_time,
                'end_time': row.end_time,
                'description': row.description
            })
            
    except Exception as e:
        print(f"Error: {str(e)}")
        flash(f"Error: {str(e)}", "error")
        
    finally:
        conn.close()

    return render_template('edit_canteen_timings.html', timings=timing_data)

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

