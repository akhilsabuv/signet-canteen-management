import json
import logging
import datetime
import win32print
import win32ui
from logging.handlers import RotatingFileHandler

# Configure logging
logging.basicConfig(
    handlers=[RotatingFileHandler('app.log', maxBytes=100000, backupCount=5)],
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_config(config_file):
    """
    Load configuration from JSON file
    """
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        logger.error(f"Config file {config_file} not found")
        # Return default configuration
        return {
            "selected_printer": win32print.GetDefaultPrinter(),
            "font_name": "Arial",
            "font_size": 10,
            "margin_left": 100,
            "margin_top": 100
        }
    except Exception as e:
        logger.error(f"Error loading config: {str(e)}")
        return {}

def log_event(message):
    """
    Log events to file
    """
    try:
        logger.info(message)
    except Exception as e:
        print(f"Logging error: {str(e)}")

def print_token(printer_name, user_id, meal_name, meal_time):
    """
    Print token with enhanced formatting
    """
    try:
        # Create printer DC
        hprinter = win32ui.CreateDC()
        hprinter.CreatePrinterDC(printer_name)
        
        # Start print job
        hprinter.StartDoc("Canteen Token")
        hprinter.StartPage()

        # Set font
        font = win32ui.CreateFont({
            "name": "Arial",
            "height": 30,
            "weight": 700
        })
        hprinter.SelectObject(font)

        # Print header
        hprinter.TextOut(100, 100, "CANTEEN TOKEN")
        
        # Change font for details
        font = win32ui.CreateFont({
            "name": "Arial",
            "height": 25,
            "weight": 400
        })
        hprinter.SelectObject(font)

        # Print details
        hprinter.TextOut(100, 200, f"User ID: {user_id}")
        hprinter.TextOut(100, 250, f"Meal: {meal_name}")
        hprinter.TextOut(100, 300, f"Time: {meal_time}")
        
        # Print footer
        hprinter.TextOut(100, 400, "=" * 40)
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hprinter.TextOut(100, 450, f"Printed: {current_time}")

        # End print job
        hprinter.EndPage()
        hprinter.EndDoc()
        hprinter.DeleteDC()

        log_event(f"Token printed successfully for User {user_id}")
        return True

    except Exception as e:
        log_event(f"Print error: {str(e)}")
        return False

def get_available_printers():
    """
    Get list of available printers
    """
    try:
        printers = [printer[2] for printer in win32print.EnumPrinters(2)]
        return printers
    except Exception as e:
        log_event(f"Error getting printers: {str(e)}")
        return []

def validate_printer(printer_name):
    """
    Validate if printer exists
    """
    try:
        printers = get_available_printers()
        return printer_name in printers
    except Exception as e:
        log_event(f"Error validating printer: {str(e)}")
        return False