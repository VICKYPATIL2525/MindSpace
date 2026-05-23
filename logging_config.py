"""
Logging configuration for MindSpace project
Logs all changes to changes.log in the root directory
"""
import logging
import logging.handlers
import os
from datetime import datetime

# Get root directory
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(ROOT_DIR, 'changes.log')

def setup_logging():
    """
    Configure logging for the project
    Creates a logger that logs to changes.log with timestamps
    """
    # Create logger
    logger = logging.getLogger('mindspace')
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers = []
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler - RotatingFileHandler to manage log size
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=5  # Keep 5 backup files
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Console handler (optional)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(detailed_formatter)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger on import
change_logger = setup_logging()

def log_change(module, action, details=''):
    """
    Log a change with consistent format
    
    Args:
        module (str): Module/file name where change occurred
        action (str): Type of action (CREATE, UPDATE, DELETE, etc.)
        details (str): Additional details about the change
    """
    message = f"[{module}] {action}"
    if details:
        message += f" - {details}"
    change_logger.info(message)

def log_error(module, error_msg, exception=None):
    """Log an error"""
    if exception:
        change_logger.error(f"[{module}] ERROR: {error_msg}", exc_info=exception)
    else:
        change_logger.error(f"[{module}] ERROR: {error_msg}")

def log_warning(module, warning_msg):
    """Log a warning"""
    change_logger.warning(f"[{module}] WARNING: {warning_msg}")

def log_debug(module, debug_msg):
    """Log debug information"""
    change_logger.debug(f"[{module}] {debug_msg}")
