import threading
import time
import webbrowser
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

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

initialize_all_tables(app)
initialize_system(app)

def background_check():
    """
    Runs continuously in a background thread.
    Every 5 seconds, updates the monitored table counts in LOGGER_DB.
    """
    with app.app_context():
        while True:
            result = update_monitored_table_counts()
            # print("Monitored table counts updated:", result)
            time.sleep(2)


def run_flask():
    # Run the Flask app without the reloader.
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

def create_icon_image():
    """Create a simple 64x64 icon image for the system tray."""
    width, height = 64, 64
    image = Image.new('RGB', (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, width-8, height-8), fill="blue")
    return image

def open_app(icon, item):
    """Open the Flask app in the default web browser."""
    webbrowser.open("http://127.0.0.1:5000")

def quit_app(icon, item):
    """Quit the tray icon and exit the program."""
    icon.stop()
    # The background threads are daemonized, so the program will exit.

def setup_tray_icon():
    """Create and run the system tray icon with a right-click menu."""
    image = create_icon_image()
    menu = (item('Open App', open_app), item('Quit', quit_app))
    icon = pystray.Icon("MyFlaskApp", image, "My Flask App", menu)
    icon.run()

if __name__ == '__main__':
    # Start the Flask app in a background thread.
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Start the background check thread.
    background_thread = threading.Thread(target=background_check)
    background_thread.daemon = True
    background_thread.start()
    
    # Optionally, wait a couple seconds for Flask to start.
    time.sleep(2)
    
    # Run the system tray icon (this will block until you quit the icon).
    setup_tray_icon()