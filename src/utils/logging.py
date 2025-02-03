import logging
import os

# Create logs directory if it doesn't exist
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Define log file path
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# Configure logging
logging.basicConfig(
    filename=LOG_FILE,
    filemode="a",
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

# Create logger instance
logger = logging.getLogger("product-search-ai")

# Enable logging to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(console_handler)
