"""CPU signature -> microarchitecture / allowed brand patterns, loaded from a sourced data file.

The module holds no CPU data itself. Every entry in cpu_arch.yaml must state its `source`;
a signature that is not in the table makes the dependent rule "could not verify".
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

DATA_FILE = Path(__file__).parent / "data" / "cpu_arch.yaml"


class CpuTablesError(Exception):
    pass


@dataclass(frozen=True)
class CpuArchEntry:
    vendor: str
    family: int
    model: int
    microarch: str
    brand_patterns: tuple[re.Pattern, ...]
    source: str
    completeness: str = "partial"

    def matches(self, brand: str) -> bool:
        return any(p.search(brand) for p in self.brand_patterns)


@dataclass(frozen=True)
class CpuTables:
    entries: tuple[CpuArchEntry, ...]

    @classmethod
    def load(cls, path: Path | None = None) -> "CpuTables":
        path = Path(path) if path is not None else DATA_FILE
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as e:
            raise CpuTablesError(f"{path.name}: {e}") from e
        entries: list[CpuArchEntry] = []
        seen: set[tuple[str, int, int]] = set()
        for raw in (data or {}).get("entries", []):
            try:
                patterns = tuple(re.compile(p) for p in raw["brand_patterns"])
                entry = CpuArchEntry(
                    vendor=str(raw["vendor"]), family=int(raw["family"]), model=int(raw["model"]),
                    microarch=str(raw["microarch"]), brand_patterns=patterns,
                    source=str(raw["source"]).strip(), completeness=str(raw.get("completeness", "partial")),
                )
            except (KeyError, TypeError, ValueError, re.error) as e:
                raise CpuTablesError(f"{path.name}: invalid entry {raw!r}: {e}") from e
            if not entry.source or not entry.brand_patterns:
                raise CpuTablesError(f"{path.name}: entry needs a source and brand_patterns: {raw!r}")
            key = (entry.vendor, entry.family, entry.model)
            if key in seen:
                raise CpuTablesError(f"{path.name}: duplicate entry {key}")
            seen.add(key)
            entries.append(entry)
        return cls(tuple(entries))

    def lookup(self, vendor: str, family: int, model: int) -> CpuArchEntry | None:
        for e in self.entries:
            if (e.vendor, e.family, e.model) == (vendor, family, model):
                return e
        return None
