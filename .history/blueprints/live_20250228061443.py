from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from datetime import datetime, time
import pyodbc

live_bp = Blueprint('live', __name__, url_prefix='/live')

def get_logger_db_conn():
    # Copy your existing database connection function
    pass

@live_bp.route('/')
def live():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    return render_template('live.html')

@live_bp.route('/data')
def get_live_data():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_logger_db_conn()
        cursor = conn.cursor()

        # Get current time
        now = datetime.now()
        today = now.date()

        # Get current shift
        cursor.execute("""
            SELECT shift_name 
            FROM shifts 
            WHERE CAST(GETDATE() AS time) BETWEEN start_time AND end_time
        """)
        current_shift = cursor.fetchone()
        current_shift = current_shift[0] if current_shift else 'No Active Shift'

        # Get today's stats
        cursor.execute("""
            SELECT 
                COUNT(*) as coupon_count,
                COUNT(DISTINCT user_id) as active_users,
                SUM(value) as total_value
            FROM coupons
            WHERE CAST(created_at AS DATE) = CAST(GETDATE() AS DATE)
        """)
        stats = cursor.fetchone()

        # Get recent activity
        cursor.execute("""
            SELECT TOP 10
                FORMAT(c.created_at, 'HH:mm:ss') as time,
                u.NM as user_name,
                c.coupon_code,
                ct.canteen_name,
                c.value,
                c.status
            FROM coupons c
            JOIN t_user u ON c.user_id = u.USRID
            LEFT JOIN canteen_timings ct ON c.canteen_timing_id = ct.id
            ORDER BY c.created_at DESC
        """)
        
        recent_activity = []
        for row in cursor.fetchall():
            recent_activity.append({
                'time': row.time,
                'user_name': row.user_name,
                'coupon_code': row.coupon_code,
                'canteen': row.canteen_name or 'N/A',
                'value': str(row.value),
                'status': row.status
            })

        return jsonify({
            'stats': {
                'today_coupons': stats[0] or 0,
                'active_users': stats[1] or 0,
                'current_shift': current_shift,
                'today_value': str(stats[2] or 0)
            },
            'recent_activity': recent_activity
        })

    except Exception as e:
        print(f"Error fetching live data: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
