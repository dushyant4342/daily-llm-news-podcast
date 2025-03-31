import logging
import os
from dotenv import load_dotenv
import json
# --- Add imports ---
from datetime import datetime, date, timedelta, timezone
import pytz
# -------------------

# --- Custom Formatter for IST ---
class ISTFormatter(logging.Formatter):
    """Logging Formatter to display time in IST."""
    converter = lambda *args: datetime.now(pytz.timezone('Asia/Kolkata')).timetuple()
    default_msec_format = '%s.%03d'

    def formatTime(self, record, datefmt=None):
        """Override formatTime to use IST."""
        dt = datetime.fromtimestamp(record.created, pytz.timezone('Asia/Kolkata'))
        if datefmt:
            s = dt.strftime(datefmt)
        else:
            try:
                s = dt.isoformat(timespec='milliseconds')
            except TypeError:
                s = dt.isoformat()
        return s

    # Optional: Add timezone to default format string if not using datefmt
    # def __init__(self, fmt=None, datefmt=None, style='%', validate=True):
    #     if fmt is None:
    #         fmt = '%(asctime)s %(levelname)s [%(module)s:%(lineno)d] %(message)s'
    #     if datefmt is None:
    #         datefmt = '%Y-%m-%d %H:%M:%S,%f%z' # Example including timezone offset
    #     super().__init__(fmt=fmt, datefmt=datefmt, style=style, validate=validate)

# --------------------------------

def setup_logging():
    """Configures logging to file and console with IST timestamps."""
    log_formatter = ISTFormatter(
        fmt='%(asctime)s %(levelname)s [%(module)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S %Z' # Example format including timezone name
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO) # Set level on root logger

    # Clear existing handlers (if any) to avoid duplicates
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # File Handler
    file_handler = logging.FileHandler("workflow.log", mode='a', encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    # Suppress overly verbose logs from libraries if needed
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("imaplib").setLevel(logging.INFO)
    # logging.getLogger("llama_cpp").setLevel(logging.WARNING)


def load_config():
    """Loads configuration from .env file, including target fetch date."""
    load_dotenv()

    # --- Handle Target Date ---
    fetch_since_date_str = os.getenv("FETCH_SINCE_DATE", "")
    target_date = None
    if fetch_since_date_str:
        try:
            target_date = datetime.strptime(fetch_since_date_str, "%Y-%m-%d").date()
            logging.info(f"Target fetch date specified: {target_date.strftime('%Y-%m-%d')}")
        except ValueError:
            logging.warning(f"Invalid FETCH_SINCE_DATE format ('{fetch_since_date_str}'). Should be YYYY-MM-DD. Defaulting to yesterday.")
            target_date = None # Fallback to default

    if target_date is None: # If not specified or invalid
        target_date = date.today() - timedelta(days=1)
        logging.info(f"Using default target fetch date: {target_date.strftime('%Y-%m-%d')} (Yesterday)")
    # -------------------------

    config = {
        "gmail_email": os.getenv("GMAIL_EMAIL"),
        "gmail_password": os.getenv("GMAIL_APP_PASSWORD"),
        "target_email": os.getenv("TARGET_EMAIL"),
        "allowed_senders": json.loads(os.getenv("ALLOWED_SENDERS", '[]')),
        "local_model_path": os.getenv("LOCAL_MODEL_PATH"),
        "transcript_save_dir": os.getenv("TRANSCRIPT_SAVE_DIR", "./email_transcripts"),
        "target_date": target_date, # Store the date object
    }

    # --- Validation ---
    if not config["gmail_email"] or not config["gmail_password"]:
        logging.critical("Missing GMAIL_EMAIL or GMAIL_APP_PASSWORD in .env. Exiting.")
        exit(1)
    if not config["target_email"]:
        logging.warning("TARGET_EMAIL not set in .env. Email notifications will be disabled.")
    if not config["allowed_senders"]:
        logging.critical("ALLOWED_SENDERS is empty in .env. Cannot process emails.")
        exit(1)
    if not config["local_model_path"] or not os.path.exists(config["local_model_path"]):
         logging.error(f"LOCAL_MODEL_PATH '{config['local_model_path']}' not set or GGUF file does not exist. LLM disabled.")
         config["local_model_path"] = None
    elif not os.path.isfile(config["local_model_path"]):
         logging.error(f"LOCAL_MODEL_PATH '{config['local_model_path']}' is not a GGUF file. LLM disabled.")
         config["local_model_path"] = None
    else:
         logging.info(f"Using GGUF Model: {config['local_model_path']}")

    try:
        os.makedirs(config["transcript_save_dir"], exist_ok=True)
        logging.info(f"Transcript save directory: {config['transcript_save_dir']}")
    except OSError as e:
        logging.error(f"Could not create transcript directory '{config['transcript_save_dir']}': {e}. Transcripts will not be saved.")

    logging.info("Configuration loaded successfully.")
    logging.info(f"Allowed Senders: {config['allowed_senders']}")

    return config
