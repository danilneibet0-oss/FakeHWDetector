"""Portable mode: where a frozen build keeps its settings and knowledge-base cache.

A `portable.txt` file next to the executables (shipped in the portable zip, not in the installer) moves
both into a `data` folder beside them, so the program leaves nothing in the user profile. Running from
source and installed builds keep using %APPDATA% / %LOCALAPPDATA%.
"""

import sys
from pathlib import Path

PORTABLE_MARKER = "portable.txt"


def portable_data_dir() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    base = Path(sys.executable).resolve().parent
    return base / "data" if (base / PORTABLE_MARKER).is_file() else None
