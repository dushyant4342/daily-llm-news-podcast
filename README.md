# daily-llm-news-podcast

#CMAKE_ARGS="-DLLAMA_METAL=on" pip install --force-reinstall --no-cache-dir llama-cpp-python -> run in terminal
#(This tells the installer to compile the Metal-specific code).

bitsandbytes #  enable 4-bit quantization for limited memory (loads the model using lower precision (like 4-bit instead of 16-bit or 32-bit), significantly reducing the memory)


Okay, so there are many limitations to fetch the complete blog from website like Medium, DailyDoseofDS etc using Beautifulsoup or even serpapi. Now, I will try to summarize the emails and then make it into a podcast.

71784 is character count, not token count. Tokens are usually shorter than words (avg: 1 token ≈ 4 characters in English). So 71,784 chars ≈ 17,946 tokens, which is within your n_ctx = 22048 limit.








