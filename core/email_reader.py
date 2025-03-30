import imaplib
import email
from email.header import decode_header
import logging
import re
from datetime import date
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

class EmailReader:
    """Handles connection to IMAP server and fetching/parsing emails.
    Extracts links from HTML content and filters structurally."""

    # --- Define patterns/domains to ignore (Reinstated) ---
    IGNORED_DOMAINS = {
        "help.medium.com",
        "policy.medium.com",
        "play.google.com", # Ignore Google Play Store
        "itunes.apple.com", # Ignore Apple App Store (older domain)
        "apps.apple.com", # Ignore Apple App Store (newer domain)
    }
    IGNORED_PATH_PREFIXES = {
        "/unsubscribe",
        "/privacy",
        "/terms",
        "/legal",
        "/careers",
        "/jobs",
        "/support",
        "/settings",
        "/me/", # Ignore user-specific pages like settings
        "/m/", # Often mobile links or redirects
        "/plans", # Medium subscription plans page
        "/search", # Search results pages
        "/recommendations", # Often internal
        "/notifications",
        "/following",
        "/followers",
        "/topics", # Usually tag pages, handled below too
    }
    # IGNORE_PROFILE_PATHS = True # We handle this more precisely now


    # --- No keywords needed in init for this version ---
    def __init__(self, email_address, password, server="imap.gmail.com"):
        self.email_address = email_address
        self.password = password
        self.server = server
        self.mail = None
        self.connected = False
        logging.info("EmailReader initialized with structural link filtering.")

    def connect(self):
        """Connects to the IMAP server and logs in."""
        if self.connected:
            logging.info("Already connected to IMAP server.")
            return True
        try:
            logging.info(f"Connecting to IMAP server: {self.server}")
            self.mail = imaplib.IMAP4_SSL(self.server)
            logging.info(f"Logging in as {self.email_address}")
            status, _ = self.mail.login(self.email_address, self.password)
            if status == 'OK':
                logging.info("IMAP login successful.")
                self.connected = True
                return True
            else:
                logging.error(f"IMAP login failed with status: {status}")
                self.connected = False
                return False
        except imaplib.IMAP4.error as e:
            logging.error(f"IMAP connection/login error: {e}", exc_info=True)
            self.connected = False
            return False
        except Exception as e:
            logging.error(f"Unexpected error during IMAP connection: {e}", exc_info=True)
            self.connected = False
            return False

    def disconnect(self):
        """Logs out and closes the IMAP connection."""
        if self.connected and self.mail:
            try:
                self.mail.logout()
                logging.info("IMAP logout successful.")
            except imaplib.IMAP4.error as e:
                logging.warning(f"Error during IMAP logout: {e}")
            finally:
                 self.mail = None
                 self.connected = False
        else:
            logging.info("Not connected to IMAP server, no need to disconnect.")


    def fetch_today_emails(self, allowed_senders):
        """
        Fetches emails received today from the specified list of senders.

        Args:
            allowed_senders (list): A list of sender email addresses to filter by.

        Returns:
            list: A list of dictionaries, each containing 'subject', 'from', 'body' (HTML preferred).
        """
        if not self.connected:
            logging.error("Not connected to IMAP server. Cannot fetch emails.")
            return []
        if not allowed_senders:
            logging.warning("No allowed senders provided. Cannot fetch emails.")
            return []

        emails_data = []
        try:
            status, _ = self.mail.select("inbox")
            if status != 'OK':
                 logging.error("Failed to select INBOX.")
                 return []

            today = date.today()
            date_str = today.strftime("%d-%b-%Y")
            search_criteria = f'(SINCE "{date_str}")'
            logging.info(f"Searching INBOX for emails SINCE {date_str}...")

            status, messages = self.mail.search(None, search_criteria)

            if status != "OK":
                logging.error(f"Error searching emails: {status}")
                return []

            email_ids = messages[0].split()
            logging.info(f"Found {len(email_ids)} emails received today. Filtering by allowed senders...")

            allowed_senders_lower = [s.lower() for s in allowed_senders]
            fetched_count = 0

            for email_id in reversed(email_ids):
                status, msg_data = self.mail.fetch(email_id, "(RFC822)")
                if status != "OK":
                    logging.warning(f"Failed to fetch email ID {email_id.decode()}")
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        from_header = msg.get("From", "")
                        sender_email = email.utils.parseaddr(from_header)[1].lower()

                        if sender_email not in allowed_senders_lower:
                            continue

                        subject_header = msg.get("Subject", "No Subject")
                        subject, encoding = decode_header(subject_header)[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8", errors='replace')

                        logging.info(f"Processing email from '{sender_email}' with subject '{subject}'")
                        fetched_count += 1
                        body = self._get_email_body(msg, prefer_html=True)

                        if body:
                            emails_data.append({"subject": subject, "from": sender_email, "body": body})
                        else:
                            logging.warning(f"Could not extract HTML or text body for email '{subject}' from {sender_email}")

            logging.info(f"Finished fetching. Found {fetched_count} relevant emails from allowed senders.")
            return emails_data

        except imaplib.IMAP4.error as e:
            logging.error(f"IMAP error during fetch: {e}", exc_info=True)
            self.disconnect()
            return []
        except Exception as e:
            logging.error(f"Unexpected error fetching emails: {e}", exc_info=True)
            self.disconnect()
            return []

    def _get_email_body(self, msg, prefer_html=False):
        """Extracts the text or HTML body from an email message object."""
        body = ""
        plain_text_body = ""
        html_body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if "attachment" not in content_disposition:
                    charset = part.get_content_charset() or 'utf-8'
                    if content_type == "text/plain" and not plain_text_body:
                        try:
                            payload = part.get_payload(decode=True)
                            if payload: plain_text_body = payload.decode(charset, errors='replace')
                        except Exception as e: logging.warning(f"Could not decode text/plain part: {e}")
                    elif content_type == "text/html" and not html_body:
                         try:
                            payload = part.get_payload(decode=True)
                            if payload: html_body = payload.decode(charset, errors='replace')
                         except Exception as e: logging.warning(f"Could not decode text/html part: {e}")
        else:
             content_type = msg.get_content_type()
             charset = msg.get_content_charset() or 'utf-8'
             if content_type == "text/plain":
                 try:
                    payload = msg.get_payload(decode=True)
                    if payload: plain_text_body = payload.decode(charset, errors='replace')
                 except Exception as e: logging.warning(f"Could not decode non-multipart text/plain body: {e}")
             elif content_type == "text/html":
                  try:
                    payload = msg.get_payload(decode=True)
                    if payload: html_body = payload.decode(charset, errors='replace')
                  except Exception as e: logging.warning(f"Could not decode non-multipart text/html body: {e}")
        if prefer_html and html_body: return html_body.strip()
        elif plain_text_body: return plain_text_body.strip()
        elif html_body: return html_body.strip()
        else: return ""
    # --------------------------------------------------------------------------

    # --- Reinstated AND Corrected structural filter ---
    def _is_valid_article_link(self, url):
        """
        Checks if a URL is likely an article link and not a footer/action/profile/publication link.
        """
        try:
            if not url or not url.startswith(('http://', 'https://')):
                return False

            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            path = parsed.path.lower().strip('/')
            original_path_lower = parsed.path.lower()

            # 1. Ignore specific non-article domains
            if domain in self.IGNORED_DOMAINS:
                logging.info(f"FILTERED (Ignored Domain '{domain}'): {url}")
                return False

            # 2. Ignore specific path prefixes
            for prefix in self.IGNORED_PATH_PREFIXES:
                if original_path_lower.startswith(prefix):
                    logging.info(f"FILTERED (Ignored Path Prefix '{prefix}'): {url}")
                    return False

            # 3. *** CORRECTED Profile Path Check ***
            if original_path_lower.startswith('/@'):
                 path_segments_profile = [seg for seg in path.split('/') if seg]
                 # If it starts with @ and has only 1 segment (the username), it's a profile page.
                 if len(path_segments_profile) == 1:
                      logging.info(f"FILTERED (Profile Homepage Path): {url}")
                      return False
                 # Otherwise (e.g., /@username/article-slug), it might be an article - allow for now.

            # 4. Ignore common image file extensions
            if any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp']):
                 logging.info(f"FILTERED (Image File): {url}")
                 return False

            # 5. Ignore root domain paths (like medium.com/)
            if domain == "medium.com" and not path:
                 logging.info(f"FILTERED (Root Medium Domain): {url}")
                 return False

            # 6. Ignore likely publication/tag homepages
            path_segments = [seg for seg in path.split('/') if seg]
            is_likely_pub_or_tag = False
            # Check for /tag/name or single segment path (unless it looks like an ID)
            if len(path_segments) == 1 and not re.search(r'[a-f0-9]{6,}', path_segments[0]): # Allow single segments if they look like IDs
                 is_likely_pub_or_tag = True
            elif len(path_segments) == 2 and path_segments[0] == 'tag':
                 is_likely_pub_or_tag = True

            if is_likely_pub_or_tag:
                 logging.info(f"FILTERED (Likely Publication/Tag Homepage): {url}")
                 return False

            # If it passes all checks, assume it's a valid article link
            # logging.debug(f"Filter Passed: {url}")
            return True

        except Exception as e:
            logging.warning(f"Error parsing URL '{url}' for validation: {e}. Assuming invalid.")
            return False


    def extract_links_from_text(self, html_content):
        """
        Extracts valid article links from HTML email content using BeautifulSoup
        and applies structural filtering.
        """
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, 'html.parser')
        potential_links = set()

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            href = href.strip()
            if href and href.startswith(('http://', 'https://')):
                potential_links.add(href)

        logging.info(f"Found {len(potential_links)} unique absolute potential links in HTML.")

        valid_article_links = []
        for url in potential_links:
            norm_url = url.rstrip('/')
            # Apply the corrected structural filter
            if self._is_valid_article_link(norm_url):
                valid_article_links.append(norm_url)
            # else: Filter messages now logged inside _is_valid_article_link

        logging.info(f"Extracted {len(valid_article_links)} valid article links after structural filtering.")
        # Return as list, maybe sort for consistency? Optional.
        return sorted(list(valid_article_links))

