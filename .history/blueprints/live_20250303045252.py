from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from datetime import datetime
from .system import get_logger_db_conn  # Import the database connection function



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

        # Get current time for debugging
        cursor.execute("SELECT CAST(GETDATE() AS time)")
        current_time = cursor.fetchone()[0]
        print(f"Current time: {current_time}")

        # Retrieve active canteen timings based on the current time
        cursor.execute("""
            SELECT 
                canteen_name,
                CONVERT(varchar(5), start_time, 108) as formatted_start,
                CONVERT(varchar(5), end_time, 108) as formatted_end
            FROM canteen_timings 
            WHERE CAST(GETDATE() AS time) BETWEEN start_time AND end_time
            ORDER BY start_time
        """)
        
        active_timings = cursor.fetchall()
        print("Active timings query result:", active_timings)

        current_timings = []
        if active_timings:
            for row in active_timings:
                current_timings.append({
                    'canteen': row.canteen_name,
                    'start_time': row.formatted_start,
                    'end_time': row.formatted_end
                })
        else:
            # Fallback if no active timings
            current_timings = [{
                'canteen': 'No Active Canteen',
                'start_time': '--:--',
                'end_time': '--:--'
            }]

        return jsonify({
            'stats': {
                'total_meals': 0,
                'active_users': 0,
                'current_timings': current_timings
            },
            'recent_users': [],
            'canteen_stats': []
        })
        
    except Exception as e:
        print(f"Error in live_data: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


# @live_bp.route('/')
# def index():
#     if not session.get('logged_in'):
#         return redirect(url_for('auth.login'))
#     return render_template('live.html')

# @live_bp.route('/data')
# def data():  # Simplified function name
#     if not session.get('logged_in'):
#         return jsonify({'error': 'Unauthorized'}), 401
    
#     try:
#         conn = get_logger_db_conn()
#         cursor = conn.cursor()
        
#         # Get current stats
#         cursor.execute("""
#             SELECT 
#                 COUNT(*) as total_meals,
#                 COUNT(DISTINCT user_id) as active_users,
#                 SUM(value) as total_value
#             FROM coupons 
#             WHERE CAST(created_at AS DATE) = CAST(GETDATE() AS DATE)
#         """)
#         stats_row = cursor.fetchone()
        
#         # Get current shift
#         cursor.execute("""
#             SELECT shift_name 
#             FROM shifts 
#             WHERE CAST(GETDATE() AS time) BETWEEN start_time AND end_time
#         """)
#         current_shift = cursor.fetchone()
        
#         # Get recent users
#         cursor.execute("""
#             SELECT TOP 20
#                 u.USRID as user_id,
#                 u.NM as user_name,
#                 FORMAT(c.created_at, 'HH:mm:ss') as access_time,
#                 c.status
#             FROM coupons c
#             JOIN t_user u ON c.user_id = u.USRID
#             WHERE CAST(c.created_at AS DATE) = CAST(GETDATE() AS DATE)
#             ORDER BY c.created_at DESC
#         """)
#         recent_users = [dict(zip([column[0] for column in cursor.description], row)) 
#                        for row in cursor.fetchall()]
        
#         # Get canteen stats
#         cursor.execute("""
#             SELECT 
#                 ct.canteen_name,
#                 CONCAT(FORMAT(ct.start_time, 'HH:mm'), ' - ', FORMAT(ct.end_time, 'HH:mm')) as timing,
#                 COUNT(c.id) as meals_issued,
#                 CASE 
#                     WHEN CAST(GETDATE() AS time) BETWEEN ct.start_time AND ct.end_time 
#                     THEN 1 ELSE 0 
#                 END as is_active
#             FROM canteen_timings ct
#             LEFT JOIN coupons c ON c.canteen_timing_id = ct.id 
#                 AND CAST(c.created_at AS DATE) = CAST(GETDATE() AS DATE)
#             GROUP BY ct.canteen_name, ct.start_time, ct.end_time
#             ORDER BY ct.start_time
#         """)
#         canteen_stats = [dict(zip([column[0] for column in cursor.description], row)) 
#                         for row in cursor.fetchall()]
        
#         return jsonify({
#             'stats': {
#                 'total_meals': stats_row[0] or 0,
#                 'active_users': stats_row[1] or 0,
#                 'current_shift': current_shift[0] if current_shift else 'No Active Shift',
#                 'today_value': str(stats_row[2] or 0)
#             },
#             'recent_users': recent_users,
#             'canteen_stats': canteen_stats
#         })
        
#     except Exception as e:
#         print(f"Error fetching live data: {e}")
#         return jsonify({'error': str(e)}), 500
#     finally:
#         conn.close()


# monitor table()
#     every 2 seconds check for any changes in the monitored table






# if check for any update in monitered tables with cateen device id
#     get user id from the table
#     if user id:
#         load check eligibiliy(user id)
#     else
#         pass
# else
#     pass


# check elegibility(user id)
#     if check for attentance_elegibility()  && check for duplication()
#         value=add to log("success", user id)
#         print token generator(value)
#     else
#         add to log(error, user id)