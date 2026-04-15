import subprocess
import os
import sys
import tempfile


def call_glm_4_7_flash(prompt):
    """
    Uses opencode CLI to call configured model
    """
    try:
        model_name = os.getenv("MODEL_NAME", "zai-coding-plan/glm-4.7-flash")
        cmd = ['opencode', 'run', '-m', model_name]
        result = subprocess.run(
            cmd,
            shell=True,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,
            encoding='utf-8'
        )
        
        if result.returncode != 0:
            raise Exception(f"opencode failed with code {result.returncode}\nStderr: {result.stderr}")
        
        output = result.stdout.strip()
        
        if not output:
            raise Exception("opencode returned empty output")
        
        return output
    except subprocess.TimeoutExpired:
        raise Exception("opencode request timed out")
    except FileNotFoundError:
        raise Exception("opencode not found. Install with: npm install -g opencode-ai")
    except Exception as e:
        raise Exception(f"opencode request failed: {str(e)}")
