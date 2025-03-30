import logging
import pandas as pd
import os
import tempfile
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

class OutputManager:
    """Handles creating the Excel report and sending the email notification."""

    def __init__(self, gmail_email, gmail_password, target_email):
        self.gmail_email = gmail_email
        self.gmail_password = gmail_password
        self.target_email = target_email
        self.temp_dir = tempfile.gettempdir()

    def create_excel(self, processed_data, filename="daily_summary.xlsx"):
        """
        Creates an Excel (.xlsx) file from the processed data.

        Args:
            processed_data (list): List of dictionaries, each representing a processed article.
                                   Expected keys: 'link', 'summary'.
            filename (str): The desired name for the Excel file.

        Returns:
            str: The full path to the created Excel file, or None on failure.
        """
        if not processed_data:
            logging.info("No processed data to create Excel file.")
            return None

        try:
            df = pd.DataFrame(processed_data)
            # --- Ensure only link and summary columns are expected/used ---
            if not df.empty and 'link' in df.columns and 'summary' in df.columns:
                 report_df = df[['link', 'summary']]
            else:
                 logging.warning("DataFrame is empty or missing 'link'/'summary' columns. Creating empty/partial Excel.")
                 # Create empty df with columns if original was empty
                 report_df = pd.DataFrame(columns=['link', 'summary']) if df.empty else df

            output_path = os.path.join(self.temp_dir, filename)

            logging.info(f"Creating Excel report with summaries at: {output_path}")
            report_df.to_excel(output_path, index=False, engine='openpyxl')
            logging.info("Excel report created successfully.")
            return output_path

        except Exception as e:
            logging.error(f"Failed to create Excel file: {e}", exc_info=True)
            return None

    # --- send_email and cleanup_files methods remain the same ---
    def send_email(self, subject, body, attachments=None):
        """
        Sends an email using Gmail SMTP with optional attachments.

        Args:
            subject (str): The email subject.
            body (str): The plain text email body.
            attachments (list): A list of file paths to attach.

        Returns:
            bool: True if email sent successfully, False otherwise.
        """
        if not self.target_email:
            logging.error("No target email address configured. Cannot send email.")
            return False
        if not self.gmail_email or not self.gmail_password:
             logging.error("Gmail credentials missing. Cannot send email.")
             return False

        if attachments is None:
            attachments = []

        try:
            logging.info(f"Preparing email for {self.target_email} with subject: {subject}")
            msg = MIMEMultipart()
            msg['From'] = self.gmail_email
            msg['To'] = self.target_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            attached_count = 0
            for file_path in attachments:
                if file_path and os.path.exists(file_path):
                    filename = os.path.basename(file_path)
                    try:
                        with open(file_path, "rb") as attachment_file:
                            part = MIMEApplication(attachment_file.read(), Name=filename)
                        part['Content-Disposition'] = f'attachment; filename="{filename}"'
                        msg.attach(part)
                        logging.info(f"Attaching file to email: {filename}")
                        attached_count += 1
                    except Exception as e:
                        logging.error(f"Error attaching file {filename}: {e}", exc_info=True)
                else:
                    logging.warning(f"Attachment file not found or invalid: {file_path}")

            logging.info(f"Attempting to send email with {attached_count} attachments...")
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.ehlo()
                server.login(self.gmail_email, self.gmail_password)
                server.send_message(msg)
                logging.info("Email sent successfully.")
                return True

        except smtplib.SMTPAuthenticationError:
            logging.error("SMTP Authentication Error: Check Gmail email/app password.")
            return False
        except Exception as e:
            logging.error(f"Error sending email: {e}", exc_info=True)
            return False

    def cleanup_files(self, file_paths):
        """
        Deletes a list of temporary files.

        Args:
            file_paths (list): A list of full file paths to delete.
        """
        logging.info(f"Cleaning up {len(file_paths)} temporary files...")
        cleaned_count = 0
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    cleaned_count += 1
                except OSError as e:
                    logging.error(f"Error removing temporary file {file_path}: {e}", exc_info=True)
        logging.info(f"Cleaned up {cleaned_count} files.")

