from pathlib import Path

from fakehw import branding


def test_branding_values():
    assert branding.APP_NAME == "FakeHWDetector"
    assert branding.PACKAGE_NAME == "fakehwdetector"
    assert branding.CLI_NAME == "fakehw"
    assert branding.TAGLINE == "Hardware Authenticity Checker"


def test_no_hardcoded_app_name_outside_branding():
    root = Path(branding.__file__).parent
    for py in root.rglob("*.py"):
        if py.name == "branding.py":
            continue
        assert "FakeHWDetector" not in py.read_text(encoding="utf-8"), py
