import pyodbc
import bcrypt
from flask import current_app

def hash_password(plain_password):
    """Return a bcrypt hashed password."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def ensure_logger_db_tables():
    """
    Ensures that the required tables exist in the Logger Database ([signet_log]).
    In this example, we create a 'sig_users' table to store user credentials.
    """
    config = current_app.config
    host = config.get('LOGGER_DB_HOST')
    username = config.get('LOGGER_DB_USERNAME')
    password = config.get('LOGGER_DB_PASSWORD')
    dbname = config.get('LOGGER_DB_NAME')  # Should be set to 'signet_log'
    
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={username};PWD={password}"
    )
    
    # Create the login table if it doesn't exist.
    sig_users_sql = """
        CREATE TABLE login (
            id INT IDENTITY(1,1) PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            user_type VARCHAR(50) NOT NULL DEFAULT 'user',
            created_at DATETIME DEFAULT GETDATE()
        );
    """
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sys.tables WHERE name = 'login'")
        table_count = cursor.fetchone()[0]
        print("login table count:", table_count)
        if table_count == 0:
            cursor.execute(sig_users_sql)
            conn.commit()
            print("Created login table in LOGGER_DB ([signet_log]).")
        else:
            print("login table already exists in LOGGER_DB ([signet_log]).")
        conn.close()
    except Exception as e:
        print("Error initializing LOGGER_DB tables:", e)

def create_initial_admin():
    """
    Creates an initial admin user (username: "admin", password: "admin")
    in the sig_users table (in [signet_log]) if no such user exists.
    """
    config = current_app.config
    host = config.get('LOGGER_DB_HOST')
    username_db = config.get('LOGGER_DB_USERNAME')
    password_db = config.get('LOGGER_DB_PASSWORD')
    dbname = config.get('LOGGER_DB_NAME')  # Should be 'signet_log'
    
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host};"
        f"DATABASE={dbname};"
        f"UID={username_db};PWD={password_db}"
    )
    
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM login WHERE username = ?", ("admin",))
        admin_count = cursor.fetchone()[0]
        print("Admin count from login:", admin_count)
        if admin_count == 0:
            hashed_password = hash_password("admin")
            insert_sql = "INSERT INTO login (username, password_hash, user_type) VALUES (?, ?, ?)"
            cursor.execute(insert_sql, ("admin", hashed_password, "admin"))
            conn.commit()
            print("Initial admin user created in login (admin/admin).")
        else:
            print("Admin user already exists in login.")
        conn.close()
    except Exception as e:
        print("Error creating initial admin user:", e)

def initialize_all_tables(app):
    """
    Initialize the required tables in the Logger Database and create the initial admin.
    This function should be called within an app context.
    """
    with app.app_context():
        ensure_logger_db_tables()
        create_initial_admin()

if __name__ == "__main__":
    from app import app  # Make sure your app.py creates your Flask app and loads config
    initialize_all_tables(app)
