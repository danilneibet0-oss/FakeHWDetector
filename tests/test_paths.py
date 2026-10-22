import sys

from fakehw import paths, settings
from fakehw.kb import updater


def frozen_at(monkeypatch, folder, portable: bool):
    folder.mkdir(parents=True, exist_ok=True)
    if portable:
        (folder / paths.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(folder / "app.exe"))


def test_source_checkout_is_never_portable():
    assert getattr(sys, "frozen", False) is False
    assert paths.portable_data_dir() is None


def test_marker_next_to_exe_switches_to_portable_data(monkeypatch, tmp_path):
    frozen_at(monkeypatch, tmp_path / "app", portable=True)
    monkeypatch.delenv("FAKEHW_CONFIG", raising=False)
    monkeypatch.delenv("FAKEHW_CACHE", raising=False)
    data = tmp_path / "app" / "data"
    assert paths.portable_data_dir() == data
    assert settings.default_path() == data / "settings.json"
    assert updater.default_cache_dir() == data / "kb"


def test_installed_build_uses_profile_folders(monkeypatch, tmp_path):
    frozen_at(monkeypatch, tmp_path / "app", portable=False)
    monkeypatch.delenv("FAKEHW_CONFIG", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert paths.portable_data_dir() is None
    assert settings.default_path() == tmp_path / "roaming" / "FakeHWDetector" / "settings.json"


def test_environment_override_wins_over_portable(monkeypatch, tmp_path):
    frozen_at(monkeypatch, tmp_path / "app", portable=True)
    monkeypatch.setenv("FAKEHW_CONFIG", str(tmp_path / "x.json"))
    assert settings.default_path() == tmp_path / "x.json"
