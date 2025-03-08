from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from datetime import datetime
from .system import get_logger_db_conn  # Import the database connection function

live_bp = Blueprint('live', __name__, url_prefix='/live')

@live_bp.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    return render_template('live.html')

@live_bp.route('/data')
def data():  # Simplified function name
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_logger_db_conn()
        cursor = conn.cursor()
        
        # Get current stats
        cursor.execute("""
            SELECT COUNT(*) as active_users FROM userlist
        """)
        stats_row = cursor.fetchone()

        print(stats_row)
        
        # Get current shift
        cursor.execute("""
            SELECT shift_name 
            FROM shifts 
            WHERE CAST(GETDATE() AS time) BETWEEN start_time AND end_time
        """)
        current_shift = cursor.fetchone()
        
      
        recent_users = []
        
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
                'current_shift': current_shift[0] if current_shift else 'No Active Shift',
                'today_value': str(stats_row[2] or 0)
            },
            'recent_users': recent_users,
            'canteen_stats': canteen_stats
        })
        
    except Exception as e:
        print(f"Error fetching live data: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
