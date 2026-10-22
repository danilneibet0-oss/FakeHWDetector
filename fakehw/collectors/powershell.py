"""Run a PowerShell snippet and parse its JSON output (no extra Python dependencies, no admin rights)."""

import base64
import json
import shutil
import subprocess
import sys


class PsQueryError(RuntimeError):
    pass


def run_json(script: str, timeout: float = 90.0):
    if sys.platform != "win32":
        raise PsQueryError("PowerShell collectors are only available on Windows")
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        raise PsQueryError("PowerShell not found")
    prelude = "$ErrorActionPreference = 'Stop'\n[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
    encoded = base64.b64encode((prelude + script).encode("utf-16-le")).decode("ascii")
    try:
        proc = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, timeout=timeout, creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PsQueryError(f"PowerShell failed: {e}") from e
    if proc.returncode != 0:
        raise PsQueryError(f"PowerShell exited with {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[:300]}")
    text = proc.stdout.decode("utf-8-sig", "replace").strip()
    try:
        return json.loads(text) if text else []
    except ValueError as e:
        raise PsQueryError(f"unexpected PowerShell output: {e}") from e


def as_list(data) -> list:
    return [data] if isinstance(data, dict) else list(data or [])
