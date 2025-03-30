import logging
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
import re
import os # Import os for path manipulation
import tempfile # Import tempfile for saving html

class ContentProcessor:
    """Fetches web content, cleans it, extracts text more broadly,
       saves raw HTML for debugging, and generates summaries using an LLM."""

    def __init__(self, llm_instance):
        self.llm = llm_instance
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        # Create a directory for saving HTML if it doesn't exist
        self.debug_html_dir = os.path.join(tempfile.gettempdir(), "debug_html")
        os.makedirs(self.debug_html_dir, exist_ok=True)


    def _clean_fetched_text(self, text):
        # (Keep the _clean_fetched_text method from the previous version)
        if not text: return text
        logging.debug("Attempting to clean fetched text...")
        cleaned = text
        patterns_to_remove = [
            r"Member-only story", r"From .*? in .*?(?:Follow)?", r"Follow\s*$",
            r"Share\s*$", r"\d+ min read", r"Listen\s*$", r"--\s*\d+\s*$", r"^\s*\d+\s*$",
        ]
        lines = cleaned.splitlines()
        cleaned_lines = []
        for line in lines:
            original_line = line
            line_lower = line.lower().strip()
            should_remove = False
            if len(line_lower) < 15 and not line_lower.endswith(('.', '?', '!')):
                 if any(kw in line_lower for kw in ['follow', 'share', 'listen', 'clap', 'min read', 'member only']):
                      should_remove = True
            if not should_remove:
                for pattern in patterns_to_remove:
                    if re.search(pattern, line, re.IGNORECASE):
                        logging.debug(f"Removing line matching pattern '{pattern}': {original_line}")
                        should_remove = True
                        break
            if not should_remove:
                cleaned_lines.append(original_line)
        cleaned = "\n".join(cleaned_lines)
        return cleaned.strip()


    def fetch_article_text(self, url):
        """
        Fetches HTML, saves it for debugging, extracts text from relevant tags,
        cleans it, and logs a snippet.
        """
        html_content = None # Initialize variable
        try:
            logging.info(f"Fetching content from URL: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            html_content = response.text # Get the raw HTML text

            # --- Save Raw HTML for Debugging ---
            try:
                # Create a filename based on the URL
                safe_filename = "debug_" + re.sub(r'[^a-zA-Z0-9_-]', '_', url.split("//")[-1])[:100] + ".html"
                save_path = os.path.join(self.debug_html_dir, safe_filename)
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logging.info(f"Saved raw HTML for debugging to: {save_path}")
            except Exception as save_err:
                logging.warning(f"Could not save debug HTML for {url}: {save_err}")
            # ------------------------------------

            # Proceed with parsing the fetched HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            article_body = soup.find('article')
            if not article_body: article_body = soup.find('main')
            target_element = article_body if article_body else soup.body
            if not target_element:
                 logging.warning(f"Could not find <article>, <main>, or <body> tag in {url}.")
                 return None

            content_tags = target_element.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'pre', 'blockquote', 'td', 'th'])
            extracted_text = []
            for tag in content_tags:
                 tag_text = tag.get_text(separator='\n', strip=True)
                 if tag_text: extracted_text.append(tag_text)

            full_text = "\n\n".join(extracted_text)
            cleaned_text = '\n'.join([line.strip() for line in full_text.splitlines() if line.strip()])

            if not cleaned_text:
                 logging.warning(f"Could not extract meaningful text from relevant tags in {url}.")
                 return None

            final_cleaned_text = self._clean_fetched_text(cleaned_text)

            if not final_cleaned_text:
                 logging.warning(f"Text became empty after cleaning boilerplate for {url}")
                 return None

            snippet_length = 500
            text_snippet = final_cleaned_text[:snippet_length]
            if len(final_cleaned_text) > snippet_length: text_snippet += "..."
            logging.info(f"Fetched and cleaned text snippet (Length: {len(final_cleaned_text)} chars): {text_snippet}")

            return final_cleaned_text

        # Handle exceptions after trying to get html_content
        except requests.exceptions.Timeout: logging.error(f"Timeout error fetching URL {url}"); return None
        except requests.exceptions.RequestException as e: logging.error(f"HTTP error fetching URL {url}: {e}"); return None
        except Exception as e: logging.error(f"Error parsing/cleaning content from {url}: {e}", exc_info=True); return None

    # --- process_link method remains the same ---
    def process_link(self, url):
        """
        Fetches cleaned content and generates a summary for a single link.
        """
        content = self.fetch_article_text(url) # Gets cleaned text now
        if not content:
            return None
        summary = "Error: Summarization Failed"
        if self.llm and self.llm.llm:
            summary = self.llm.summarize(content)
        else:
            summary = "Error: LLM not available for summarization."
            logging.warning("LLM not available (check loading logs), cannot generate summary.")
        return {"link": url, "summary": summary}
