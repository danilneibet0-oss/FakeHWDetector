"""Parser for the usb.ids database (http://www.linux-usb.org/usb-ids.html). No IDs are hardcoded here."""

import re
from dataclasses import dataclass, field

from ._common import HEX2, HEX4, ClassEntry, SubclassEntry, class_lookup, iter_lines, parse_header

_KEYWORD = re.compile(r"^(C|AT|HID|R|BIAS|PHY|HUT|L|HCC|VT) ")
_VENDOR = re.compile(rf"^({HEX4})  +(\S.*)$")
_CLASS = re.compile(rf"^C ({HEX2})  +(\S.*)$")
_DEVICE = re.compile(rf"^({HEX4})  +(\S.*)$")
_BYTE = re.compile(rf"^({HEX2})  +(\S.*)$")


@dataclass
class UsbDevice:
    name: str
    interfaces: dict[int, str] = field(default_factory=dict)


@dataclass
class UsbVendor:
    name: str
    devices: dict[int, UsbDevice] = field(default_factory=dict)


@dataclass
class UsbIds:
    version: str | None = None
    date: str | None = None
    vendors: dict[int, UsbVendor] = field(default_factory=dict)
    classes: dict[int, ClassEntry] = field(default_factory=dict)
    parse_errors: int = 0

    def has_vendor(self, vid: int) -> bool:
        return vid in self.vendors

    def has_device(self, vid: int, pid: int) -> bool:
        v = self.vendors.get(vid)
        return v is not None and pid in v.devices

    def vendor_name(self, vid: int) -> str | None:
        v = self.vendors.get(vid)
        return v.name if v else None

    def device_name(self, vid: int, pid: int) -> str | None:
        v = self.vendors.get(vid)
        d = v.devices.get(pid) if v else None
        return d.name if d else None

    def class_name(self, cls: int, sub: int | None = None, proto: int | None = None) -> str | None:
        return class_lookup(self.classes, cls, sub, proto)


def parse_usb_ids(text: str) -> UsbIds:
    db = UsbIds()
    db.version, db.date = parse_header(text)
    mode: str | None = None  # "vendor" | "class" | "other"
    vendor: UsbVendor | None = None
    device: UsbDevice | None = None
    cls: ClassEntry | None = None
    sub: SubclassEntry | None = None

    for tabs, content in iter_lines(text):
        if mode == "other" and tabs > 0:
            continue  # HID/HUT/language/... tables are not used
        if tabs == 0:
            vendor = device = cls = sub = None
            kw = _KEYWORD.match(content)
            if kw:
                m = _CLASS.match(content) if kw[1] == "C" else None
                if m:
                    mode = "class"
                    cls = db.classes.setdefault(int(m[1], 16), ClassEntry(m[2]))
                else:
                    mode = "other"
                    if kw[1] == "C":
                        db.parse_errors += 1
                continue
            m = _VENDOR.match(content)
            if m:
                mode = "vendor"
                vendor = db.vendors.setdefault(int(m[1], 16), UsbVendor(m[2]))
                continue
            mode = None
            db.parse_errors += 1
        elif tabs == 1:
            if mode == "vendor" and vendor is not None:
                m = _DEVICE.match(content)
                if m:
                    device = vendor.devices.setdefault(int(m[1], 16), UsbDevice(m[2]))
                    continue
                device = None
            elif mode == "class" and cls is not None:
                m = _BYTE.match(content)
                if m:
                    sub = cls.subclasses.setdefault(int(m[1], 16), SubclassEntry(m[2]))
                    continue
                sub = None
            db.parse_errors += 1
        elif tabs == 2:
            if mode == "vendor" and device is not None:
                m = _BYTE.match(content)
                if m:
                    device.interfaces[int(m[1], 16)] = m[2]
                    continue
            elif mode == "class" and sub is not None:
                m = _BYTE.match(content)
                if m:
                    sub.prog_ifs[int(m[1], 16)] = m[2]
                    continue
            db.parse_errors += 1
        else:
            db.parse_errors += 1
    return db
