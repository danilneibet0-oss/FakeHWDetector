"""Capture collector fixtures from the current machine.

Usage:  python tools/capture_fixtures.py [output_dir]

Writes local_pnp.json and local_cpuid.json, plus hand-edited CPUID variants used by tests
(edited_* files are derived from the real capture and say so in their "note" field).
USB serial numbers in the dump are replaced by deterministic fake ones before saving.
"""

import copy
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fakehw.collectors.cpu import capture_leaves, leaf_key  # noqa: E402
from fakehw.collectors.pnp import WmiPnpSource  # noqa: E402
from fakehw.collectors.memory import WmiMemorySource  # noqa: E402
from fakehw.collectors.storage import WmiStorageSource  # noqa: E402
from fakehw.collectors import _gpu_io, _storage_io  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "collectors"
_USB_ID = re.compile(r"^(USB\\VID_[0-9A-Fa-f]{4}&PID_[0-9A-Fa-f]{4})\\([^&\\]+)$")


def sanitize(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        e = dict(e)
        m = _USB_ID.match(e["DeviceID"])
        if m:  # no '&' in the instance part -> a real device serial
            fake = "SN" + hashlib.sha1(m[2].encode()).hexdigest()[:8].upper()
            e["DeviceID"] = f"{m[1]}\\{fake}"
        out.append(e)
    return sorted(out, key=lambda e: e["DeviceID"])


def fake_serial(real: str) -> str:
    return "SN" + hashlib.sha1(real.strip().encode()).hexdigest()[:8].upper()


def capture_memory_storage(out: Path) -> None:
    mem = WmiMemorySource().query()
    for m in mem:
        if m.get("SerialNumber"):
            m["SerialNumber"] = fake_serial(m["SerialNumber"])
    write(out / "local_memory.json", {
        "note": "Real Win32_PhysicalMemory dump from the developer machine; serials replaced.", "entries": mem})

    disks = WmiStorageSource().query()
    identify = {}
    for d in disks:
        real_serial = (d.get("SerialNumber") or "").strip()
        d["SerialNumber"] = fake_serial(real_serial) if real_serial else d.get("SerialNumber")
        if d.get("BusType") == "NVMe":
            raw = bytearray(_storage_io.read_nvme_identify(int(d["Index"])))
            raw[4:24] = fake_serial(bytes(raw[4:24]).strip(b"\x00 ").decode("ascii", "replace")).encode().ljust(20, b" ")
            identify[str(d["Index"])] = raw.hex()
    write(out / "local_storage.json", {
        "note": "Real Win32_DiskDrive + Get-PhysicalDisk dump from the developer machine; serials replaced.",
        "entries": disks})
    write(out / "local_nvme_identify.json", {
        "note": "Real NVMe Identify Controller data (4096 bytes, hex) keyed by disk index; serial number replaced.",
        "identify": identify})


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", path)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    write(out / "local_pnp.json", {
        "note": "Real dump of Win32_PnPEntity (PCI/USB) from the developer machine; USB serials replaced.",
        "entries": sanitize(WmiPnpSource().query()),
    })

    capture_memory_storage(out)

    write(out / "local_gpu_probe.json", {
        "note": "Real DXGI adapters and NVML devices from the developer machine.",
        "dxgi": _gpu_io.dxgi_adapters(), "nvml": _gpu_io.nvml_devices(),
    })

    leaves = capture_leaves()
    write(out / "local_cpuid.json", {"note": "Real CPUID capture from the developer machine.", "leaves": leaves})

    bare = copy.deepcopy(leaves)
    bare[leaf_key(1)][2] &= ~(1 << 31)
    bare.pop(leaf_key(0x40000000), None)
    write(out / "edited_bare_metal_cpuid.json", {
        "note": "HAND-EDITED copy of local_cpuid.json: hypervisor bit cleared, leaf 0x40000000 removed.",
        "leaves": bare,
    })

    swapped = copy.deepcopy(leaves)
    new_brand = "Intel(R) Core(TM) i9-12900K CPU @ 3.20GHz".encode("ascii").ljust(48, b"\x00")
    for i, leaf in enumerate((0x80000002, 0x80000003, 0x80000004)):
        swapped[leaf_key(leaf)] = [int.from_bytes(new_brand[16 * i + 4 * j : 16 * i + 4 * j + 4], "little") for j in range(4)]
    write(out / "edited_brand_cpuid.json", {
        "note": "HAND-EDITED copy of local_cpuid.json: brand string replaced, signature untouched.",
        "leaves": swapped,
    })


if __name__ == "__main__":
    main()
