from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash, jsonify
import pyodbc
from datetime import datetime

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
            print("Form data received:", dict(request.form))
            
            # Get all form data
            canteen_names = request.form.getlist('canteen_name[]')
            start_times = request.form.getlist('start_time[]')
            end_times = request.form.getlist('end_time[]')
            descriptions = request.form.getlist('description[]')
            
            # Get existing timing IDs to track updates and deletions
            cursor.execute("SELECT id, canteen_name, start_time, end_time FROM canteen_timings")
            existing_timings = {(row.canteen_name, str(row.start_time), str(row.end_time)): row.id 
                              for row in cursor.fetchall()}
            
            updated_timing_ids = set()
            
            # Process each timing entry
            for i in range(len(canteen_names)):
                timing_key = (canteen_names[i], start_times[i], end_times[i])
                
                if timing_key in existing_timings:
                    # Update existing timing
                    timing_id = existing_timings[timing_key]
                    cursor.execute("""
                        UPDATE canteen_timings 
                        SET description = ?
                        WHERE id = ?
                    """, (descriptions[i], timing_id))
                    print(f"Updated timing ID: {timing_id}")
                else:
                    # Insert new timing
                    cursor.execute("""
                        INSERT INTO canteen_timings (canteen_name, start_time, end_time, description)
                        OUTPUT INSERTED.id
                        VALUES (?, ?, ?, ?)
                    """, (canteen_names[i], start_times[i], end_times[i], descriptions[i]))
                    timing_id = cursor.fetchone()[0]
                    print(f"Inserted new timing ID: {timing_id}")
                
                updated_timing_ids.add(timing_id)
                
                # Update shift relationships
                cursor.execute("DELETE FROM canteen_timing_shifts WHERE canteen_timing_id = ?", (timing_id,))
                
                # Get shifts for this timing
                shift_key = f'shifts_{i}[]'
                selected_shifts = request.form.getlist(shift_key)
                print(f"Selected shifts for timing {timing_id}: {selected_shifts}")
                
                # Insert new shift relationships
                for shift_id in selected_shifts:
                    cursor.execute("""
                        INSERT INTO canteen_timing_shifts (canteen_timing_id, shift_id)
                        VALUES (?, ?)
                    """, (timing_id, int(shift_id)))
                    print(f"Inserted relationship: timing={timing_id}, shift={shift_id}")
            
            # Remove timings that no longer exist
            if updated_timing_ids:
                cursor.execute("""
                    DELETE FROM canteen_timing_shifts 
                    WHERE canteen_timing_id NOT IN ({})
                """.format(','.join('?' * len(updated_timing_ids))), tuple(updated_timing_ids))
                
                cursor.execute("""
                    DELETE FROM canteen_timings 
                    WHERE id NOT IN ({})
                """.format(','.join('?' * len(updated_timing_ids))), tuple(updated_timing_ids))
            
            # Verify changes
            cursor.execute("SELECT COUNT(*) FROM canteen_timings")
            timing_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM canteen_timing_shifts")
            relationship_count = cursor.fetchone()[0]
            print(f"Final counts - Timings: {timing_count}, Relationships: {relationship_count}")
            
            cursor.execute("COMMIT")
            conn.commit()  # Ensure changes are committed
            flash("Canteen timings updated successfully.", "success")
            
        except Exception as e:
            print(f"Error in transaction: {str(e)}")
            cursor.execute("ROLLBACK")
            conn.rollback()  # Ensure rollback is complete
            flash(f"Error updating canteen timings: {str(e)}", "error")
        finally:
            conn.close()
        return redirect(url_for('system.edit_canteen_timings'))

    # GET request handling
    try:
        # Verify table structure
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'canteen_timing_shifts')
            CREATE TABLE canteen_timing_shifts (
                canteen_timing_id INT,
                shift_id INT,
                PRIMARY KEY (canteen_timing_id, shift_id),
                FOREIGN KEY (canteen_timing_id) REFERENCES canteen_timings(id),
                FOREIGN KEY (shift_id) REFERENCES shifts(id)
            )
        """)
        conn.commit()
        
        # Get shifts
        cursor.execute("""
            SELECT id, shift_name, 
                   CONVERT(varchar, start_time, 108) as start_time, 
                   CONVERT(varchar, end_time, 108) as end_time
            FROM shifts 
            ORDER BY start_time
        """)
        shifts = [dict(zip([column[0] for column in cursor.description], row)) 
                 for row in cursor.fetchall()]
        
        # Get timings with their shifts
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
        print(f"Error in GET request: {str(e)}")  # Debug print
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

        # Add this debug query at the start of live_data route
        cursor.execute("SELECT COUNT(*) FROM canteen_timings")
        count = cursor.fetchone()[0]
        print(f"Total canteen timings in database: {count}")

        cursor.execute("SELECT canteen_name, start_time, end_time FROM canteen_timings")
        all_timings = cursor.fetchall()
        print("All canteen timings:", all_timings)

        # Get current active canteen timing with formatted time
        cursor.execute("""
            SELECT 
                canteen_name,
                FORMAT(start_time, 'HH:mm') as start_time,
                FORMAT(end_time, 'HH:mm') as end_time
            FROM canteen_timings 
            WHERE CAST(GETDATE() AS time) BETWEEN start_time AND end_time
            ORDER BY start_time
        """)
        active_timings = cursor.fetchall()

        # For debugging: Print the query results
        print("Active Timings Query Result:", active_timings)
        
        # Format active timings for display
        current_timings = []
        if active_timings:
            for row in active_timings:
                current_timings.append({
                    'canteen': row.canteen_name,
                    'timing': f"{row.start_time} - {row.end_time}"
                })
        
        # If no active timings found, use dummy data for testing
        if not current_timings:
            current_timings = [
                {
                    'canteen': 'No Active Canteen',
                    'timing': '--:-- - --:--'
                }
            ]

        # Print the final current_timings for debugging
        print("Current Timings Data:", current_timings)

        return jsonify({
            'stats': {
                'total_meals': 0,  # Replace with actual count
                'active_users': 0,  # Replace with actual count
                'current_timings': current_timings
            },
            'recent_users': [],  # Your recent users data
            'canteen_stats': []  # Your canteen stats data
        })
        
    except Exception as e:
        print(f"Error in live_data: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


