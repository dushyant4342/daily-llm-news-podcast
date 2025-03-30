import logging
import os
import time
from llama_cpp import Llama

class LocalLLM:
    """Handles loading and interacting with a local GGUF language model
       using llama-cpp-python."""

    def __init__(self, model_path):
        """
        Initializes the LocalLLM class using llama-cpp-python.
        """
        self.model_path = model_path
        self.llm = None
        # Keep forced CPU based on user's hardware confirmation
        self.device = "cpu"
        logging.warning("Forcing model loading onto CPU. This may require significant RAM and will be slow.")
        self._load_model()

    def _get_device(self):
        # Bypassed
        return "cpu"

    def _load_model(self):
        """Loads the GGUF model using llama-cpp-python, forcing CPU."""
        if not self.model_path or not os.path.exists(self.model_path):
            logging.error(f"GGUF Model file not found at '{self.model_path}'. Cannot load model.")
            return
        if not os.path.isfile(self.model_path):
             logging.error(f"Path '{self.model_path}' is a directory, not a GGUF file.")
             return
        try:
            n_ctx = 2048
            n_gpu_layers = 0 # Keep forced CPU
            verbose = True
            logging.info(f"Loading GGUF model from: {self.model_path}")
            logging.warning(f"Forcing CPU execution with n_gpu_layers={n_gpu_layers}.")

            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                verbose=verbose
            )
            backend_used = "CPU"
            logging.info(f"GGUF model loaded successfully using llama-cpp-python (Backend: {backend_used}).")

        except Exception as e:
            logging.error(f"Failed to load GGUF model using llama-cpp-python: {e}", exc_info=True)
            self.llm = None

    def summarize(self, text, max_length=512): # Keep max_length generous
        """
        Generates a summary for the given text using the loaded GGUF model.
        Logs the raw output dictionary.
        """
        if not self.llm:
            return "Error: GGUF Model not loaded. Cannot summarize."
        if not text or not text.strip():
            return "Error: No text provided for summarization."

        # --- Slightly Simplified Prompt ---
        prompt = f"""[INST] Provide a comprehensive summary of the following text:
Text: "{text}" [/INST]
Summary:"""
        # ----------------------------------

        stop_sequences = ["</s>", "[/INST]"]

        try:
            logging.info(f"Generating summary for text (length: {len(text)} chars) using llama.cpp (CPU)...")

            start_time = time.time()
            # --- Call llama-cpp-python ---
            output = self.llm(
                prompt,
                max_tokens=max_length,
                stop=stop_sequences,
                echo=False
            )
            # -----------------------------
            end_time = time.time()
            inference_time = end_time - start_time

            # --- Log the RAW output dictionary ---
            logging.info(f"Raw llama.cpp output dictionary: {output}")
            # -------------------------------------

            # Extract generated text (handle potential missing keys)
            summary = "Error: Could not parse summary from LLM output." # Default error
            if output and "choices" in output and isinstance(output["choices"], list) and len(output["choices"]) > 0:
                if "text" in output["choices"][0]:
                     summary = output["choices"][0]["text"].strip()

            # Basic cleanup
            if isinstance(summary, str) and summary.startswith("Summary:"):
                 summary = summary[len("Summary:"):].strip()

            word_count = len(summary.split()) if isinstance(summary, str) else 0
            logging.info(f"llama.cpp CPU Inference time: {inference_time:.2f} seconds")
            logging.info(f"Summary extracted (length: {len(summary)} chars, ~{word_count} words).")

            if word_count < 10 and not summary.startswith("Error:"): # Check for very short valid output
                 logging.warning(f"Generated summary is very short ({word_count} words).")

            return summary if summary else "Summary generation resulted in empty output."

        except Exception as e:
            logging.error(f"Error during llama.cpp inference: {e}", exc_info=True)
            if "llama_decode returned" in str(e):
                 return f"Error: Summary generation failed (llama_decode error - {e})."
            else:
                 return f"Error: Summary generation failed ({e})."
