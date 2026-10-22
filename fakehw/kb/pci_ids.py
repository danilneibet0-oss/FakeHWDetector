"""Parser for the pci.ids database (https://pci-ids.ucw.cz/). No IDs are hardcoded here."""

import re
from dataclasses import dataclass, field

from ._common import HEX2, HEX4, ClassEntry, SubclassEntry, class_lookup, iter_lines, parse_header

_VENDOR = re.compile(rf"^({HEX4})  +(\S.*)$")
_CLASS = re.compile(rf"^C ({HEX2})  +(\S.*)$")
_DEVICE = re.compile(rf"^({HEX4})  +(\S.*)$")
_SUBSYS = re.compile(rf"^({HEX4}) ({HEX4})  +(\S.*)$")
_PROG = re.compile(rf"^({HEX2})  +(\S.*)$")


@dataclass
class PciDevice:
    name: str
    subsystems: dict[tuple[int, int], str] = field(default_factory=dict)


@dataclass
class PciVendor:
    name: str
    devices: dict[int, PciDevice] = field(default_factory=dict)


@dataclass
class PciIds:
    version: str | None = None
    date: str | None = None
    vendors: dict[int, PciVendor] = field(default_factory=dict)
    classes: dict[int, ClassEntry] = field(default_factory=dict)
    parse_errors: int = 0

    def has_vendor(self, vid: int) -> bool:
        return vid in self.vendors

    def has_device(self, vid: int, did: int) -> bool:
        v = self.vendors.get(vid)
        return v is not None and did in v.devices

    def vendor_name(self, vid: int) -> str | None:
        v = self.vendors.get(vid)
        return v.name if v else None

    def device_name(self, vid: int, did: int) -> str | None:
        v = self.vendors.get(vid)
        d = v.devices.get(did) if v else None
        return d.name if d else None

    def subsystem_name(self, vid: int, did: int, svid: int, sdid: int) -> str | None:
        v = self.vendors.get(vid)
        d = v.devices.get(did) if v else None
        return d.subsystems.get((svid, sdid)) if d else None

    def class_name(self, cls: int, sub: int | None = None, prog: int | None = None) -> str | None:
        return class_lookup(self.classes, cls, sub, prog)


def parse_pci_ids(text: str) -> PciIds:
    db = PciIds()
    db.version, db.date = parse_header(text)
    mode: str | None = None  # "vendor" | "class"
    vendor: PciVendor | None = None
    device: PciDevice | None = None
    cls: ClassEntry | None = None
    sub: SubclassEntry | None = None

    for tabs, content in iter_lines(text):
        if tabs == 0:
            vendor = device = cls = sub = None
            m = _CLASS.match(content)
            if m:
                mode = "class"
                cls = db.classes.setdefault(int(m[1], 16), ClassEntry(m[2]))
                continue
            m = _VENDOR.match(content)
            if m:
                mode = "vendor"
                vendor = db.vendors.setdefault(int(m[1], 16), PciVendor(m[2]))
                continue
            mode = None
            db.parse_errors += 1
        elif tabs == 1:
            if mode == "vendor" and vendor is not None:
                m = _DEVICE.match(content)
                if m:
                    device = vendor.devices.setdefault(int(m[1], 16), PciDevice(m[2]))
                    continue
                device = None
            elif mode == "class" and cls is not None:
                m = _PROG.match(content)
                if m:
                    sub = cls.subclasses.setdefault(int(m[1], 16), SubclassEntry(m[2]))
                    continue
                sub = None
            db.parse_errors += 1
        elif tabs == 2:
            if mode == "vendor" and device is not None:
                m = _SUBSYS.match(content)
                if m:
                    device.subsystems[(int(m[1], 16), int(m[2], 16))] = m[3]
                    continue
            elif mode == "class" and sub is not None:
                m = _PROG.match(content)
                if m:
                    sub.prog_ifs[int(m[1], 16)] = m[2]
                    continue
            db.parse_errors += 1
        else:
            db.parse_errors += 1
    return db
