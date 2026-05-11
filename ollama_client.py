"""
Ollama client for local LLM inference.
Replaces opencode/GLM client with direct Ollama HTTP API calls.
"""

import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from typing import Optional


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?(?:\x07|\x1b\\)|\r')
    return ansi_re.sub('', text)


def call_ollama(prompt: str, model_name: Optional[str] = None, timeout: Optional[int] = None) -> str:
    """
    Call Ollama API to generate text completion.
    
    Args:
        prompt: The prompt text to send to Ollama
        model_name: Model name to use (defaults to MODEL_NAME env var)
        timeout: Request timeout in seconds (defaults to OLLAMA_TIMEOUT env var)
    
    Returns:
        Generated text response from Ollama
    
    Raises:
        Exception: If Ollama request fails
    """
    model_name = model_name or os.getenv("MODEL_NAME", "qwen2.5:7b")
    timeout = timeout or int(os.getenv("OLLAMA_TIMEOUT", "600"))
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    temp_path = None
    try:
        # Prepare the request payload
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
            }
        }
        
        # Convert to JSON
        json_data = json.dumps(payload).encode('utf-8')
        
        # Create request
        req = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        # Make request with timeout
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        # Extract generated text
        generated_text = result.get('response', '')
        
        if not generated_text:
            raise Exception(f"Ollama returned empty response for model: {model_name}")
        
        # Debug output
        print(f"[DEBUG] Ollama model: {model_name}")
        print(f"[DEBUG] Response length: {len(generated_text)}")
        
        return generated_text
        
    except urllib.error.URLError as e:
        raise Exception(f"Ollama connection failed ({base_url}): {str(e)}")
    except json.JSONDecodeError as e:
        raise Exception(f"Ollama response parsing failed: {str(e)}")
    except subprocess.TimeoutExpired:
        raise Exception(f"Ollama request timed out after {timeout} seconds")
    except Exception as e:
        if "Ollama" in str(e) or "connection" in str(e).lower():
            raise
        raise Exception(f"Ollama request failed: {str(e)}")


def call_ollama_with_retry(
    prompt: str,
    max_retries: Optional[int] = None,
    model_name: Optional[str] = None,
    timeout: Optional[int] = None
) -> str:
    """
    Call Ollama with retry logic for failed requests.
    
    Args:
        prompt: The prompt text
        max_retries: Maximum number of retry attempts (default: OLLAMA_RETRIES env var)
        model_name: Model name to use
        timeout: Request timeout in seconds
    
    Returns:
        Generated text response
    
    Raises:
        Exception: After all retries exhausted
    """
    max_retries = max_retries or int(os.getenv("OLLAMA_RETRIES", "3"))
    
    for attempt in range(1, max_retries + 1):
        try:
            return call_ollama(prompt, model_name, timeout)
        except Exception as e:
            if attempt == max_retries:
                raise
            print(f"[WARNING] [Ollama Retry] Attempt {attempt}/{max_retries} failed: {str(e)}")
            time.sleep(2 ** attempt)  # Exponential backoff
    
    # Should not reach here, but just in case
    raise Exception("Ollama request failed after all retries")


def call_ollama_file(prompt_file_path: str, model_name: Optional[str] = None) -> str:
    """
    Call Ollama with prompt from a file (similar to original opencode behavior).
    
    Args:
        prompt_file_path: Path to file containing prompt
        model_name: Model name to use
    
    Returns:
        Generated text response
    """
    with open(prompt_file_path, 'r', encoding='utf-8') as f:
        prompt = f.read()
    
    return call_ollama(prompt, model_name)
