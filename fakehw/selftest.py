"""`fakehw selftest`: checks that every bundled resource loads. Useful right after installing or on a clean VM."""

from typing import Callable


def _rules() -> str:
    from .rules.engine import load_rules

    return f"{len(load_rules())} rules"


def _kb(kind: str) -> Callable[[], str]:
    def check() -> str:
        from .kb.updater import KbStore

        store = KbStore()
        db = store.pci() if kind == "pci" else store.usb()
        if db.parse_errors or not db.vendors:
            raise RuntimeError(f"{kind}.ids did not parse cleanly")
        return f"version {db.version}, {len(db.vendors)} vendors"

    return check


def _cpu_arch() -> str:
    from .kb.cpu_tables import CpuTables

    return f"{len(CpuTables.load().entries)} entries"


def _gpu_refs() -> str:
    from .kb.gpu_refs import GpuRefs

    return f"{len(GpuRefs.load().entries)} entries"


CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("rules", _rules), ("pci.ids", _kb("pci")), ("usb.ids", _kb("usb")),
    ("cpu_arch", _cpu_arch), ("gpu_refs", _gpu_refs),
]


def run() -> int:
    failed = 0
    for name, check in CHECKS:
        try:
            print(f"OK    {name}: {check()}")
        except Exception as e:  # report every problem instead of stopping at the first
            failed += 1
            print(f"FAIL  {name}: {e}")
    return 1 if failed else 0
