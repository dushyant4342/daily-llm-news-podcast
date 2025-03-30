# daily-llm-news-podcast

#CMAKE_ARGS="-DLLAMA_METAL=on" pip install --force-reinstall --no-cache-dir llama-cpp-python -> run in terminal
#(This tells the installer to compile the Metal-specific code).

bitsandbytes #  enable 4-bit quantization for limited memory (loads the model using lower precision (like 4-bit instead of 16-bit or 32-bit), significantly reducing the memory)
