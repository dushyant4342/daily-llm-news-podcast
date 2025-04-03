import imaplib
import email
from email.header import decode_header
import logging
import re
# --- Keep date, timedelta ---
from datetime import date, timedelta
# ---------------------------
from bs4 import BeautifulSoup # Keep for HTML parsing

class EmailReader:
    """Handles connection to IMAP server and fetching email bodies."""

    def __init__(self, email_address, password, server="imap.gmail.com"):
        self.email_address = email_address
        self.password = password
        self.server = server
        self.mail = None
        self.connected = False
        logging.info("EmailReader initialized to fetch email bodies.")

    # --- connect, disconnect methods remain the same ---
    def connect(self):
        if self.connected: return True
        try:
            logging.info(f"Connecting to IMAP server: {self.server}")
            self.mail = imaplib.IMAP4_SSL(self.server)
            logging.info(f"Logging in as {self.email_address}")
            status, _ = self.mail.login(self.email_address, self.password)
            if status == 'OK': self.connected = True; return True
            else: logging.error(f"IMAP login failed: {status}"); self.connected = False; return False
        except Exception as e: logging.error(f"IMAP connection error: {e}", exc_info=True); self.connected = False; return False

    def disconnect(self):
        if self.connected and self.mail:
            try: self.mail.logout(); logging.info("IMAP logout successful.")
            except Exception as e: logging.warning(f"Error during IMAP logout: {e}")
            finally: self.mail = None; self.connected = False
        else: logging.info("Not connected.")
    # ----------------------------------------------------

    # --- Modified method to accept target_date ---
    def fetch_emails_since(self, allowed_senders, target_date):
        """
        Fetches emails received SINCE the specified target_date from allowed senders.

        Args:
            allowed_senders (list): List of sender emails.
            target_date (date): The date object representing the start date (exclusive).

        Returns:
            list: List of dicts: {'subject': str, 'from': str, 'body': str (HTML preferred)}
        """
        if not self.connected: logging.error("Not connected..."); return []
        if not allowed_senders: logging.warning("No allowed senders..."); return []
        if not target_date: logging.error("No target_date provided."); return[]

        emails_data = []
        try:
            status, _ = self.mail.select("inbox")
            if status != 'OK': logging.error("Failed to select INBOX."); return []

            # --- Use target_date for search ---
            # Format for IMAP SINCE command (e.g., 29-Mar-2025)
            date_str = target_date.strftime("%d-%b-%Y")
            logging.info(f"Searching INBOX for emails SINCE {date_str}...")
            search_criteria = f'SINCE "{date_str}"'
            # ----------------------------------

            status, messages = self.mail.search(None, search_criteria)

            if status != "OK": logging.error(f"Error searching: {status}, {messages}"); return []
            if not messages or not messages[0]: logging.info("No email IDs found."); return []

            email_ids = messages[0].split()
            logging.info(f"Found {len(email_ids)} emails potentially received since {date_str}. Filtering...")

            allowed_senders_lower = [s.lower() for s in allowed_senders]
            fetched_count = 0

            for email_id in reversed(email_ids):
                try: # Add inner try block for fetch/parse resilience
                    email_id_bytes = email_id if isinstance(email_id, bytes) else email_id.encode('ascii')
                    status, msg_data = self.mail.fetch(email_id_bytes, "(RFC822)")
                    if status != "OK":
                        logging.warning(f"Failed to fetch email ID {email_id_bytes.decode()}")
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            from_header = msg.get("From", "")
                            sender_email = email.utils.parseaddr(from_header)[1].lower()
                            if sender_email not in allowed_senders_lower: continue

                            subject_header = msg.get("Subject", "No Subject")
                            subject, encoding = decode_header(subject_header)[0]
                            if isinstance(subject, bytes): subject = subject.decode(encoding if encoding else "utf-8", errors='replace')

                            logging.info(f"Processing email from '{sender_email}' with subject '{subject}'")
                            fetched_count += 1
                            body = self._get_email_body(msg, prefer_html=True)
                            if body: emails_data.append({"subject": subject, "from": sender_email, "body": body})
                            else: logging.warning(f"Could not extract body for email '{subject}' from {sender_email}")
                except Exception as e_inner:
                     logging.error(f"Error processing individual email ID {email_id}: {e_inner}", exc_info=False) # Log error but continue loop


            logging.info(f"Finished fetching. Found {fetched_count} relevant emails received since {date_str}.")
            return emails_data

        except imaplib.IMAP4.error as e: logging.error(f"IMAP error: {e}", exc_info=True); self.disconnect(); return []
        except Exception as e: logging.error(f"Unexpected error fetching: {e}", exc_info=True); self.disconnect(); return []

    def _get_email_body(self, msg, prefer_html=False):
        """Extracts the text or HTML body from an email message object."""
        # (Keep the improved _get_email_body from previous version)
        body = ""; plain_text_body = ""; html_body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type(); content_disposition = str(part.get("Content-Disposition"))
                if "attachment" not in content_disposition:
                    charset = part.get_content_charset() or 'utf-8'
                    if content_type == "text/plain" and not plain_text_body:
                        try: payload = part.get_payload(decode=True); plain_text_body = payload.decode(charset, errors='replace') if payload else ""
                        except Exception as e: logging.warning(f"Could not decode text/plain part: {e}")
                    elif content_type == "text/html" and not html_body:
                         try: payload = part.get_payload(decode=True); html_body = payload.decode(charset, errors='replace') if payload else ""
                         except Exception as e: logging.warning(f"Could not decode text/html part: {e}")
        else:
             content_type = msg.get_content_type(); charset = msg.get_content_charset() or 'utf-8'
             if content_type == "text/plain":
                 try: payload = msg.get_payload(decode=True); plain_text_body = payload.decode(charset, errors='replace') if payload else ""
                 except Exception as e: logging.warning(f"Could not decode non-multipart text/plain body: {e}")
             elif content_type == "text/html":
                  try: payload = msg.get_payload(decode=True); html_body = payload.decode(charset, errors='replace') if payload else ""
                  except Exception as e: logging.warning(f"Could not decode non-multipart text/html body: {e}")
        if prefer_html and html_body: return html_body.strip()
        elif plain_text_body: return plain_text_body.strip()
        elif html_body: return html_body.strip()
        else: return ""


