import threading
import time

from flask import Flask
from config import Config
from blueprints.auth import auth_bp
from blueprints.dashboard import dashboard_bp
from blueprints.configuration import configuration_bp
from blueprints.devices import devices_bp
from blueprints.reports import reports_bp
from blueprints.debug_bp import debug_bp
from blueprints.monitored_tables import monitored_tables_bp, update_monitored_table_counts
from blueprints.initialize_db import initialize_all_tables
from blueprints.initialize_system import initialize_system
from blueprints.system import system_bp
from blueprints.live import live_bp

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = 'a_very_secret_key'  # This can be overridden by your JSON config if needed

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(configuration_bp)
app.register_blueprint(devices_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(debug_bp)
app.register_blueprint(monitored_tables_bp)
app.register_blueprint(system_bp)
app.register_blueprint(live_bp)

initialize_all_tables(app)
initialize_system(app)

def background_check():
    """
    Periodically (every 60 seconds) updates the monitored table counts in LOGGER_DB.
    This function should be run in a background thread.
    """
    with app.app_context():
        while True:
            # Call your update function (defined in monitored_tables.py)
            result = update_monitored_table_counts()
            # print("Monitored table counts updated:", result)
            time.sleep(2)  # Wait 60 seconds before checking again.

# Start the background thread as a daemon so it doesn't block shutdown.
threading.Thread(target=background_check, daemon=True).start()


if __name__ == '__main__':
    app.run(debug=True)