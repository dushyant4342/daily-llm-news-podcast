import schedule
import time
import logging
from datetime import date
import os
import re

# Import utility functions and core classes
from utils.helpers import setup_logging, load_config
from llm.local_llm import LocalLLM
from core.email_reader import EmailReader
from core.content_processor import ContentProcessor # Still needed for fetch+summarize
from core.audio_generator import AudioGenerator
from core.output_manager import OutputManager

def daily_workflow(config):
    """
    The main daily workflow function.
    Fetches emails, takes the first N links found (no filtering),
    summarizes (~200 words), creates audio FROM SUMMARY, generates Excel, and emails results.
    """
    logging.info("--- Starting Daily Workflow (No Link Filtering) ---")
    start_time = time.time()
    today_str = date.today().strftime("%Y-%m-%d")
    num_links_to_process = config["links_to_process"]

    # --- Initialization ---
    email_reader = EmailReader(
        config["gmail_email"],
        config["gmail_password"]
    )
    llm = LocalLLM(config["local_model_path"])
    # ContentProcessor no longer needs keywords, just LLM
    content_processor = ContentProcessor(llm)
    audio_generator = AudioGenerator()
    output_manager = OutputManager(config["gmail_email"], config["gmail_password"], config["target_email"])

    processed_articles_data = [] # Store dicts with {'link': url, 'summary': text}
    summary_mp3_paths = [] # Store paths of generated MP3s (from summaries)
    files_to_cleanup = [] # Keep track of all temp files (Excel + MP3s)

    try:
        # --- 1. Fetch Emails & Extract ALL Links ---
        if not email_reader.connect():
            logging.error("Failed to connect to email server. Aborting workflow.")
            return

        emails = email_reader.fetch_today_emails(config["allowed_senders"])
        all_extracted_links = []
        for email_data in emails:
            # extract_links_from_text now gets ALL http/https links
            links_in_email = email_reader.extract_links_from_text(email_data['body'])
            # Maintain order reasonably well by extending list (set loses order)
            for link in links_in_email:
                 if link not in all_extracted_links: # Keep uniqueness
                      all_extracted_links.append(link)

        email_reader.disconnect()

        if not all_extracted_links:
            logging.info("No HTTP/HTTPS links found in today's emails. Workflow finished.")
            return

        # --- Limit to first N links ---
        links_to_process = all_extracted_links[:num_links_to_process]
        logging.info(f"Found {len(all_extracted_links)} unique links. Processing the first {len(links_to_process)}.")
        # -----------------------------

        # --- 2. Process Top N Links (Fetch, Summarize ~200 words, Generate Audio from Summary) ---
        processed_link_count = 0
        links_processed_successfully = 0

        for link in links_to_process:
            processed_link_count += 1
            logging.info(f"--- Processing link {processed_link_count}/{len(links_to_process)}: {link} ---")
            # process_link now just fetches and summarizes
            processed_result = content_processor.process_link(link)

            # Check if processing (fetch + summary) was successful
            if processed_result and processed_result.get("summary") and not processed_result["summary"].startswith("Error:"):
                summary_text = processed_result["summary"]
                logging.info(f"Successfully processed and summarized: {link}")

                # Store data for Excel
                processed_articles_data.append({
                    "link": link,
                    "summary": summary_text
                })
                links_processed_successfully += 1

                # Generate audio FROM THE SUMMARY
                logging.info(f"Attempting audio generation for summary of: {link}")
                filename_base = f"summary_{processed_link_count}_" + re.sub(r'[^a-zA-Z0-9_-]', '_', link.split("//")[-1])[:40]
                mp3_path = audio_generator.text_to_speech(summary_text, filename_base)
                if mp3_path:
                    summary_mp3_paths.append(mp3_path)
                    files_to_cleanup.append(mp3_path)
                else:
                    logging.warning(f"Audio generation failed for summary of: {link}")

            else:
                # Log failure (fetch or summary failed)
                logging.warning(f"Failed to process or summarize link: {link}. Summary result: {processed_result.get('summary', 'N/A') if processed_result else 'Fetch Failed'}")


        if not processed_articles_data:
             logging.info("None of the first {num_links_to_process} links could be successfully processed and summarized. Workflow finished.")
             return

        logging.info(f"Finished processing. Successfully summarized {links_processed_successfully} links.")

        # --- 3. Create Excel Report (with Summaries) ---
        excel_filename = f"First_{links_processed_successfully}_Links_Summary_{today_str}.xlsx"
        excel_path = output_manager.create_excel(processed_articles_data, filename=excel_filename)
        if excel_path:
            files_to_cleanup.append(excel_path)

        # --- 4. Send Email with Attachments ---
        email_subject = f"Daily Summary & Audio for first {links_processed_successfully} Links - {today_str}"
        email_body = f"Processed the first {len(links_to_process)} links found. Successfully summarized {links_processed_successfully}.\n\n"

        if excel_path:
            email_body += f"The summary report is attached as '{excel_filename}'.\n"
        else:
            email_body += "Failed to generate the Excel summary report.\n"

        if summary_mp3_paths:
            email_body += f"\nAttaching {len(summary_mp3_paths)} MP3 audio files generated from the summaries.\n"
        else:
            email_body += "\nNo MP3 audio files were generated.\n"

        email_body += "\n--- Summaries --- \n"
        for i, article_data in enumerate(processed_articles_data):
             email_body += f"\n{i+1}. {article_data['link']}\n   Summary: {article_data['summary'][:250]}...\n" # Show slightly more

        files_for_email = []
        if excel_path:
            files_for_email.append(excel_path)
        files_for_email.extend(summary_mp3_paths)

        output_manager.send_email(email_subject, email_body, files_for_email)


    except Exception as e:
        logging.critical(f"An unexpected error occurred during the daily workflow: {e}", exc_info=True)
        try:
            error_subject = f"ERROR in Daily Workflow - {today_str}"
            error_body = f"The daily email processing workflow encountered an error.\n\nError:\n{e}\n\nPlease check the logs (workflow.log) for details."
            if 'output_manager' in locals():
                 output_manager.send_email(error_subject, error_body, [])
            else:
                 temp_output_manager = OutputManager(config["gmail_email"], config["gmail_password"], config["target_email"])
                 temp_output_manager.send_email(error_subject, error_body, [])
        except Exception as email_err:
            logging.error(f"Failed to send error notification email: {email_err}")

    finally:
        # --- 5. Cleanup ---
        if 'output_manager' in locals() and 'files_to_cleanup' in locals():
            output_manager.cleanup_files(files_to_cleanup)
        if 'email_reader' in locals() and email_reader.connected:
             email_reader.disconnect()

        end_time = time.time()
        logging.info(f"--- Daily Workflow Finished. Total time: {end_time - start_time:.2f} seconds ---")


# --- Main Execution Block ---
if __name__ == "__main__":
    setup_logging()
    logging.info("=============================================")
    logging.info(" Starting Modular Email Processor Script ")
    logging.info("=============================================")

    try:
        config = load_config()

        # --- Run Immediately ---
        logging.info("Running workflow immediately...")
        daily_workflow(config)
        logging.info("Workflow run complete.")
        # --- End Immediate Run ---

    except FileNotFoundError as e:
         logging.critical(f"CRITICAL ERROR: Missing required file: {e}. Ensure .env and potentially model files exist.")
    except ImportError as e:
         logging.critical(f"CRITICAL ERROR: Missing required library: {e}. Please run 'pip install -r requirements.txt'.")
    except KeyboardInterrupt:
        logging.info("Script interrupted by user. Exiting gracefully.")
    except Exception as e:
        logging.critical(f"An unexpected critical error occurred at startup: {e}", exc_info=True)

    logging.info("Script finished.")
