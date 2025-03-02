from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, send_file
import pyodbc
import csv
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

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
    months = get_last_six_months()
    report_data = []
    
    if request.method == 'POST':
        # Get filter values
        from_date = request.form.get('from_date')
        to_date = request.form.get('to_date')
        month = request.form.get('month')
        user_id = request.form.get('user')
        
        # Build query based on filters
        query = """
            SELECT 
                FORMAT(c.created_at, 'yyyy-MM-dd') as date,
                c.coupon_code,
                u.USRID as user_id,
                u.NM as user_name,
                c.status,
                c.value
            FROM coupons c
            JOIN t_user u ON c.user_id = u.USRID
            WHERE 1=1
        """
        params = []
        
        if from_date:
            query += " AND c.created_at >= ?"
            params.append(from_date)
        if to_date:
            query += " AND c.created_at <= ?"
            params.append(to_date)
        if user_id:
            query += " AND u.USRID = ?"
            params.append(user_id)
        if month:
            # Parse month string to get year and month
            month_date = datetime.strptime(month, "%B %Y")
            query += " AND MONTH(c.created_at) = ? AND YEAR(c.created_at) = ?"
            params.extend([month_date.month, month_date.year])
            
        query += " ORDER BY c.created_at DESC"
        
        # Execute query
        try:
            conn = get_logger_db_conn()
            cursor = conn.cursor()
            cursor.execute(query, params)
            report_data = [dict(zip([column[0] for column in cursor.description], row)) 
                          for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            print(f"Error retrieving report data: {e}")
    
    return render_template('reports.html', users=users, months=months, report_data=report_data)

@reports_bp.route('/download_csv')
def download_csv():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    # Get the report data using the same logic as the main route
    # ... (implement query logic here) ...
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(['Date', 'Coupon Code', 'User ID', 'User Name', 'Status', 'Value'])
    
    # Write data
    for row in report_data:
        writer.writerow([
            row['date'],
            row['coupon_code'],
            row['user_id'],
            row['user_name'],
            row['status'],
            row['value']
        ])
    
    # Prepare response
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

@reports_bp.route('/download_pdf')
def download_pdf():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    # Get the report data using the same logic as the main route
    # ... (implement query logic here) ...
    
    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Prepare data for PDF table
    data = [['Date', 'Coupon Code', 'User ID', 'User Name', 'Status', 'Value']]
    for row in report_data:
        data.append([
            row['date'],
            row['coupon_code'],
            row['user_id'],
            row['user_name'],
            row['status'],
            row['value']
        ])
    
    # Create table
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    )
