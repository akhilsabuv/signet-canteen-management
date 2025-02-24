from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app
import pyodbc

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

def get_last_six_months():
    """Return a list of the last six months (including the current month) in descending order."""
    now = datetime.now()
    months = []
    year = now.year
    month = now.month
    for i in range(6):
        dt = datetime(year, month, 1)
        months.append(dt.strftime("%B %Y"))  # e.g. "September 2023"
        # Move to previous month
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return months

def get_users():
    """
    Connect to the Main DB using MSSQL connection parameters from Flask config,
    retrieve USRID and NM from the t_user table, and return a list of dictionaries.
    """
    config = current_app.config
    host = config.get('MAIN_DB_HOST')
    port = config.get('MAIN_DB_PORT')
    username = config.get('MAIN_DB_USERNAME')
    password = config.get('MAIN_DB_PASSWORD')
    dbname = config.get('MAIN_DB_NAME')
    
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host},{port};"
        f"DATABASE={dbname};"
        f"UID={username};PWD={password}"
    )
    
    query = "SELECT USRID, NM FROM t_user ORDER BY NM;"
    
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute(query)
        users = []
        for row in cursor.fetchall():
            users.append({
                "USRID": row.USRID,
                "NM": row.NM
            })
        conn.close()
        return users
    except Exception as e:
        print("Error retrieving users:", e)
        return []

@reports_bp.route('/', methods=['GET', 'POST'])
def reports():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    users = get_users()
    months = get_last_six_months()  # Get the last six months (most recent first)
    
    if request.method == 'POST':
        # Process report filters here...
        return redirect(url_for('reports.reports'))
    
    return render_template('reports.html', users=users, months=months)
