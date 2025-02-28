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
        print("\n=== Form Data ===")
        print(dict(request.form))
        
        try:
            cursor.execute("BEGIN TRANSACTION")
            
            # Store existing relationships before deletion
            cursor.execute("SELECT * FROM canteen_timing_shifts")
            old_relationships = cursor.fetchall()
            print("Previous relationships:", old_relationships)
            
            # Instead of deleting everything, we'll update existing records
            # and only delete/add as needed
            new_timings = []
            for i in range(len(request.form.getlist('canteen_name[]'))):
                canteen_name = request.form.getlist('canteen_name[]')[i]
                start_time = request.form.getlist('start_time[]')[i]
                end_time = request.form.getlist('end_time[]')[i]
                description = request.form.getlist('description[]')[i]
                
                print(f"\nProcessing timing: {canteen_name} ({start_time} - {end_time})")
                
                # Check if this timing already exists
                cursor.execute("""
                    SELECT id FROM canteen_timings 
                    WHERE canteen_name = ? AND start_time = ? AND end_time = ?
                """, (canteen_name, start_time, end_time))
                existing = cursor.fetchone()
                
                if existing:
                    timing_id = existing[0]
                    # Update existing timing
                    cursor.execute("""
                        UPDATE canteen_timings 
                        SET description = ?
                        WHERE id = ?
                    """, (description, timing_id))
                    print(f"Updated existing timing ID: {timing_id}")
                else:
                    # Insert new timing
                    cursor.execute("""
                        INSERT INTO canteen_timings (canteen_name, start_time, end_time, description)
                        OUTPUT INSERTED.id
                        VALUES (?, ?, ?, ?)
                    """, (canteen_name, start_time, end_time, description))
                    timing_id = cursor.fetchone()[0]
                    print(f"Inserted new timing ID: {timing_id}")
                
                new_timings.append(timing_id)
                
                # Handle shifts for this timing
                shifts_key = f'shifts_{i}'
                selected_shifts = request.form.getlist(f'{shifts_key}[]')
                print(f"Selected shifts for timing {timing_id}: {selected_shifts}")
                
                # Remove old relationships for this timing
                cursor.execute("""
                    DELETE FROM canteen_timing_shifts 
                    WHERE canteen_timing_id = ?
                """, (timing_id,))
                
                # Insert new relationships
                for shift_id in selected_shifts:
                    print(f"Inserting relationship: timing={timing_id}, shift={shift_id}")
                    cursor.execute("""
                        INSERT INTO canteen_timing_shifts (canteen_timing_id, shift_id)
                        VALUES (?, ?)
                    """, (timing_id, shift_id))
            
            # Remove timings that no longer exist
            cursor.execute("""
                DELETE FROM canteen_timings 
                WHERE id NOT IN ({})
            """.format(','.join('?' * len(new_timings))), new_timings)
            
            # Verify the final state
            cursor.execute("SELECT COUNT(*) FROM canteen_timings")
            timings_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM canteen_timing_shifts")
            relationships_count = cursor.fetchone()[0]
            
            print(f"\nVerification counts:")
            print(f"Canteen timings: {timings_count}")
            print(f"Shift relationships: {relationships_count}")
            
            cursor.execute("COMMIT")
            print("Transaction committed successfully")
            flash("Canteen timings updated successfully.", "success")
            
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"Error: {str(e)}")
            flash(f"Error updating canteen timings: {str(e)}", "error")
        finally:
            conn.close()
        return redirect(url_for('system.edit_canteen_timings'))

    # GET request handling
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
        print(f"Error retrieving data: {str(e)}")
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


