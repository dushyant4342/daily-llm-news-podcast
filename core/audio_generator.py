import logging
from gtts import gTTS
import os
import tempfile
import re
from datetime import datetime

TTS_CHARACTER_LIMIT = 20000 # Keep limit as safeguard, though summaries should be shorter

class AudioGenerator:
    """Handles Text-to-Speech conversion using gTTS with text length limits."""

    def __init__(self):
        self.temp_dir = os.path.join(tempfile.gettempdir(), "daily_podcasts")
        os.makedirs(self.temp_dir, exist_ok=True)
        logging.info(f"AudioGenerator initialized. Temp directory: {self.temp_dir}")

    def text_to_speech(self, text, filename_base="podcast"):
        """
        Generates an MP3 audio file from text (expected to be a summary),
        truncating if too long.
        """
        if not text or not text.strip():
            logging.warning(f"No text provided for audio generation (base: {filename_base}).")
            return None

        original_length = len(text)
        text_to_process = text

        if original_length > TTS_CHARACTER_LIMIT:
            logging.warning(f"Text (Summary?) length ({original_length} chars) exceeds limit ({TTS_CHARACTER_LIMIT}). Truncating for audio generation.")
            text_to_process = text[:TTS_CHARACTER_LIMIT] + "... (truncated)"

        try:
            safe_filename_base = re.sub(r'[\\/*?:"<>|]', "", filename_base)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            output_filename = f"{safe_filename_base}_{timestamp}.mp3"
            output_path = os.path.join(self.temp_dir, output_filename)

            # --- Add logging for summary ---
            logging.info(f"Generating audio for summary text (processing length: {len(text_to_process)} chars)...")
            # -----------------------------
            tts = gTTS(text=text_to_process, lang='en', slow=False)

            logging.info(f"Attempting to save audio to: {output_path}")
            tts.save(output_path)
            logging.info(f"Audio file saved successfully: {output_path}")

            return output_path

        except Exception as e:
            logging.error(f"Error generating or saving audio using gTTS for '{filename_base}': {e}", exc_info=True)
            return None

    def get_temp_dir(self):
        """Returns the path to the temporary directory used for audio files."""
        return self.temp_dir
