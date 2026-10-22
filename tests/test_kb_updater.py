import hashlib
import json
from pathlib import Path

import pytest

from fakehw import cli
from fakehw.kb import updater
from fakehw.kb.updater import KbStore, KbUpdateError

KB = Path(__file__).parent / "fixtures" / "kb"
PCI_TEXT = (KB / "pci_fragment.ids").read_text(encoding="utf-8")
USB_TEXT = (KB / "usb_fragment.ids").read_text(encoding="utf-8")


def fetcher_for(mapping):
    def fetch(url: str) -> bytes:
        return mapping[url].encode("utf-8")

    return fetch


def test_no_cache_uses_bundled_snapshot(tmp_path):
    store = KbStore(cache_dir=tmp_path)
    st = store.status()["pci"]
    assert st["origin"] == "bundled"
    assert st["version"]
    assert store.pci().vendor_name(0x10DE) == "NVIDIA Corporation"


def test_bundled_meta_has_source_and_hash():
    meta = json.loads((updater.DATA_DIR / "snapshot.json").read_text(encoding="utf-8"))
    for kind in ("pci", "usb"):
        m = meta[kind]
        assert m["source_url"].startswith(("http://", "https://"))
        data = (updater.DATA_DIR / f"{kind}.ids").read_bytes()
        assert m["sha256"] == hashlib.sha256(data).hexdigest()
        assert m["version"]


def test_update_writes_cache_and_is_preferred(tmp_path):
    store = KbStore(cache_dir=tmp_path)
    fetch = fetcher_for({updater.SOURCES["pci"]: PCI_TEXT})
    result = store.update("pci", fetch=fetch)
    assert result["version"] == "2026.10.20"
    st = KbStore(cache_dir=tmp_path).status()["pci"]
    assert st["origin"] == "cache"
    assert st["version"] == "2026.10.20"
    assert st["sha256"] == hashlib.sha256(PCI_TEXT.encode()).hexdigest()
    assert st["source_url"] == updater.SOURCES["pci"]
    assert len(KbStore(cache_dir=tmp_path).pci().vendors) == 1  # fragment, proves cache is used


def test_update_all_kinds(tmp_path):
    store = KbStore(cache_dir=tmp_path)
    fetch = fetcher_for({updater.SOURCES["pci"]: PCI_TEXT, updater.SOURCES["usb"]: USB_TEXT})
    store.update("pci", fetch=fetch)
    store.update("usb", fetch=fetch)
    s = store.status()
    assert s["pci"]["origin"] == s["usb"]["origin"] == "cache"


def test_garbage_download_rejected_cache_untouched(tmp_path):
    store = KbStore(cache_dir=tmp_path)
    store.update("pci", fetch=fetcher_for({updater.SOURCES["pci"]: PCI_TEXT}))
    with pytest.raises(KbUpdateError):
        store.update("pci", fetch=fetcher_for({updater.SOURCES["pci"]: "<html>captive portal</html>"}))
    assert store.status()["pci"]["version"] == "2026.10.20"


def test_network_error_wrapped_and_offline_fallback_works(tmp_path):
    def boom(url):
        raise OSError("no network")

    store = KbStore(cache_dir=tmp_path)
    with pytest.raises(KbUpdateError):
        store.update("pci", fetch=boom)
    assert store.status()["pci"]["origin"] == "bundled"
    assert store.pci().vendor_name(0x10DE) == "NVIDIA Corporation"


def test_corrupt_cache_falls_back_to_bundled(tmp_path):
    (tmp_path / "pci.ids").write_text("garbage", encoding="utf-8")
    (tmp_path / "pci.meta.json").write_text("{not json", encoding="utf-8")
    store = KbStore(cache_dir=tmp_path)
    assert store.status()["pci"]["origin"] == "bundled"
    assert store.pci().vendor_name(0x10DE) == "NVIDIA Corporation"


def test_cache_with_tampered_hash_ignored(tmp_path):
    store = KbStore(cache_dir=tmp_path)
    store.update("pci", fetch=fetcher_for({updater.SOURCES["pci"]: PCI_TEXT}))
    (tmp_path / "pci.ids").write_text(PCI_TEXT + "\n# tampered\n", encoding="utf-8")
    assert KbStore(cache_dir=tmp_path).status()["pci"]["origin"] == "bundled"


def test_only_http_schemes_allowed(tmp_path):
    store = KbStore(cache_dir=tmp_path)
    with pytest.raises(KbUpdateError):
        store.update("pci", url="file:///etc/passwd", fetch=lambda u: b"")


def test_unknown_kind(tmp_path):
    with pytest.raises(KbUpdateError):
        KbStore(cache_dir=tmp_path).update("nope", fetch=lambda u: b"")


def test_default_cache_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKEHW_CACHE", str(tmp_path / "c"))
    assert updater.default_cache_dir() == tmp_path / "c"


# ---- CLI ----

def test_cli_kb_status(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKEHW_CACHE", str(tmp_path))
    assert cli.main(["kb", "status"]) == 0
    out = capsys.readouterr().out
    assert "pci" in out and "usb" in out and "bundled" in out


def test_cli_kb_update(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKEHW_CACHE", str(tmp_path))
    monkeypatch.setattr(
        updater, "default_fetch",
        fetcher_for({updater.SOURCES["pci"]: PCI_TEXT, updater.SOURCES["usb"]: USB_TEXT}),
    )
    assert cli.main(["kb", "update"]) == 0
    assert "2026.10.20" in capsys.readouterr().out
    assert KbStore(cache_dir=tmp_path).status()["usb"]["origin"] == "cache"


def test_cli_kb_update_failure_exit_code(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKEHW_CACHE", str(tmp_path))

    def boom(url):
        raise OSError("offline")

    monkeypatch.setattr(updater, "default_fetch", boom)
    assert cli.main(["kb", "update"]) == 1
    assert capsys.readouterr().err
