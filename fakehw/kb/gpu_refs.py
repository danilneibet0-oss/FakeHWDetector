"""GPU reference specs (VRAM sizes, bus widths, PCIe capability) per PCI device ID, from a sourced data file.

The module holds no GPU data itself. A device ID missing from the table makes the dependent rules
"could not verify".
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

DATA_FILE = Path(__file__).parent / "data" / "gpu_refs.yaml"
VRAM_LOW, VRAM_HIGH = 0.94, 1.02  # driver-reserved memory lowers the reported size by a few percent


class GpuRefsError(Exception):
    pass


@dataclass(frozen=True)
class GpuRefEntry:
    vendor: int
    device: int
    name: str
    vram_mib: tuple[int, ...]
    bus_width_bits: tuple[int, ...]
    pcie_max_gen: int
    pcie_max_width: int
    source: str
    completeness: str = "partial"

    def vram_matches(self, mib: float) -> bool:
        return any(VRAM_LOW * s <= mib <= VRAM_HIGH * s for s in self.vram_mib)


@dataclass(frozen=True)
class GpuRefs:
    entries: tuple[GpuRefEntry, ...]

    @classmethod
    def load(cls, path: Path | None = None) -> "GpuRefs":
        path = Path(path) if path is not None else DATA_FILE
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as e:
            raise GpuRefsError(f"{path.name}: {e}") from e
        entries: list[GpuRefEntry] = []
        seen: set[tuple[int, int]] = set()
        for raw in (data or {}).get("entries", []):
            try:
                entry = GpuRefEntry(
                    vendor=int(raw["vendor"]), device=int(raw["device"]), name=str(raw.get("name", "")),
                    vram_mib=tuple(int(x) for x in raw["vram_mib"]),
                    bus_width_bits=tuple(int(x) for x in raw["bus_width_bits"]),
                    pcie_max_gen=int(raw["pcie_max_gen"]), pcie_max_width=int(raw["pcie_max_width"]),
                    source=str(raw["source"]).strip(), completeness=str(raw.get("completeness", "partial")),
                )
            except (KeyError, TypeError, ValueError) as e:
                raise GpuRefsError(f"{path.name}: invalid entry {raw!r}: {e}") from e
            if not entry.source or not entry.vram_mib or not entry.bus_width_bits:
                raise GpuRefsError(f"{path.name}: entry needs source, vram_mib and bus_width_bits: {raw!r}")
            key = (entry.vendor, entry.device)
            if key in seen:
                raise GpuRefsError(f"{path.name}: duplicate entry {key}")
            seen.add(key)
            entries.append(entry)
        return cls(tuple(entries))

    def lookup(self, vendor: int, device: int) -> GpuRefEntry | None:
        for e in self.entries:
            if (e.vendor, e.device) == (vendor, device):
                return e
        return None
