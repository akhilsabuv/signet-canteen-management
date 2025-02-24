import json
import os

class Config(object):
    # Default values (you can set them to non-null defaults if needed)
    DEBUG = True
    SECRET_KEY = 'default_secret_key'
    
    # Logger Database settings
    LOGGER_DB_HOST = 'localhost'
    LOGGER_DB_PORT = 1433
    LOGGER_DB_USERNAME = 'logger_user'
    LOGGER_DB_PASSWORD = 'logger_pass'
    LOGGER_DB_NAME = 'logger_db'
    
    # Main Database settings
    MAIN_DB_HOST = 'localhost'
    MAIN_DB_PORT = 1433
    MAIN_DB_USERNAME = 'main_user'
    MAIN_DB_PASSWORD = 'main_pass'
    MAIN_DB_NAME = 'main_db'
    
    # Printer settings
    DEFAULT_PRINTER = 'Printer A'
    TABLE_PREFIX = 't_lg'

    
    # New Time Zone configuration.
    TIME_ZONE = os.environ.get('TIME_ZONE', 'UTC')  # e.g., 'America/New_York' or 'Asia/Kolkata'
    
    @classmethod
    def load(cls, config_file='config.json'):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_file)
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                data = json.load(f)
            print("Loaded JSON config:", data)
            for key, value in data.items():
                setattr(cls, key, value)
            print("Configuration updated from", config_path)
        else:
            print("Configuration file not found:", config_path)

def get_current_time_in_timezone():
    """
    Returns the current datetime in the configured TIME_ZONE.
    """
    tz = pytz.timezone(Config.TIME_ZONE)
    return datetime.now(tz)

def convert_to_config_timezone(dt):
    """
    Converts the given datetime (assumed to be aware or in UTC) to the configured TIME_ZONE.
    """
    tz = pytz.timezone(Config.TIME_ZONE)
    return dt.astimezone(tz)

# Automatically load configuration from config.json when this module is imported.
Config.load()