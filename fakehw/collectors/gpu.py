"""GPU collector: PCI GPU records enriched with DXGI (VRAM, name) and NVML (bus width, PCIe link) data."""

from typing import Callable

from ..models.device import DeviceClass, DeviceRecord
from . import _gpu_io
from ._gpu_io import GpuProbeUnavailable
from ._util import Clock, failure_record, utcnow
from .base import Collector
from .pci import PciCollector
from .pnp import SOURCE_NAME, PnpQueryError, WmiPnpSource

SOFTWARE_VENDOR = 0x1414  # Microsoft Basic Render Driver

Probe = Callable[[], tuple[list[dict], list[dict]]]


def default_probe() -> tuple[list[dict], list[dict]]:
    adapters = _gpu_io.dxgi_adapters()  # raises GpuProbeUnavailable when DXGI cannot be used
    try:
        nvml = _gpu_io.nvml_devices()
    except GpuProbeUnavailable:
        nvml = []  # no NVIDIA driver: other vendors simply have no NVML data
    return adapters, nvml


class _Static:
    def __init__(self, entries):
        self.entries = entries

    def query(self):
        return self.entries


def _ids(record: DeviceRecord) -> tuple[int, int, int | None, int | None]:
    raw = record.raw_ids
    sub_v = int(raw["subsys_vendor_id"], 16) if "subsys_vendor_id" in raw else None
    sub_d = int(raw["subsys_device_id"], 16) if "subsys_device_id" in raw else None
    return int(raw["vendor_id"], 16), int(raw["device_id"], 16), sub_v, sub_d


def _take(candidates: list[dict], used: set[int], vendor: int, device: int, sub_v, sub_d, key) -> dict | None:
    """First unused probe entry with the same IDs (identical cards consume entries in order)."""
    for i, c in enumerate(candidates):
        if i in used:
            continue
        v, d, s = key(c)
        if (v, d) != (vendor, device):
            continue
        if sub_v is not None and sub_d is not None and (s & 0xFFFF, s >> 16) != (sub_v, sub_d):
            continue
        used.add(i)
        return c
    return None


class GpuCollector(Collector):
    def __init__(self, source=None, probe: Probe = default_probe, clock: Clock = utcnow):
        self.source = source or WmiPnpSource()
        self.probe = probe
        self.clock = clock

    def collect(self) -> list[DeviceRecord]:
        try:
            entries = self.source.query()
        except PnpQueryError as e:
            return [failure_record(DeviceClass.GPU, SOURCE_NAME, str(e), self.clock)]
        gpus = [r for r in PciCollector(_Static(entries), clock=self.clock).collect()
                if r.device_class is DeviceClass.GPU and r.raw_ids]
        try:
            dxgi, nvml = self.probe()
            note = None
        except GpuProbeUnavailable as e:
            dxgi, nvml, note = [], [], f"GPU probe unavailable: {e}"

        dxgi = [a for a in dxgi if a["vendor_id"] != SOFTWARE_VENDOR]
        used_d: set[int] = set()
        used_n: set[int] = set()
        out = []
        for rec in gpus:
            vendor, device, sub_v, sub_d = _ids(rec)
            raw, strings, source = dict(rec.raw_ids), dict(rec.strings), rec.source
            a = _take(dxgi, used_d, vendor, device, sub_v, sub_d,
                      lambda c: (c["vendor_id"], c["device_id"], c["subsys_id"]))
            if a:
                source += "+dxgi"
                raw["vram_dedicated_bytes"] = str(a["dedicated_video_memory"])
                strings["dxgi_description"] = a["description"]
            n = _take(nvml, used_n, vendor, device, sub_v, sub_d,
                      lambda c: (c.get("pci_device_id", 0) & 0xFFFF, c.get("pci_device_id", 0) >> 16,
                                 c.get("pci_subsystem_id", 0)))
            if n:
                source += "+nvml"
                for key, name in (("memory_total", "nvml_vram_total_bytes"), ("memory_bus_width", "mem_bus_width_bits"),
                                  ("pcie_gen_current", "pcie_gen_current"), ("pcie_gen_max", "pcie_gen_max"),
                                  ("pcie_width_current", "pcie_width_current"), ("pcie_width_max", "pcie_width_max")):
                    if key in n:
                        raw[name] = str(n[key])
                if n.get("name"):
                    strings["nvml_name"] = n["name"]
            errors = list(rec.errors) + ([note] if note else [])
            out.append(rec.model_copy(update={"raw_ids": raw, "strings": strings, "source": source, "errors": errors}))
        return out
