import logging
import pandas as pd
import os
import tempfile
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
# Removed date import, timestamp comes from main

class OutputManager:
    """Handles creating Excel report, saving transcripts, and sending email."""

    def __init__(self, gmail_email, gmail_password, target_email, transcript_dir):
        self.gmail_email = gmail_email
        self.gmail_password = gmail_password
        self.target_email = target_email
        self.temp_dir = tempfile.gettempdir()
        self.transcript_dir = transcript_dir
        os.makedirs(self.transcript_dir, exist_ok=True)

    # --- Modified to accept timestamp_str ---
    def create_excel(self, processed_data, report_date_str, timestamp_str, filename_base="Email_Summary_Report"):
        """
        Creates an Excel (.xlsx) file from the processed data using timestamp.

        Args:
            processed_data (list): List of dicts {'sender', 'summary', 'cleaned_content'}.
            report_date_str (str): Date string for the report (YYYY-MM-DD).
            timestamp_str (str): IST timestamp string for filename uniqueness.
            filename_base (str): Base name for the Excel file.

        Returns:
            str: Full path to the created Excel file, or None on failure.
        """
        if not processed_data: logging.info("No data for Excel."); return None
        try:
            df = pd.DataFrame(processed_data)
            columns_order = ['sender', 'summary', 'cleaned_content']
            for col in columns_order:
                 if col not in df.columns: df[col] = None
            report_df = df[columns_order]

            # --- Use report_date_str and timestamp_str in filename ---
            filename = f"{filename_base}_{report_date_str}_{timestamp_str}.xlsx"
            # -------------------------------------------------------
            output_path = os.path.join(self.temp_dir, filename)

            logging.info(f"Creating Excel report with summaries at: {output_path}")
            report_df.to_excel(output_path, index=False, engine='openpyxl')
            logging.info("Excel report created successfully.")
            return output_path

        except Exception as e:
            logging.error(f"Failed to create Excel file: {e}", exc_info=True)
            return None

    # --- Modified to accept timestamp_str ---
    def save_transcript(self, sender, subject, cleaned_body, report_date_str, timestamp_str):
        """Saves the cleaned email body to a text file using timestamp."""
        if not cleaned_body: logging.warning(f"No cleaned body for {sender} '{subject}'."); return None
        try:
            safe_subject = re.sub(r'[\\/*?:"<>|]', "", subject)[:50]
            safe_sender = re.sub(r'[\\/*?:"<>|@.]', "", sender)
            # --- Use report_date_str and timestamp_str in filename ---
            filename = f"Transcript_{safe_sender}_{timestamp_str}.txt"
            # -------------------------------------------------------
            filepath = os.path.join(self.transcript_dir, filename)

            logging.info(f"Saving transcript to: {filepath}")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Subject: {subject}\n")
                f.write(f"From: {sender}\n")
                f.write("="*20 + " CLEANED CONTENT " + "="*20 + "\n\n")
                f.write(cleaned_body)
            return filepath
        except Exception as e:
            logging.error(f"Failed to save transcript for {sender}: {e}", exc_info=True)
            return None

    # --- send_email method remains the same ---
    def send_email(self, subject, body, attachments=None):
        if not self.target_email: logging.error("No target email..."); return False
        if not self.gmail_email or not self.gmail_password: logging.error("Gmail creds missing..."); return False
        if attachments is None: attachments = []
        try:
            msg = MIMEMultipart(); msg['From'] = self.gmail_email; msg['To'] = self.target_email; msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            attached_count = 0
            for file_path in attachments:
                if file_path and os.path.exists(file_path):
                    filename = os.path.basename(file_path)
                    try:
                        with open(file_path, "rb") as attachment_file: part = MIMEApplication(attachment_file.read(), Name=filename)
                        part['Content-Disposition'] = f'attachment; filename="{filename}"'
                        msg.attach(part); logging.info(f"Attaching file: {filename}"); attached_count += 1
                    except Exception as e: logging.error(f"Error attaching {filename}: {e}", exc_info=True)
                else: logging.warning(f"Attachment not found: {file_path}")
            logging.info(f"Attempting email with {attached_count} attachments...")
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.ehlo(); server.login(self.gmail_email, self.gmail_password); server.send_message(msg)
            logging.info("Email sent successfully.")
            return True
        except smtplib.SMTPAuthenticationError: logging.error("SMTP Auth Error."); return False
        except Exception as e: logging.error(f"Error sending email: {e}", exc_info=True); return False
    # -------------------------------------------

    def cleanup_files(self, file_paths):
        """Deletes a list of temporary files (Excel, MP3s)."""
        logging.info(f"Cleaning up {len(file_paths)} temporary files (Excel, MP3s)...")
        cleaned_count = 0
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try: os.remove(file_path); cleaned_count += 1
                except OSError as e: logging.error(f"Error removing temp file {file_path}: {e}", exc_info=True)
        logging.info(f"Cleaned up {cleaned_count} files.")

