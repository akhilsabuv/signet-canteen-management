import bcrypt
import pyodbc
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash

auth_bp = Blueprint('auth', __name__)

def get_user(username):
    """
    Query the login table for a given username.
    Assumes the table 'login' has columns: username, password_hash, user_type.
    """
    config = current_app.config
    host = config.get('LOGGER_DB_HOST')       # Or change this if your login table is in another DB.
    username_db = config.get('LOGGER_DB_USERNAME')
    password_db = config.get('LOGGER_DB_PASSWORD')
    dbname = config.get('LOGGER_DB_NAME')
    
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={username_db};PWD={password_db}"
    )
    query = "SELECT username, password_hash, user_type FROM login WHERE username = ?;"
    
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute(query, (username,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "username": row.username, 
                "password_hash": row.password_hash,
                "user_type": row.user_type
            }
        else:
            return None
    except Exception as e:
        print("Error retrieving user:", e)
        return None

def update_password(username, new_password_hash):
    """
    Updates the password_hash for the given username in the login table.
    """
    config = current_app.config
    host = config.get('MAIN_DB_HOST')
    dbname = config.get('MAIN_DB_NAME')
    db_user = config.get('MAIN_DB_USERNAME')
    db_pass = config.get('MAIN_DB_PASSWORD')
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={db_user};PWD={db_pass}"
    )
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("UPDATE login SET password_hash = ? WHERE username = ?", (new_password_hash, username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error updating password:", e)
        return False

def create_user(username, password_hash, user_type):
    """
    Creates a new user in the login table.
    """
    config = current_app.config
    host = config.get('LOGGER_DB_HOST')
    dbname = config.get('LOGGER_DB_NAME')
    db_user = config.get('LOGGER_DB_USERNAME')
    db_pass = config.get('LOGGER_DB_PASSWORD')
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={db_user};PWD={db_pass}"
    )
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO login (username, password_hash, user_type) VALUES (?, ?, ?)",
            (username, password_hash, user_type)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error creating user:", e)
        return False

@auth_bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    """
    Allows a logged-in user to change their password.
    The user must provide the current password, a new password, and a confirmation.
    The new password is hashed and then updated in the database.
    """
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        username = session.get('username')
        
        # Ensure new password and confirmation match.
        if new_password != confirm_password:
            flash("New password and confirmation do not match.", "error")
            return redirect(url_for('auth.change_password'))
        
        # Retrieve the user record.
        user = get_user(username)
        if not user:
            flash("User not found.", "error")
            return redirect(url_for('auth.change_password'))
        
        stored_hash = user["password_hash"].encode('utf-8')
        # Verify the current password.
        if not bcrypt.checkpw(current_password.encode('utf-8'), stored_hash):
            flash("Current password is incorrect.", "error")
            return redirect(url_for('auth.change_password'))
        
        # Hash the new password and update in the database.
        new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        if update_password(username, new_hash):
            flash("Password updated successfully.", "success")
        else:
            flash("Error updating password.", "error")
        return redirect(url_for('auth.change_password'))
    
    return render_template('change_password.html')

@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    """
    Renders the login page and processes login submissions.
    If the provided credentials match the stored hash, the user is logged in.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
      
        user = get_user(username)
        print(user)
        if user:
            stored_hash = user["password_hash"].encode('utf-8')
            if bcrypt.checkpw(password.encode('utf-8'), stored_hash):
                session['logged_in'] = True
                session['username'] = username
                session['user_type'] = user['user_type']
                return redirect(url_for('dashboard.dashboard'))
            else:
                flash("Invalid username or password", "error")
        else:
            flash("Invalid username or password", "error")
        return redirect(url_for('auth.login'))
    
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """
    Logs out the current user by clearing the session and redirecting to login.
    """
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/manage-users', methods=['GET', 'POST'])
def manage_users():
    """
    Interface for administrators to manage users.
    Only accessible to users with admin type.
    """
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    # Check if current user is admin
    current_user = get_user(session.get('username'))
    if not current_user or current_user['user_type'] != 'admin':
        flash("Unauthorized access", "error")
        return redirect(url_for('dashboard.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_type = request.form.get('user_type')
        
        # Basic validation
        if not all([username, password, user_type]):
            flash("All fields are required", "error")
            return redirect(url_for('auth.manage_users'))
        
        # Check if user already exists
        if get_user(username):
            flash("Username already exists", "error")
            return redirect(url_for('auth.manage_users'))
        
        # Create new user
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        if create_user(username, password_hash, user_type):
            flash("User created successfully", "success")
        else:
            flash("Error creating user", "error")
        return redirect(url_for('auth.manage_users'))
    
    # For GET request, fetch all users for display
    users = get_all_users()
    return render_template('manage_users.html', users=users)

def get_all_users():
    """
    Retrieves all users from the login table (excluding password hashes).
    """
    config = current_app.config
    host = config.get('MAIN_DB_HOST')
    dbname = config.get('MAIN_DB_NAME')
    db_user = config.get('MAIN_DB_USERNAME')
    db_pass = config.get('MAIN_DB_PASSWORD')
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={db_user};PWD={db_pass}"
    )
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT username, user_type FROM login")
        users = [{"username": row.username, "user_type": row.user_type} for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception as e:
        print("Error retrieving users:", e)
        return []
