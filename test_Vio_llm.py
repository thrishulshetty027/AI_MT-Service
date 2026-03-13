import os
from vio_config import VIO_API_KEY, VIO_BASE_URL, VIO_MODEL

# Set environment variables
os.environ["VIO_API_KEY"] = VIO_API_KEY
os.environ["VIO_BASE_URL"] = VIO_BASE_URL
os.environ["VIO_MODEL"] = VIO_MODEL

from vio_llm_client import call_vio_llm

# Test the VIO LLM
print("Testing VIO LLM...")
try:
    response = call_vio_llm("Explain quantum computing in one sentence")
    print(f"Response: {response}")
except Exception as e:
    print(f"Error: {str(e)}")
