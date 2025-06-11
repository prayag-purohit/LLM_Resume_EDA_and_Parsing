import os
import logging
from datetime import datetime

# Ensure log directories exist
os.makedirs("logs", exist_ok=True)
os.makedirs("logs/Errors", exist_ok=True)

# Timestamp for filenames
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
general_log = os.path.join("logs", f"resume_parser{ts}.log")
error_log   = os.path.join("logs", "Errors", f"error_resume_parser{ts}.log")

# Set up root logger with basic configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(general_log, mode="a"),
        logging.StreamHandler()
    ]
)

# Create error-only handler
err_handler = logging.FileHandler(error_log, mode="a")
err_handler.setLevel(logging.ERROR)
err_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

# Optional: to avoid adding multiple handlers if get_logger() is called multiple times
_added_error_handler = False

def get_logger(name: str = __name__) -> logging.Logger:
    """
    Get a logger with the given name and attach an error handler only once.
    """
    global _added_error_handler
    logger = logging.getLogger(name)
    if not _added_error_handler:
        logger.addHandler(err_handler)
        _added_error_handler = True
    return logger
