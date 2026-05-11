import subprocess
import os
import re
import sys
import tempfile


def _resolve_opencode_bin():
    npm_base = os.path.join(os.environ.get('APPDATA', ''), 'npm')
    opencode_bin = os.path.join(npm_base, 'node_modules', 'opencode-ai', 'bin', 'opencode')
    if os.path.exists(opencode_bin):
        return f'node "{opencode_bin}"'
    return 'opencode'


def _strip_ansi(text):
    ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?(?:\x07|\x1b\\)|\r')
    return ansi_re.sub('', text)


def call_glm_4_7_flash(prompt):
    """
    Uses opencode CLI to call configured model
    """
    temp_path = None
    try:
        model_name = os.getenv("MODEL_NAME", "zai-coding-plan/glm-5.1")

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', delete=False, encoding='utf-8'
        ) as f:
            f.write(prompt)
            temp_path = f.name

        opencode_cmd = _resolve_opencode_bin()
        cmd_str = (
            f'{opencode_cmd} run -m {model_name} '
            f'--file "{temp_path}" '
            f'--format default '
            f'"Follow the instructions in the attached file and produce the requested output."'
        )

        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            timeout=600,
            encoding='utf-8'
        )

        stdout = _strip_ansi(result.stdout).strip()
        stderr = _strip_ansi(result.stderr).strip()

        print(f"[DEBUG] opencode returncode: {result.returncode}")
        print(f"[DEBUG] opencode stdout length: {len(stdout)}")
        if stderr:
            print(f"[DEBUG] opencode stderr: {stderr[:500]}")

        if result.returncode != 0:
            raise Exception(
                f"opencode failed with code {result.returncode}\nStderr: {stderr}"
            )

        if not stdout:
            raise Exception(f"opencode returned empty output\nStderr: {stderr}")

        return stdout
    except subprocess.TimeoutExpired:
        raise Exception("opencode request timed out")
    except FileNotFoundError:
        raise Exception("opencode not found. Install with: npm install -g opencode-ai")
    except Exception as e:
        if "opencode request failed" in str(e):
            raise
        raise Exception(f"opencode request failed: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


class GLMClient:
    def chat(self, prompt):
        """
        Uses opencode CLI to call configured model
        """
        return call_glm_4_7_flash(prompt)
