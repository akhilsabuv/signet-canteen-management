import os
import json
import win32print
import pytz
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash

configuration_bp = Blueprint('configuration', __name__, url_prefix='/configuration')

# Path to the JSON config file (adjust as needed)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config.json')

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def get_available_printers():
    """Returns a list of available printers using win32print."""
    printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS, None, 2)
    printer_names = [printer["pPrinterName"] for printer in printers]
    return printer_names

@configuration_bp.route('/', methods=['GET', 'POST'])
def configuration():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))

    # Load the current configuration from the JSON file
    config_data = load_config()

    if request.method == 'POST':
        # Update the configuration with the form data
        try:
            config_data['LOGGER_DB_HOST'] = request.form.get('logger_db_host')
            config_data['LOGGER_DB_PORT'] = int(request.form.get('logger_db_port'))
            config_data['LOGGER_DB_USERNAME'] = request.form.get('logger_db_username')
            config_data['LOGGER_DB_PASSWORD'] = request.form.get('logger_db_password')
            config_data['LOGGER_DB_NAME'] = request.form.get('logger_db_name')
            config_data['MAIN_DB_HOST'] = request.form.get('main_db_host')
            config_data['MAIN_DB_PORT'] = int(request.form.get('main_db_port'))
            config_data['MAIN_DB_USERNAME'] = request.form.get('main_db_username')
            config_data['MAIN_DB_PASSWORD'] = request.form.get('main_db_password')
            config_data['MAIN_DB_NAME'] = request.form.get('main_db_name')
            config_data['DEFAULT_PRINTER'] = request.form.get('default_printer')
            config_data['TABLE_PREFIX'] = request.form.get('table_prefix')
            config_data['TIME_ZONE'] = request.form.get('TIME_ZONE')
        except Exception as e:
            flash("Error processing input: " + str(e), "error")
            return redirect(url_for('configuration.configuration'))

        # Save the updated configuration to file
        save_config(config_data)
        current_app.config.update(config_data)
        flash("Configuration updated successfully.", "success")
        return redirect(url_for('configuration.configuration'))

    # Get dynamic printer list
    printers = get_available_printers()
    timezones = pytz.all_timezones
    return render_template('configuration.html', config=config_data, printers=printers, timezones=timezones)
