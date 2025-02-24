from flask import current_app, jsonify, Blueprint

debug_bp = Blueprint('debug', __name__)

@debug_bp.route('/debug-config')
def debug_config():
    # Return only keys relevant to your DB settings for clarity
    keys = ['LOGGER_DB_HOST', 'LOGGER_DB_PORT', 'LOGGER_DB_USERNAME', 'LOGGER_DB_PASSWORD', 'LOGGER_DB_NAME',
            'MAIN_DB_HOST', 'MAIN_DB_PORT', 'MAIN_DB_USERNAME', 'MAIN_DB_PASSWORD', 'MAIN_DB_NAME']
    config_data = {key: current_app.config.get(key) for key in keys}
    return jsonify(config_data)
