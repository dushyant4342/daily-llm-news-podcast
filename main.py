import schedule
import time
import logging
# --- Add datetime, timedelta, timezone ---
from datetime import date, timedelta, datetime
import pytz
# -----------------------------------------
import os
import re

# Import utility functions and core classes
from utils.helpers import setup_logging, load_config
from llm.local_llm import LocalLLM
from core.email_reader import EmailReader
from core.content_processor import ContentProcessor
from core.audio_generator import AudioGenerator
from core.output_manager import OutputManager

def daily_workflow(config):
    """
    Fetches emails from allowed senders SINCE target_date, cleans the body,
    summarizes, saves transcript, creates audio FROM SUMMARY,
    generates Excel, and emails results. Uses IST timestamps.
    """
    logging.info("--- Starting Daily Workflow (Processing Email Bodies) ---")
    start_time = time.time()

    # --- Get Target Date and Generate Timestamps ---
    target_date = config['target_date'] # Date object from config (defaults to yesterday)
    report_date_str = target_date.strftime("%Y-%m-%d") # For reporting (e.g., 2025-03-29)

    ist_tz = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist_tz)
    # Timestamp string for filenames (ensures uniqueness for each run)
    timestamp_str = now_ist.strftime("%Y%m%d_%H%M%S_%Z")
    logging.info(f"Workflow run timestamp (IST): {timestamp_str}")
    logging.info(f"Processing emails received since: {target_date.strftime('%Y-%m-%d')}")
    # -------------------------------------------------

    # --- Initialization ---
    email_reader = EmailReader(config["gmail_email"], config["gmail_password"])
    llm = LocalLLM(config["local_model_path"])
    content_processor = ContentProcessor(llm)
    audio_generator = AudioGenerator()
    output_manager = OutputManager(
        config["gmail_email"], config["gmail_password"],
        config["target_email"], config["transcript_save_dir"]
    )

    processed_email_data = []
    summary_mp3_paths = []
    files_to_cleanup = []

    try:
        # --- 1. Fetch Emails Since Target Date ---
        if not email_reader.connect(): logging.error("Email connection failed."); return

        # Pass the target_date object to the fetching method
        emails_to_process = email_reader.fetch_emails_since(
            config["allowed_senders"],
            target_date=target_date
        )
        email_reader.disconnect()

        if not emails_to_process:
            logging.info(f"No emails found from allowed senders since {report_date_str}. Workflow finished.")
            return

        logging.info(f"Found {len(emails_to_process)} emails to process.")

        # --- 2. Process Each Email ---
        email_count = 0
        successful_summaries = 0

        for email_data in emails_to_process:
            email_count += 1
            sender = email_data.get('from', 'Unknown Sender')
            subject = email_data.get('subject', 'No Subject')
            raw_body = email_data.get('body', '')

            logging.info(f"--- Processing email {email_count}/{len(emails_to_process)} from: {sender} | Subject: {subject} ---")
            if not raw_body: logging.warning("Empty body. Skipping."); continue

            cleaned_body, summary_text = content_processor.clean_and_summarize_email_body(raw_body)

            if not cleaned_body:
                 logging.warning(f"Cleaning failed/empty for email from {sender}. Skipping.")
                 processed_email_data.append({
                     "sender": sender, "summary": "Error: Cleaning failed.", "cleaned_content": ""
                 })
                 continue

            # Save transcript using timestamp
            output_manager.save_transcript(sender, subject, cleaned_body, report_date_str, timestamp_str)

            summary_successful = summary_text and not summary_text.startswith("Error:")
            if summary_successful:
                 successful_summaries += 1
                 logging.info(f"Summary generated successfully for email from {sender}.")
                 # Generate audio using timestamp
                 filename_base = f"summary_{email_count}_" + re.sub(r'[^a-zA-Z0-9_-]', '_', subject)[:40]
                 mp3_path = audio_generator.text_to_speech(summary_text, filename_base, timestamp_str) # Pass timestamp
                 if mp3_path:
                     summary_mp3_paths.append(mp3_path)
                     files_to_cleanup.append(mp3_path)
                 else:
                     logging.warning(f"Audio generation failed for summary of email from {sender}.")
            else:
                 logging.warning(f"Summarization failed for email from {sender}. Summary: {summary_text}")

            processed_email_data.append({
                "sender": sender, "summary": summary_text, "cleaned_content": cleaned_body
            })


        if not processed_email_data:
             logging.info("No emails were processed. Workflow finished.")
             return

        logging.info(f"Finished processing. Summarized {successful_summaries}/{len(emails_to_process)} emails.")

        # --- 3. Create Excel Report ---
        excel_path = output_manager.create_excel(
            processed_email_data,
            report_date_str=report_date_str,
            timestamp_str=timestamp_str # Pass timestamp
        )
        if excel_path: files_to_cleanup.append(excel_path)

        # --- 4. Send Email ---
        email_subject = f"Email Summaries & Audio for {report_date_str} ({successful_summaries} processed) - Run {timestamp_str}" # Add timestamp to subject
        email_body = f"Processed {len(emails_to_process)} emails from allowed senders received since {report_date_str}.\n"
        email_body += f"Successfully generated summaries for {successful_summaries} emails.\n\n"
        email_body += f"Cleaned transcripts saved locally to: {config['transcript_save_dir']}\n"
        # ... (rest of email body generation same as before) ...
        if excel_path: email_body += f"Summary report attached.\n"
        else: email_body += "Failed to generate Excel report.\n"
        if summary_mp3_paths: email_body += f"Attaching {len(summary_mp3_paths)} summary MP3s.\n"
        else: email_body += "No MP3s generated.\n"
        email_body += "\n--- Summary Snippets --- \n"
        snippet_count = 0; max_snippets = 5
        for i, data in enumerate(processed_email_data):
             if snippet_count < max_snippets and not data['summary'].startswith("Error:"):
                  email_body += f"\n{i+1}. From: {data['sender']}\n   Summary: {data['summary'][:250]}...\n"
                  snippet_count += 1
        files_for_email = [];
        if excel_path: files_for_email.append(excel_path)
        files_for_email.extend(summary_mp3_paths)
        output_manager.send_email(email_subject, email_body, files_for_email)

    # --- Exception handling remains the same ---
    except Exception as e:
        logging.critical(f"An unexpected error occurred: {e}", exc_info=True)
        try:
            error_subject = f"ERROR in Daily Email Workflow - {report_date_str} - {timestamp_str}"
            error_body = f"Workflow encountered an error on {report_date_str}.\nRun Timestamp: {timestamp_str}\nError:\n{e}\nCheck logs."
            if 'output_manager' in locals(): output_manager.send_email(error_subject, error_body, [])
            else:
                 temp_output_manager = OutputManager(config["gmail_email"], config["gmail_password"], config["target_email"], config["transcript_save_dir"])
                 temp_output_manager.send_email(error_subject, error_body, [])
        except Exception as email_err: logging.error(f"Failed to send error email: {email_err}")

    finally:
        # --- Cleanup ---
        if 'output_manager' in locals() and 'files_to_cleanup' in locals():
            output_manager.cleanup_files(files_to_cleanup)
        if 'email_reader' in locals() and email_reader.connected:
             email_reader.disconnect()
        end_time = time.time()
        logging.info(f"--- Daily Workflow Finished. Total time: {end_time - start_time:.2f} seconds ---")


# --- Main Execution Block ---
if __name__ == "__main__":
    setup_logging() # Setup logging with IST formatter
    logging.info("=============================================")
    logging.info(" Starting Modular Email Processor Script ")
    logging.info("=============================================")
    try:
        config = load_config()
        logging.info(f"Running workflow immediately (processing emails since {config['target_date'].strftime('%Y-%m-%d')})...")
        daily_workflow(config)
        logging.info("Workflow run complete.")
    except FileNotFoundError as e: logging.critical(f"CRITICAL ERROR: Missing required file: {e}.")
    except ImportError as e: logging.critical(f"CRITICAL ERROR: Missing required library: {e}. ({e})")
    except KeyboardInterrupt: logging.info("Script interrupted by user. Exiting gracefully.")
    except Exception as e: logging.critical(f"An unexpected critical error occurred at startup: {e}", exc_info=True)
    logging.info("Script finished.")
