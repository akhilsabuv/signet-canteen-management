from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash
import pyodbc

system_bp = Blueprint('system', __name__, url_prefix='/system')

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
        print("\n=== FORM DATA ===")
        print(dict(request.form))
        
        try:
            cursor.execute("BEGIN TRANSACTION")
            
            # First verify if the tables exist and their structure
            print("\nVerifying tables:")
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'canteen_timing_shifts')
                BEGIN
                    CREATE TABLE canteen_timing_shifts (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        canteen_timing_id INT NOT NULL,
                        shift_id INT NOT NULL
                    )
                END
            """)
            
            # Clear existing data
            cursor.execute("DELETE FROM canteen_timing_shifts")
            cursor.execute("DELETE FROM canteen_timings")
            
            # Process each canteen timing
            for key in request.form:
                if key.startswith('canteen_name_'):
                    index = key.split('_')[-1]
                    
                    canteen_name = request.form.get(f'canteen_name_{index}')
                    start_time = request.form.get(f'start_time_{index}')
                    end_time = request.form.get(f'end_time_{index}')
                    description = request.form.get(f'description_{index}', '')
                    
                    print(f"\nProcessing canteen: {canteen_name}")
                    
                    # Insert canteen timing
                    insert_timing_sql = """
                        INSERT INTO canteen_timings (canteen_name, start_time, end_time, description)
                        OUTPUT INSERTED.id
                        VALUES (?, ?, ?, ?)
                    """
                    cursor.execute(insert_timing_sql, (canteen_name, start_time, end_time, description))
                    timing_id = cursor.fetchone()[0]
                    print(f"Inserted timing_id: {timing_id}")
                    
                    # Get shifts for this timing
                    shifts = request.form.getlist(f'shift_{index}')
                    print(f"Processing shifts for timing {timing_id}: {shifts}")
                    
                    # Insert shift relationships
                    for shift_id in shifts:
                        try:
                            print(f"Inserting relationship: timing={timing_id}, shift={shift_id}")
                            cursor.execute("""
                                INSERT INTO canteen_timing_shifts (canteen_timing_id, shift_id)
                                VALUES (?, ?)
                            """, (timing_id, shift_id))
                            
                            # Verify the insertion
                            cursor.execute("""
                                SELECT COUNT(*) FROM canteen_timing_shifts 
                                WHERE canteen_timing_id = ? AND shift_id = ?
                            """, (timing_id, shift_id))
                            count = cursor.fetchone()[0]
                            print(f"Verification count: {count}")
                            
                        except Exception as shift_error:
                            print(f"Error inserting shift relationship: {str(shift_error)}")
            
            # Verify final data
            cursor.execute("SELECT COUNT(*) FROM canteen_timing_shifts")
            final_count = cursor.fetchone()[0]
            print(f"\nFinal count in canteen_timing_shifts: {final_count}")
            
            cursor.execute("""
                SELECT ct.canteen_name, cts.shift_id 
                FROM canteen_timings ct 
                JOIN canteen_timing_shifts cts ON ct.id = cts.canteen_timing_id
            """)
            relationships = cursor.fetchall()
            print("Final relationships:", relationships)
            
            cursor.execute("COMMIT")
            print("Transaction committed successfully")
            flash("Canteen timings updated successfully.", "success")
            
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"Error in transaction: {str(e)}")
            flash(f"Error updating canteen timings: {str(e)}", "error")
        finally:
            conn.close()
        return redirect(url_for('system.edit_canteen_timings'))

    # GET request - fetch existing data
    try:
        # Get all shifts
        cursor.execute("""
            SELECT id, shift_name, 
                   CONVERT(varchar, start_time, 108) as start_time, 
                   CONVERT(varchar, end_time, 108) as end_time
            FROM shifts 
            ORDER BY start_time
        """)
        shifts = [dict(zip([column[0] for column in cursor.description], row)) 
                 for row in cursor.fetchall()]
        
        # Get canteen timings with their allowed shifts
        cursor.execute("""
            SELECT 
                ct.id, 
                ct.canteen_name, 
                CONVERT(varchar, ct.start_time, 108) as start_time, 
                CONVERT(varchar, ct.end_time, 108) as end_time, 
                ct.description,
                STRING_AGG(CAST(cts.shift_id as VARCHAR), ',') as allowed_shifts
            FROM canteen_timings ct
            LEFT JOIN canteen_timing_shifts cts ON ct.id = cts.canteen_timing_id
            GROUP BY ct.id, ct.canteen_name, ct.start_time, ct.end_time, ct.description
            ORDER BY ct.start_time
        """)
        
        timings = []
        for row in cursor.fetchall():
            allowed_shifts = set()
            if row.allowed_shifts:
                allowed_shifts = set(int(x) for x in row.allowed_shifts.split(','))
            timings.append({
                'id': row.id,
                'canteen_name': row.canteen_name,
                'start_time': row.start_time,
                'end_time': row.end_time,
                'description': row.description,
                'allowed_shifts': allowed_shifts
            })
            
    except Exception as e:
        shifts = []
        timings = []
        flash(f"Error retrieving data: {str(e)}", "error")
    finally:
        conn.close()
    
    return render_template('edit_canteen_timings.html', timings=timings, shifts=shifts)

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


