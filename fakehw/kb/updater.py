"""Knowledge-base storage: bundled snapshot, explicit-command update, verified local cache.

Nothing here touches the network unless `KbStore.update` is called.
"""

import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import branding, paths
from ._common import decode_ids
from .pci_ids import PciIds, parse_pci_ids
from .usb_ids import UsbIds, parse_usb_ids

DATA_DIR = Path(__file__).parent / "data"

# Official upstream locations. linux-usb.org serves usb.ids over plain http only (its TLS
# certificate does not match the host name), so downloads are validated by parsing - see OPEN_QUESTIONS.md.
SOURCES = {
    "pci": "https://pci-ids.ucw.cz/v2.2/pci.ids",
    "usb": "http://www.linux-usb.org/usb.ids",
}
_PARSERS = {"pci": parse_pci_ids, "usb": parse_usb_ids}
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024


class KbUpdateError(Exception):
    pass


def default_cache_dir() -> Path:
    override = os.environ.get("FAKEHW_CACHE")
    if override:
        return Path(override)
    portable = paths.portable_data_dir()
    if portable:
        return portable / "kb"
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / branding.APP_NAME / "kb"


def default_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"{branding.CLI_NAME}-kb-updater"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - scheme checked by caller
        data = resp.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise OSError("download too large")
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class KbStore:
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
        self._resolved: dict[str, tuple[bytes, dict]] = {}
        self._parsed: dict[str, object] = {}

    # ---- reading ----

    def _cache_entry(self, kind: str) -> tuple[bytes, dict] | None:
        data_path = self.cache_dir / f"{kind}.ids"
        meta_path = self.cache_dir / f"{kind}.meta.json"
        try:
            data = data_path.read_bytes()
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("sha256") != _sha256(data):
                return None
            db = _PARSERS[kind](decode_ids(data))
            if db.version is None or not db.vendors:
                return None
        except (OSError, ValueError, KeyError, AttributeError):
            return None
        return data, {**meta, "origin": "cache"}

    def _bundled_entry(self, kind: str) -> tuple[bytes, dict]:
        data = (DATA_DIR / f"{kind}.ids").read_bytes()
        snap = json.loads((DATA_DIR / "snapshot.json").read_text(encoding="utf-8"))[kind]
        return data, {**snap, "origin": "bundled"}

    def _resolve(self, kind: str) -> tuple[bytes, dict]:
        if kind not in _PARSERS:
            raise KbUpdateError(f"unknown knowledge base: {kind!r}")
        if kind not in self._resolved:
            self._resolved[kind] = self._cache_entry(kind) or self._bundled_entry(kind)
        return self._resolved[kind]

    def _db(self, kind: str):
        if kind not in self._parsed:
            data, _ = self._resolve(kind)
            self._parsed[kind] = _PARSERS[kind](decode_ids(data))
        return self._parsed[kind]

    def pci(self) -> PciIds:
        return self._db("pci")  # type: ignore[return-value]

    def usb(self) -> UsbIds:
        return self._db("usb")  # type: ignore[return-value]

    def status(self) -> dict[str, dict]:
        out = {}
        for kind in _PARSERS:
            data, meta = self._resolve(kind)
            db = self._db(kind)
            out[kind] = {
                "origin": meta["origin"],
                "version": db.version,
                "date": db.date,
                "source_url": meta.get("source_url"),
                "sha256": meta.get("sha256"),
                "retrieved_at": meta.get("retrieved_at"),
            }
        return out

    # ---- updating (explicit command only) ----

    def update(self, kind: str, url: str | None = None, fetch: Callable[[str], bytes] | None = None) -> dict:
        if kind not in _PARSERS:
            raise KbUpdateError(f"unknown knowledge base: {kind!r}")
        url = url or SOURCES[kind]
        if not url.startswith(("http://", "https://")):
            raise KbUpdateError("only http(s) URLs are allowed")
        fetch = fetch or default_fetch
        try:
            data = fetch(url)
        except Exception as e:  # network errors of any kind must not break the app
            raise KbUpdateError(f"download failed: {e}") from e
        db = _PARSERS[kind](decode_ids(data))
        if db.version is None or not db.vendors:
            raise KbUpdateError("downloaded file does not look like a valid ids database; cache not changed")

        meta = {
            "source_url": url,
            "sha256": _sha256(data),
            "version": db.version,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_data = self.cache_dir / f"{kind}.ids.tmp"
        tmp_meta = self.cache_dir / f"{kind}.meta.json.tmp"
        tmp_data.write_bytes(data)
        tmp_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        os.replace(tmp_data, self.cache_dir / f"{kind}.ids")
        os.replace(tmp_meta, self.cache_dir / f"{kind}.meta.json")
        self._resolved.pop(kind, None)
        self._parsed.pop(kind, None)
        return meta
