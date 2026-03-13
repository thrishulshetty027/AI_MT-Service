from xmlrpc import client

import openai
import os
from vio_config import VIO_API_KEY, VIO_BASE_URL, VIO_MODEL

def call_vio_llm(prompt):
    """
    Uses OpenAI-compatible VIO LLM endpoint
    """
    try:
        client = openai.OpenAI(
            api_key=VIO_API_KEY,
            base_url=VIO_BASE_URL
        )

        response = client.chat.completions.create(
            model=VIO_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ] 
        )
        return response.choices[0].message.content
        
    except Exception as e:
        raise Exception(f"VIO LLM request failed: {str(e)}")
    
