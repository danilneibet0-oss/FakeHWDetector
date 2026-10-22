"""Signal providers: turn a DeviceRecord plus knowledge bases into named facts for rule conditions.

A signal is True/False, or None when the data needed to decide is not available - the engine then
reports the rule as "could not verify" instead of guessing.
"""

import re
from typing import Any

from ..collectors._placeholder import is_placeholder_text, names_match
from ..models.device import DeviceRecord

_COUNTERFEIT = re.compile(r"\b(counterfeit|fake)\b", re.I)
_INTEL = re.compile(r"\bIntel\b")
_AMD = re.compile(r"\bAMD\b")


def _hex(raw: dict[str, str], key: str) -> int | None:
    v = raw.get(key)
    try:
        return int(v, 16) if v else None
    except ValueError:
        return None


def _int(raw: dict[str, str], key: str) -> int | None:
    try:
        return int(raw[key])
    except (KeyError, ValueError):
        return None


def compute_signals(device: DeviceRecord, ctx) -> dict[str, Any]:
    cls = device.device_class.value
    if cls in ("pci", "gpu"):
        sig = _pci_signals(device, ctx)
        return {**sig, **_gpu_signals(device, ctx)} if cls == "gpu" else sig
    if cls == "usb":
        return _usb_signals(device, ctx)
    if cls == "cpu":
        return _cpu_signals(device, ctx)
    if cls == "ram":
        return _ram_signals(device, ctx)
    if cls == "storage":
        return _storage_signals(device, ctx)
    return {}


def _odd_parity(byte: int) -> bool:
    return bin(byte).count("1") % 2 == 1


def _flag(raw: dict[str, str], key: str) -> bool | None:
    v = raw.get(key)
    return None if v is None else v == "true"


def _placeholder_shape(raw: dict[str, str]) -> bool | None:
    shape = raw.get("serial_shape")
    return None if shape is None else shape != "normal"


def _ram_signals(device: DeviceRecord, ctx) -> dict[str, Any]:
    sig: dict[str, Any] = {}
    code = device.raw_ids.get("manufacturer_code")
    if code and len(code) == 4:
        try:
            sig["jedec_parity_ok"] = all(_odd_parity(b) for b in bytes.fromhex(code))
        except ValueError:
            pass
    part = device.strings.get("part_number")
    if part is not None:
        sig["part_number_placeholder"] = is_placeholder_text(part)
    placeholder = _placeholder_shape(device.raw_ids)
    if placeholder is not None:
        sig["serial_placeholder"] = placeholder
    return sig


def _storage_signals(device: DeviceRecord, ctx) -> dict[str, Any]:
    sig: dict[str, Any] = {}
    placeholder = _placeholder_shape(device.raw_ids)
    if placeholder is not None:
        sig["serial_placeholder"] = placeholder
    vid = _hex(device.raw_ids, "nvme_vid")
    if vid is not None and ctx.pci is not None:
        sig["nvme_vid_known"] = ctx.pci.has_vendor(vid)
    for key in ("identify_model_matches", "size_exceeds_nvme_capacity"):
        flag = _flag(device.raw_ids, key)
        if flag is not None:
            sig[key] = flag
    return sig


def _pci_signals(device: DeviceRecord, ctx) -> dict[str, Any]:
    db = ctx.pci
    vid, did = _hex(device.raw_ids, "vendor_id"), _hex(device.raw_ids, "device_id")
    if db is None or vid is None or did is None:
        return {}
    name = db.device_name(vid, did)
    sig: dict[str, Any] = {
        "vendor_known": db.has_vendor(vid),
        "device_known": db.has_device(vid, did),
        "db_marks_counterfeit": bool(name and _COUNTERFEIT.search(name)),
    }
    svid, sdid = _hex(device.raw_ids, "subsys_vendor_id"), _hex(device.raw_ids, "subsys_device_id")
    if svid is not None and sdid is not None:
        present = (svid, sdid) != (0, 0)
        sig["subsys_present"] = present
        # "present and registered"; False when there is no subsystem so conditions stay decidable
        sig["subsys_vendor_known"] = present and db.has_vendor(svid)
    return sig


