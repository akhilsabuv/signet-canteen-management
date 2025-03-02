from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash, jsonify
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
        
        # Get current stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_meals,
                COUNT(DISTINCT user_id) as active_users,
                SUM(value) as total_value
            FROM coupons 
            WHERE CAST(created_at AS DATE) = CAST(GETDATE() AS DATE)
        """)
        stats_row = cursor.fetchone()
        
        # Get current shift
        cursor.execute("""
            SELECT shift_name 
            FROM shifts 
            WHERE CAST(GETDATE() AS time) BETWEEN start_time AND end_time
        """)
        current_shift = cursor.fetchone()
        
        # Get recent users
        cursor.execute("""
            SELECT TOP 20
                u.USRID as user_id,
                u.NM as user_name,
                FORMAT(c.created_at, 'HH:mm:ss') as access_time,
                c.status
            FROM coupons c
            JOIN t_user u ON c.user_id = u.USRID
            WHERE CAST(c.created_at AS DATE) = CAST(GETDATE() AS DATE)
            ORDER BY c.created_at DESC
        """)
        recent_users = [dict(zip([column[0] for column in cursor.description], row)) 
                       for row in cursor.fetchall()]
        
        # Get canteen stats
        cursor.execute("""
            SELECT 
                ct.canteen_name,
                CONCAT(FORMAT(ct.start_time, 'HH:mm'), ' - ', FORMAT(ct.end_time, 'HH:mm')) as timing,
                COUNT(c.id) as meals_issued,
                CASE 
                    WHEN CAST(GETDATE() AS time) BETWEEN ct.start_time AND ct.end_time 
                    THEN 1 ELSE 0 
                END as is_active
            FROM canteen_timings ct
            LEFT JOIN coupons c ON c.canteen_timing_id = ct.id 
                AND CAST(c.created_at AS DATE) = CAST(GETDATE() AS DATE)
            GROUP BY ct.canteen_name, ct.start_time, ct.end_time
            ORDER BY ct.start_time
        """)
        canteen_stats = [dict(zip([column[0] for column in cursor.description], row)) 
                        for row in cursor.fetchall()]
        
        return jsonify({
            'stats': {
                'total_meals': stats_row[0] or 0,
                'active_users': stats_row[1] or 0,
                'current_shift': current_shift[0] if current_shift else 'No Active Shift'
            },
            'recent_users': recent_users,
            'canteen_stats': canteen_stats
        })
        
    except Exception as e:
        print(f"Error fetching live data: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


