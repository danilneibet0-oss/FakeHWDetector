"""Scan orchestration shared by the CLI and the GUI: collect devices, evaluate rules, build a report."""

from datetime import datetime
from pathlib import Path
from typing import Callable

from .collectors._util import utcnow
from .collectors.base import Collector
from .kb import updater
from .kb.cpu_tables import CpuTables
from .kb.gpu_refs import GpuRefs
from .models.device import DeviceRecord
from .models.report import Report
from .rules.engine import Engine, EvalContext, Rule, load_rules
from .rules.scoring import virtualization_state

COLLECTORS = ("pci", "usb", "cpu", "ram", "storage", "gpu")


def build_collectors(only: list[str] | None, include_serials: bool, enable_spd: bool = False) -> list[Collector]:
    from .collectors.cpu import CpuCollector
    from .collectors.gpu import GpuCollector
    from .collectors.memory import MemoryCollector
    from .collectors.pci import PciCollector
    from .collectors.pnp import WmiPnpSource
    from .collectors.storage import StorageCollector
    from .collectors.usb import UsbCollector

    source = WmiPnpSource()  # shared so PnP is queried once
    makers = {
        "pci": lambda: PciCollector(source, include_gpu="gpu" not in (only or COLLECTORS)),
        "gpu": lambda: GpuCollector(source),
        "usb": lambda: UsbCollector(source, include_serials=include_serials),
        "cpu": lambda: CpuCollector(),
        "ram": lambda: MemoryCollector(include_serials=include_serials),
        "storage": lambda: StorageCollector(include_serials=include_serials),
    }
    collectors = [makers[name]() for name in (only or COLLECTORS)]
    if enable_spd:
        from .collectors.plugins.spd import SpdCollector

        collectors.append(SpdCollector(enabled=True, include_serials=include_serials))
    return collectors


def collect(collectors: list[Collector]) -> list[DeviceRecord]:
    devices: list[DeviceRecord] = []
    for collector in collectors:
        devices.extend(collector.collect())
    return devices


def assess(
    devices: list[DeviceRecord],
    rules: list[Rule] | None = None,
    lang: str = "en",
    store: updater.KbStore | None = None,
    generated_at: datetime | None = None,
) -> Report:
    store = store or updater.KbStore()
    rules = load_rules() if rules is None else rules
    ctx = EvalContext(
        pci=store.pci(), usb=store.usb(), cpu_tables=CpuTables.load(),
        virtualization=virtualization_state(devices), gpu_refs=GpuRefs.load(),
    )
    findings, assessments = Engine(rules, ctx, lang=lang).run(devices)
    return Report(
        generated_at=generated_at or utcnow(),
        devices=devices,
        findings=findings,
        assessments=assessments,
        kb_versions={k: v["version"] for k, v in store.status().items()},
    )


class ScanService:
    """What the GUI talks to: scan hardware, or re-evaluate an existing scan in another language."""

    def __init__(self, collector_factory: Callable = build_collectors, rules_dir: Path | None = None):
        self.collector_factory = collector_factory
        self.rules_dir = rules_dir
        self._store: updater.KbStore | None = None

    @property
    def store(self) -> updater.KbStore:
        if self._store is None:
            self._store = updater.KbStore()  # parsed once, reused when the language changes
        return self._store

    def scan(self, include_serials: bool, lang: str, only: list[str] | None = None, enable_spd: bool = False) -> Report:
        devices = collect(self.collector_factory(only, include_serials, enable_spd))
        return assess(devices, load_rules(self.rules_dir), lang, store=self.store)

    def reassess(self, report: Report, lang: str) -> Report:
        return assess(report.devices, load_rules(self.rules_dir), lang, store=self.store,
                      generated_at=report.generated_at)