def _usb_signals(device: DeviceRecord, ctx) -> dict[str, Any]:
    db = ctx.usb
    vid, pid = _hex(device.raw_ids, "vendor_id"), _hex(device.raw_ids, "product_id")
    if db is None or vid is None or pid is None:
        return {}
    name = db.device_name(vid, pid)
    return {
        "vendor_known": db.has_vendor(vid),
        "device_known": db.has_device(vid, pid),
        "db_marks_counterfeit": bool(name and _COUNTERFEIT.search(name)),
    }


def _cpu_signals(device: DeviceRecord, ctx) -> dict[str, Any]:
    vendor, brand = device.strings.get("vendor"), device.strings.get("brand")
    family, model = _int(device.raw_ids, "family"), _int(device.raw_ids, "model")
    sig: dict[str, Any] = {}

    if vendor and brand:
        has_intel, has_amd = bool(_INTEL.search(brand)), bool(_AMD.search(brand))
        if has_intel and not has_amd:
            sig["brand_vendor_mismatch"] = vendor != "GenuineIntel"
        elif has_amd and not has_intel:
            sig["brand_vendor_mismatch"] = vendor != "AuthenticAMD"

    if ctx.cpu_tables is not None and vendor and family is not None and model is not None:
        entry = ctx.cpu_tables.lookup(vendor, family, model)
        sig["arch_known"] = entry is not None
        if entry is not None and brand:
            sig["brand_matches_arch"] = entry.matches(brand)
    return sig


def _gpu_signals(device: DeviceRecord, ctx) -> dict[str, Any]:
    raw = device.raw_ids
    sig: dict[str, Any] = {}
    dxgi, nvml = _int(raw, "vram_dedicated_bytes"), _int(raw, "nvml_vram_total_bytes")
    if dxgi is not None and nvml is not None and max(dxgi, nvml) > 0:
        sig["vram_sources_disagree"] = abs(dxgi - nvml) / max(dxgi, nvml) > 0.10

    width = _int(raw, "mem_bus_width_bits")
    if width is not None:
        sig["bus_width_valid"] = width > 0 and width % 32 == 0

    cur_g, max_g = _int(raw, "pcie_gen_current"), _int(raw, "pcie_gen_max")
    cur_w, max_w = _int(raw, "pcie_width_current"), _int(raw, "pcie_width_max")
    if None not in (cur_g, max_g, cur_w, max_w):
        sig["pcie_link_consistent"] = cur_g <= max_g and cur_w <= max_w

    vid, did = _hex(raw, "vendor_id"), _hex(raw, "device_id")
    ref = ctx.gpu_refs.lookup(vid, did) if ctx.gpu_refs is not None and vid is not None and did is not None else None
    if ref is not None:
        vram = nvml if nvml is not None else dxgi
        if vram is not None:
            sig["vram_matches_reference"] = ref.vram_matches(vram / (1024 * 1024))
        if width is not None:
            sig["bus_width_matches_reference"] = width in ref.bus_width_bits
        if max_g is not None and max_w is not None:
            sig["pcie_exceeds_reference"] = max_g > ref.pcie_max_gen or max_w > ref.pcie_max_width

    desc = device.strings.get("dxgi_description") or device.strings.get("nvml_name")
    if desc and ctx.pci is not None and vid is not None and did is not None:
        registered = ctx.pci.device_name(vid, did)
        if registered:
            sig["name_matches_pci_ids"] = _name_matches_registered(desc, registered)
    return sig


def _name_matches_registered(description: str, registered: str) -> bool:
    """pci.ids names look like "GA104 [GeForce RTX 3060 Ti]"; compare with the marketing name in brackets."""
    bracket = re.findall(r"\[([^\]]+)\]", registered)
    candidates = [part.strip() for part in (bracket[-1] if bracket else registered).split("/")]
    return any(names_match(description, c) for c in candidates if c)
