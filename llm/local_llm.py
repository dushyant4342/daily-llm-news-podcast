import logging
import os
import time
from llama_cpp import Llama

class LocalLLM:
    """Handles loading and interacting with a local GGUF language model
       using llama-cpp-python."""

    def __init__(self, model_path):
        self.model_path = model_path
        self.llm = None
        self.device = "cpu" # Keep forced CPU
        logging.warning("Forcing model loading onto CPU...")
        self._load_model()

    def _get_device(self): return "cpu"

    def _load_model(self):
        """Loads the GGUF model using llama-cpp-python, forcing CPU."""
        if not self.model_path or not os.path.exists(self.model_path):
            logging.error(f"GGUF Model file not found at '{self.model_path}'."); return
        if not os.path.isfile(self.model_path):
             logging.error(f"Path '{self.model_path}' is not a GGUF file."); return
        try:
            n_ctx = 2048; n_gpu_layers = 0; verbose = True #2048 is maximum for mistral ai
            logging.info(f"Loading GGUF model from: {self.model_path}")
            logging.warning(f"Forcing CPU execution with n_gpu_layers={n_gpu_layers}.")
            self.llm = Llama(model_path=self.model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=verbose)
            logging.info("GGUF model loaded successfully using llama-cpp-python (Backend: CPU).")
        except Exception as e:
            logging.error(f"Failed to load GGUF model: {e}", exc_info=True); self.llm = None

    def summarize(self, text, max_length=50000): #ValueError: Requested tokens (6772) for 40000 chars exceed context window of 2048
        """# A context window of 2048 means the AI model can process roughly 1500 words or 4000 characters at once.
        Generates a detailed summary for the given email body text.
        """
        if not self.llm: return "Error: GGUF Model not loaded."
        if not text or not text.strip(): return "Error: No text provided."

        # --- Prompt for Email Content ---
        prompt = (
        f"[INST] Summarize the following email content. Only include the main product updates, tutorials, or announcements. Clean the text as the best as you can to avoid *,!@#$%^&*() etc. so it can be readable easily and can be converted into a transcript, make sure to clean the text in a good way before summarizing so the generated speech is more clearer and have all the details. "
        f"Do not include greetings, dates like March 31, 2025, Read Online,  sender details, dates, or links.\n\n{text}\n\n[/INST]"
        )

        print("="*80)
        print(f'prompt: {prompt}')

#         prompt = f"""[INST] Provide a comprehensive and detailed summary of the main content of the following email text. #          Read the content provided and give summary which relevant to read ignore everything which is not important. #          Ignore greetings, sign-offs, unsubscribe links, author promotions, and other boilerplate: # Text: "{text}" [/INST] # Summary:"""
        # --------------------------------

        stop_sequences = ["</s>", "[/INST]"]
        try:
            logging.info(f"Generating detailed summary for email text (length: {len(text)} chars) using llama.cpp (CPU)...")
            start_time = time.time()
            output = self.llm(prompt, max_tokens=max_length, stop=stop_sequences, echo=False, temperature=0.7)
            end_time = time.time()
            inference_time = end_time - start_time

            summary = "Error: Could not parse summary."
            if output and "choices" in output and isinstance(output["choices"], list) and len(output["choices"]) > 0:
                if "text" in output["choices"][0]: summary = output["choices"][0]["text"].strip()

            if isinstance(summary, str) and summary.startswith("Summary:"): summary = summary[len("Summary:"):].strip()

            word_count = len(summary.split()) if isinstance(summary, str) else 0
            logging.info(f"llama.cpp CPU Inference time: {inference_time:.2f} seconds")
            logging.info(f"Summary generated (length: {len(summary)} chars, ~{word_count} words).")
            

            print("=" * 80)
            print(f'Generated summary: ', summary)


            return summary if summary else "Summary generation resulted in empty output."

        except Exception as e:
            logging.error(f"Error during llama.cpp inference: {e}", exc_info=True)
            if "llama_decode returned" in str(e): return f"Error: Summary generation failed (llama_decode error - {e})."
            else: return f"Error: Summary generation failed ({e})."
