import re

from ..models.device import DeviceClass, DeviceRecord
from ._util import Clock, failure_record, utcnow
from .base import Collector
from .pnp import SOURCE_NAME, PnpQueryError, PnpSource, WmiPnpSource

_DEVICE_ID = re.compile(
    r"^PCI\\VEN_(?P<ven>[0-9A-Fa-f]{4})&DEV_(?P<dev>[0-9A-Fa-f]{4})"
    r"(?:&SUBSYS_(?P<sdev>[0-9A-Fa-f]{4})(?P<svid>[0-9A-Fa-f]{4}))?"
    r"(?:&REV_(?P<rev>[0-9A-Fa-f]{2}))?(?:&CC_[0-9A-Fa-f]+)?\\(?P<inst>.*)$"
)
_CC = re.compile(r"CC_([0-9A-Fa-f]{6})(?![0-9A-Fa-f])")


def _class_code(entry: dict) -> str | None:
    for s in [*entry.get("HardwareID", []), *entry.get("CompatibleID", [])]:
        m = _CC.search(s)
        if m:
            return m.group(1).upper()
    return None


class PciCollector(Collector):
    def __init__(self, source: PnpSource | None = None, include_gpu: bool = True, clock: Clock = utcnow):
        self.source = source or WmiPnpSource()
        self.include_gpu = include_gpu
        self.clock = clock

    def collect(self) -> list[DeviceRecord]:
        try:
            entries = self.source.query()
        except PnpQueryError as e:
            return [failure_record(DeviceClass.PCI, SOURCE_NAME, str(e), self.clock)]

        records: list[DeviceRecord] = []
        for e in entries:
            did = e.get("DeviceID") or ""
            if not did.upper().startswith("PCI\\") or e.get("Present") is False:
                continue
            m = _DEVICE_ID.match(did)
            strings = {k: e[k] for k in ("Name", "Manufacturer", "PNPClass") if e.get(k)}
            strings = {k.lower() if k != "PNPClass" else "pnp_class": v for k, v in strings.items()}
            if not m:
                records.append(DeviceRecord(
                    device_class=DeviceClass.PCI, source=SOURCE_NAME, strings=strings,
                    collected_at=self.clock(), errors=[f"unparsable PCI device id: {did}"],
                ))
                continue
            raw = {"vendor_id": m["ven"].upper(), "device_id": m["dev"].upper()}
            if m["svid"]:
                raw["subsys_vendor_id"] = m["svid"].upper()
                raw["subsys_device_id"] = m["sdev"].upper()
            if m["rev"]:
                raw["revision"] = m["rev"].upper()
            cc = _class_code(e)
            if cc:
                raw["class_code"] = cc
            strings["instance_id"] = m["inst"]
            records.append(DeviceRecord(
                device_class=DeviceClass.GPU if cc and cc.startswith("03") else DeviceClass.PCI,
                source=SOURCE_NAME, raw_ids=raw, strings=strings, collected_at=self.clock(),
            ))
        if not self.include_gpu:
            records = [r for r in records if r.device_class is not DeviceClass.GPU]
        return sorted(records, key=lambda r: (tuple(sorted(r.raw_ids.items())), r.strings.get("instance_id", ""), r.errors))
