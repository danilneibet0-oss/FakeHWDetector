from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKEHW_CONFIG", str(tmp_path / "settings.json"))


@pytest.fixture
def rules_dir() -> Path:
    return FIXTURES / "rules"
