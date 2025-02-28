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
        try:
            cursor.execute("BEGIN TRANSACTION")
            
            # Clear existing data
            cursor.execute("DELETE FROM canteen_timing_shifts")
            cursor.execute("DELETE FROM canteen_timings")
            
            # Get all form data for debugging
            form_data = request.form
            print("Form data received:", dict(form_data))
            
            # Process each canteen timing
            for i in range(len(request.form.getlist('canteen_name[]'))):
                canteen_name = request.form.getlist('canteen_name[]')[i]
                start_time = request.form.getlist('start_time[]')[i]
                end_time = request.form.getlist('end_time[]')[i]
                description = request.form.getlist('description[]')[i]
                
                # Insert canteen timing and get its ID
                cursor.execute("""
                    INSERT INTO canteen_timings (canteen_name, start_time, end_time, description)
                    OUTPUT INSERTED.id
                    VALUES (?, ?, ?, ?)
                """, (canteen_name, start_time, end_time, description))
                
                timing_id = cursor.fetchone()[0]
                print(f"Inserted timing ID: {timing_id}")
                
                # Get selected shifts for this timing
                shift_key = f'shifts_{i}[]'
                selected_shifts = request.form.getlist(shift_key)
                print(f"Selected shifts for timing {timing_id}: {selected_shifts}")
                
                # Insert shift relationships
                for shift_id in selected_shifts:
                    print(f"Inserting relationship: timing_id={timing_id}, shift_id={shift_id}")
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
                    print(f"Relationship count after insertion: {count}")
            
            # Final verification
            cursor.execute("SELECT COUNT(*) FROM canteen_timing_shifts")
            total_relationships = cursor.fetchone()[0]
            print(f"Total relationships in table: {total_relationships}")
            
            cursor.execute("SELECT * FROM canteen_timing_shifts")
            all_relationships = cursor.fetchall()
            print(f"All relationships: {all_relationships}")
            
            cursor.execute("COMMIT")
            flash("Canteen timings updated successfully.", "success")
            
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"Error: {str(e)}")
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


