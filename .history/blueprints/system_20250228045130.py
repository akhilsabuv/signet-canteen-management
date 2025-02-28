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

@system_bp.route('/canteen_timings', methods=['GET', 'POST'])
def edit_canteen_timings():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        try:
            # Start with deleting all existing records
            cursor.execute("DELETE FROM canteen_timings")
            
            # Process existing entries
            for key, value in request.form.items():
                if key.startswith("canteen_name_") and not key.startswith("new_"):
                    idx = key.split("_")[-1]
                    canteen_name = request.form.get(f"canteen_name_{idx}")
                    start_time = request.form.get(f"start_time_{idx}")
                    end_time = request.form.get(f"end_time_{idx}")
                    description = request.form.get(f"description_{idx}")
                    
                    if canteen_name and start_time and end_time:  # Basic validation
                        cursor.execute("""
                            INSERT INTO canteen_timings (canteen_name, start_time, end_time, description)
                            VALUES (?, ?, ?, ?)
                        """, (canteen_name, start_time, end_time, description))
            
            # Process new entries
            new_names = request.form.getlist("new_canteen_name[]")
            new_starts = request.form.getlist("new_start_time[]")
            new_ends = request.form.getlist("new_end_time[]")
            new_descs = request.form.getlist("new_description[]")
            
            for i in range(len(new_names)):
                if new_names[i].strip():  # Only insert if name is not empty
                    cursor.execute("""
                        INSERT INTO canteen_timings (canteen_name, start_time, end_time, description)
                        VALUES (?, ?, ?, ?)
                    """, (new_names[i], new_starts[i], new_ends[i], new_descs[i] if i < len(new_descs) else ''))
            
            conn.commit()
            flash("Canteen timings updated successfully.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error updating canteen timings: {str(e)}", "error")
            print(f"Error updating canteen timings: {str(e)}")  # For debugging
        finally:
            conn.close()
        return redirect(url_for('system.edit_canteen_timings'))
    
    # GET request - display current timings
    try:
        cursor.execute("""
            SELECT id, canteen_name, 
                   CONVERT(varchar, start_time, 108) as start_time, 
                   CONVERT(varchar, end_time, 108) as end_time, 
                   description 
            FROM canteen_timings 
            ORDER BY id
        """)
        timings = cursor.fetchall()
    except Exception as e:
        timings = []
        flash(f"Error retrieving canteen timings: {str(e)}", "error")
    finally:
        conn.close()
    
    return render_template('edit_canteen_timings.html', timings=timings)

@system_bp.route('/shifts', methods=['GET', 'POST'])
def edit_shifts():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    conn = get_logger_db_conn()
    cursor = conn.cursor()
    if request.method == 'POST':
        try:
            cursor.execute("DELETE FROM shifts")
            for key in request.form:
                if key.startswith("shift_name_"):
                    idx = key.split("_")[-1]
                    shift_name = request.form.get(f"shift_name_{idx}")
                    start_time = request.form.get(f"shift_start_{idx}")
                    end_time = request.form.get(f"shift_end_{idx}")
                    insert_sql = """
                        INSERT INTO shifts (shift_name, start_time, end_time)
                        VALUES (?, ?, ?)
                    """
                    cursor.execute(insert_sql, (shift_name, start_time, end_time))
            conn.commit()
            flash("Shifts updated successfully.", "success")
        except Exception as e:
            flash(f"Error updating shifts: {e}", "error")
        return redirect(url_for('system.edit_shifts'))
    
    try:
        cursor.execute("SELECT id, shift_name, CONVERT(varchar, start_time, 108) as start_time, CONVERT(varchar, end_time, 108) as end_time FROM shifts ORDER BY id")
        shifts = cursor.fetchall()
    except Exception as e:
        shifts = []
        flash(f"Error retrieving shifts: {e}", "error")
    conn.close()
    return render_template('edit_shifts.html', shifts=shifts)


