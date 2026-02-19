import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:3b"


def call_ollama(prompt):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,      # lower randomness
            "top_p": 0.9,
            "num_predict": 2048      # prevent runaway output
        }
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=600   # increased timeout (10 mins)
        )

        response.raise_for_status()

        data = response.json()

        if "response" not in data:
            raise Exception("Invalid response from Ollama")

        return data["response"].strip()

    except requests.exceptions.Timeout:
        raise Exception("Ollama request timed out. Reduce diff size.")

    except requests.exceptions.RequestException as e:
        raise Exception(f"Ollama request failed: {str(e)}")
