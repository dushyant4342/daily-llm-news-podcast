import logging
import re
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

class ContentProcessor:
    """Cleans HTML email body content and generates summaries using an LLM."""

    def __init__(self, llm_instance):
        """
        Initializes the ContentProcessor.
        Args:
            llm_instance (LocalLLM): An instance of the LocalLLM class for summarization.
        """
        self.llm = llm_instance
        logging.info("ContentProcessor initialized for cleaning/summarizing email bodies.")

    def _clean_html_body(self, html_content):
        """
        Attempts to clean common boilerplate from HTML email content.
        Returns the extracted and cleaned text content.
        """
        if not html_content:
            return ""

        logging.info("Parsing and cleaning HTML email body...")
        try: # Add try block for BeautifulSoup parsing
            soup = BeautifulSoup(html_content, 'lxml') # Use lxml parser if installed
        except Exception as e:
             logging.warning(f"BeautifulSoup parsing failed (install lxml?): {e}. Trying html.parser.")
             try:
                  soup = BeautifulSoup(html_content, 'html.parser')
             except Exception as e_html:
                  logging.error(f"HTML parsing failed completely: {e_html}")
                  return "" # Cannot proceed if parsing fails


        # --- Remove unwanted elements ---
        # Scripts, styles, comments
        for element in soup(["script", "style", "comment", "head", "meta", "title", "link"]):
            element.decompose()

        # Common footer/header patterns (selectors might need adjustment)
        footer_texts = ["unsubscribe", "manage preferences", "view this email in your browser",
                        "sent by", "mailing address", "terms of service", "privacy policy",
                        "contact us", "help center", "no longer wish to receive", "update your preferences",
                        "all rights reserved"]
        elements_to_remove = []
        # Find elements likely containing footer text (check parents too)
        for text_pattern in footer_texts:
            try:
                found = soup.find_all(string=re.compile(re.escape(text_pattern), re.IGNORECASE))
                for text_node in found:
                    parent = text_node.find_parent(['p', 'td', 'div', 'span', 'font']) # Check common containers
                    if parent and parent not in elements_to_remove:
                         # Heuristic: remove if parent is small or looks like a footer block
                         parent_text_len = len(parent.get_text(strip=True))
                         if parent_text_len < 250 or parent.find_parent('footer'):
                              elements_to_remove.append(parent)
                         else:
                              grandparent = parent.find_parent(['tr', 'table', 'div'])
                              if grandparent and grandparent not in elements_to_remove and grandparent.name != 'body':
                                   if len(grandparent.get_text(strip=True)) < 400:
                                        elements_to_remove.append(grandparent)
            except Exception as e:
                logging.warning(f"Error during footer text search for '{text_pattern}': {e}")

        # Remove common social media link sections
        social_domains = ["facebook.com", "twitter.com", "linkedin.com", "instagram.com", "youtube.com", "pinterest.com"]
        for a_tag in soup.find_all('a', href=True):
             try:
                 href_lower = a_tag['href'].lower()
                 if any(domain in href_lower for domain in social_domains):
                      parent = a_tag.find_parent(['div', 'p', 'td', 'span'])
                      if parent and parent not in elements_to_remove and len(parent.find_all('a')) < 8 and len(parent.get_text(strip=True)) < 100:
                           elements_to_remove.append(parent)
             except Exception as e:
                  logging.warning(f"Error processing social link {a_tag.get('href')}: {e}")

        # Remove the identified elements
        removed_count = 0
        for element in set(elements_to_remove):
             try: element.decompose(); removed_count += 1
             except Exception as e: logging.warning(f"Error decomposing element: {e}")
        if removed_count > 0: logging.info(f"Removed {removed_count} potential boilerplate HTML elements.")

        # --- Extract text from remaining relevant tags ---
        body_element = soup.body if soup.body else soup
        if not body_element: return ""

        # Prioritize finding a main content div if possible (heuristic)
        main_content = body_element.find(['article', 'main'])
        # More heuristics: look for common container IDs/classes (highly variable)
        if not main_content: main_content = body_element.find('div', id=re.compile(r'content|main|body', re.I))
        if not main_content: main_content = body_element.find('table', id=re.compile(r'content|main|body', re.I))

        target_element = main_content if main_content else body_element # Use found container or fallback to body

        content_tags = target_element.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'pre', 'blockquote', 'td', 'th'])

        if len(content_tags) < 3: # If very few specific tags found in target, broaden search
             logging.warning("Few specific content tags found, getting all text from target element.")
             all_text = target_element.get_text(separator='\n', strip=True)
             extracted_text_lines = [line.strip() for line in all_text.splitlines() if line.strip()]
        else:
             extracted_text_lines = []
             for tag in content_tags:
                 tag_text = tag.get_text(separator='\n', strip=True)
                 if tag_text:
                      extracted_text_lines.extend([line.strip() for line in tag_text.splitlines() if line.strip()])

        # --- Final text cleaning ---
        meaningful_lines = []
        for line in extracted_text_lines:
             # Remove very short lines unless they end with punctuation
             if len(line) < 5 and not re.search(r'[.?!]$', line): continue
             # Remove lines that look like typical unsubscribe/boilerplate again
             line_lower = line.lower()
             if any(phrase in line_lower for phrase in footer_texts): continue
             meaningful_lines.append(line)

        cleaned_text = "\n".join(meaningful_lines)

        logging.info(f"Extracted {len(cleaned_text)} chars of cleaned text from email body.")
        return cleaned_text

    def clean_and_summarize_email_body(self, email_body_html):
        """
        Cleans the HTML email body and generates a summary using the LLM.

        Args:
            email_body_html (str): The raw HTML content of the email body.

        Returns:
            tuple: (cleaned_text, summary_text) or (None, None) on failure.
        """
        cleaned_text = self._clean_html_body(email_body_html)

        if not cleaned_text or len(cleaned_text) < 50:
            logging.warning("Cleaned email content is too short to summarize meaningfully.")
            return cleaned_text, "Error: Cleaned content too short for summary."

        summary = "Error: Summarization Failed"
        if self.llm and self.llm.llm:
            summary = self.llm.summarize(cleaned_text)
        else:
            summary = "Error: LLM not available for summarization."
            logging.warning("LLM not available, cannot generate summary.")

        return cleaned_text, summary

