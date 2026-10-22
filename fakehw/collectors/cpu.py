"""CPU collector: raw CPUID first (family/model/stepping, brand string, hypervisor), registry as fallback.

This module only decodes what the CPU reports. It contains no tables of known CPUs; judging
whether the values are plausible belongs to the rules (iteration 4).
"""

import re
from dataclasses import dataclass
from typing import Callable

from ..models.device import DeviceClass, DeviceRecord
from ._cpuid import CpuidUnavailable, cpuid
from ._util import Clock, failure_record, utcnow
from .base import Collector

__all__ = ["CpuCollector", "CpuInfo", "CpuidUnavailable", "capture_leaves", "decode_leaves", "parse_registry_identifier"]

Leaves = dict[str, list[int]]


def leaf_key(leaf: int, sub: int = 0) -> str:
    return f"0x{leaf:08x}:{sub}"


@dataclass(frozen=True)
class CpuInfo:
    vendor: str | None
    family: int
    model: int
    stepping: int
    signature: int | None
    brand: str | None
    hypervisor_present: bool | None  # None = unknown
    hypervisor_vendor: str | None


def capture_leaves(fn: Callable[[int, int], tuple[int, int, int, int]] = cpuid) -> Leaves:
    leaves: Leaves = {}

    def grab(leaf: int, sub: int = 0):
        leaves[leaf_key(leaf, sub)] = list(fn(leaf, sub))

    grab(0)
    max_basic = leaves[leaf_key(0)][0]
    grab(1)
    if max_basic >= 7:
        grab(7, 0)
    if leaves[leaf_key(1)][2] & (1 << 31):
        grab(0x40000000)  # only meaningful when the hypervisor bit is set
    grab(0x80000000)
    max_ext = leaves[leaf_key(0x80000000)][0]
    for leaf in range(0x80000001, min(max_ext, 0x80000004) + 1):
        grab(leaf)
    return leaves


def _ascii(regs: list[int]) -> str:
    return b"".join(r.to_bytes(4, "little") for r in regs).decode("ascii", "replace")


def decode_leaves(leaves: Leaves) -> CpuInfo:
    l0, l1 = leaves.get(leaf_key(0)), leaves.get(leaf_key(1))
    if l1 is None:
        raise ValueError("CPUID leaf 1 is missing")
    vendor = _ascii([l0[1], l0[3], l0[2]]).strip("\x00 ") if l0 else None

    eax = l1[0]
    stepping, model, family = eax & 0xF, (eax >> 4) & 0xF, (eax >> 8) & 0xF
    ext_model, ext_family = (eax >> 16) & 0xF, (eax >> 20) & 0xFF
    if family == 0xF:
        disp_family = family + ext_family
    else:
        disp_family = family
    disp_model = model | (ext_model << 4) if family in (0x6, 0xF) else model

    brand = None
    ext0 = leaves.get(leaf_key(0x80000000))
    parts = [leaves.get(leaf_key(n)) for n in (0x80000002, 0x80000003, 0x80000004)]
    if ext0 and ext0[0] >= 0x80000004 and all(parts):
        raw = "".join(_ascii(p) for p in parts)  # type: ignore[arg-type]
        brand = raw.split("\x00", 1)[0].strip() or None

    hyper = bool(l1[2] & (1 << 31))
    hyper_vendor = None
    hv = leaves.get(leaf_key(0x40000000))
    if hyper and hv:
        hyper_vendor = _ascii([hv[1], hv[2], hv[3]]).strip("\x00 ") or None

    return CpuInfo(vendor, disp_family, disp_model, stepping, eax, brand, hyper, hyper_vendor)


_REG_ID = re.compile(r"Family (\d+) Model (\d+) Stepping (\d+)")


def parse_registry_identifier(identifier: str) -> tuple[int, int, int] | None:
    m = _REG_ID.search(identifier)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def read_registry() -> dict:
    import winreg

    key = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
        return {
            "vendor": winreg.QueryValueEx(k, "VendorIdentifier")[0],
            "brand": winreg.QueryValueEx(k, "ProcessorNameString")[0].strip(),
            "identifier": winreg.QueryValueEx(k, "Identifier")[0],
        }


class CpuCollector(Collector):
    def __init__(
        self,
        leaves_source: Callable[[], Leaves] = capture_leaves,
        registry_source: Callable[[], dict] = read_registry,
        clock: Clock = utcnow,
    ):
        self.leaves_source = leaves_source
        self.registry_source = registry_source
        self.clock = clock

    def collect(self) -> list[DeviceRecord]:
        notes: list[str] = []
        try:
            return [self._from_cpuid(decode_leaves(self.leaves_source()))]
        except (CpuidUnavailable, OSError, ValueError, KeyError, IndexError) as e:
            notes.append(f"CPUID unavailable: {e}")
        try:
            return [self._from_registry(self.registry_source(), notes)]
        except (OSError, ValueError, KeyError, ImportError) as e:
            notes.append(f"registry unavailable: {e}")
        return [failure_record(DeviceClass.CPU, "cpuid", "; ".join(notes), self.clock)]

    def _from_cpuid(self, info: CpuInfo) -> DeviceRecord:
        raw = {
            "family": str(info.family), "model": str(info.model), "stepping": str(info.stepping),
            "hypervisor_present": "true" if info.hypervisor_present else "false",
        }
        if info.signature is not None:
            raw["signature"] = f"{info.signature:08X}"
        strings = {}
        for k, v in (("vendor", info.vendor), ("brand", info.brand), ("hypervisor_vendor", info.hypervisor_vendor)):
            if v:
                strings[k] = v
        return DeviceRecord(device_class=DeviceClass.CPU, source="cpuid", raw_ids=raw, strings=strings, collected_at=self.clock())

    def _from_registry(self, reg: dict, notes: list[str]) -> DeviceRecord:
        parsed = parse_registry_identifier(reg.get("identifier", ""))
        raw = {"hypervisor_present": "unknown"}
        errors = list(notes)
        if parsed:
            raw.update(family=str(parsed[0]), model=str(parsed[1]), stepping=str(parsed[2]))
        else:
            errors.append("registry identifier not parsable")
        strings = {k: reg[k] for k in ("vendor", "brand") if reg.get(k)}
        return DeviceRecord(
            device_class=DeviceClass.CPU, source="registry", raw_ids=raw, strings=strings,
            collected_at=self.clock(), errors=errors if not parsed else [],
        )
