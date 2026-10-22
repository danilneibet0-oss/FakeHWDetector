"""Render README.md and README.ru.md from docs/readme/*.tmpl using fakehw/branding.py.

Usage: python tools/render_readme.py
"""

import sys
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fakehw import branding  # noqa: E402
from fakehw.rules.engine import load_rules  # noqa: E402

NAMES = ("README.md", "README.ru.md")


def render(name: str) -> str:
    template = (ROOT / "docs" / "readme" / f"{name}.tmpl").read_text(encoding="utf-8")
    return Template(template).substitute(
        APP_NAME=branding.APP_NAME, PACKAGE_NAME=branding.PACKAGE_NAME, CLI_NAME=branding.CLI_NAME,
        TAGLINE=branding.TAGLINE, RULE_COUNT=len(load_rules()),
    )


def main() -> None:
    for name in NAMES:
        (ROOT / name).write_text(render(name), encoding="utf-8")
        print("wrote", name)


if __name__ == "__main__":
    main()
