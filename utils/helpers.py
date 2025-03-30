import logging
import os
from dotenv import load_dotenv
import json

def setup_logging():
    """Configures logging to file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s',
        handlers=[
            logging.FileHandler("workflow.log", mode='a'), # Append mode
            logging.StreamHandler()
        ]
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("imaplib").setLevel(logging.INFO)

def load_config():
    """Loads configuration from .env file."""
    load_dotenv()
    try:
        # Attempt to load LINKS_TO_PROCESS, default to 3 if missing or invalid
        links_to_process_str = os.getenv("LINKS_TO_PROCESS", "3")
        links_to_process = int(links_to_process_str)
        if links_to_process <= 0:
            logging.warning(f"LINKS_TO_PROCESS value '{links_to_process_str}' is invalid. Defaulting to 3.")
            links_to_process = 3
    except ValueError:
        logging.warning(f"LINKS_TO_PROCESS value '{links_to_process_str}' is not a valid integer. Defaulting to 3.")
        links_to_process = 3

    config = {
        "gmail_email": os.getenv("GMAIL_EMAIL"),
        "gmail_password": os.getenv("GMAIL_APP_PASSWORD"),
        "target_email": os.getenv("TARGET_EMAIL"),
        "allowed_senders": json.loads(os.getenv("ALLOWED_SENDERS", '[]')),
        # "keywords": [], # Removed keywords
        "local_model_path": os.getenv("LOCAL_MODEL_PATH"),
        "links_to_process": links_to_process, # Added
    }

    # --- Validation ---
    if not config["gmail_email"] or not config["gmail_password"]:
        logging.critical("Missing GMAIL_EMAIL or GMAIL_APP_PASSWORD in .env. Exiting.")
        exit(1)
    if not config["target_email"]:
        logging.warning("TARGET_EMAIL not set in .env. Email notifications will be disabled.")
    if not config["allowed_senders"]:
        logging.warning("ALLOWED_SENDERS is empty in .env. No emails will be fetched.")
    if not config["local_model_path"] or not os.path.exists(config["local_model_path"]):
         logging.error(f"LOCAL_MODEL_PATH '{config['local_model_path']}' not set or directory does not exist. LLM functions disabled.")
         config["local_model_path"] = None

    logging.info("Configuration loaded successfully.")
    logging.info(f"Allowed Senders: {config['allowed_senders']}")
    logging.info(f"Number of links to process: {config['links_to_process']}")
    logging.info(f"Local Model Path: {config['local_model_path'] if config['local_model_path'] else 'Disabled'}")

    return config
