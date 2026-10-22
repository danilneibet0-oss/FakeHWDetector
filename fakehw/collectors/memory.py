"""RAM collector: SMBIOS data as exposed by Win32_PhysicalMemory (no admin rights, no SPD access)."""

import re

from ..models.device import DeviceClass, DeviceRecord
from ._placeholder import serial_shape
from ._util import Clock, failure_record, hash_serial, utcnow
from .base import Collector
from .powershell import PsQueryError, as_list, run_json

SOURCE_NAME = "wmi:Win32_PhysicalMemory"

_SCRIPT = r"""
$r = @(Get-CimInstance Win32_PhysicalMemory |
  Select-Object BankLabel,DeviceLocator,Manufacturer,PartNumber,SerialNumber,Capacity,Speed,
    ConfiguredClockSpeed,SMBIOSMemoryType,FormFactor,DataWidth,TotalWidth)
ConvertTo-Json -InputObject $r -Compress -Depth 3
"""

_HEX_CODE = re.compile(r"^[0-9A-Fa-f]{4}$")


class WmiMemorySource:
    def __init__(self, timeout: float = 90.0):
        self.timeout = timeout

    def query(self) -> list[dict]:
        return as_list(run_json(_SCRIPT, self.timeout))


class MemoryCollector(Collector):
    def __init__(self, source=None, include_serials: bool = False, clock: Clock = utcnow):
        self.source = source or WmiMemorySource()
        self.include_serials = include_serials
        self.clock = clock

    def collect(self) -> list[DeviceRecord]:
        try:
            entries = self.source.query()
        except PsQueryError as e:
            return [failure_record(DeviceClass.RAM, SOURCE_NAME, str(e), self.clock)]
        records = [self._record(e) for e in entries]
        return sorted(records, key=lambda r: (r.strings.get("locator", ""), r.strings.get("bank", ""),
                                              tuple(sorted(r.raw_ids.items()))))

    def _record(self, e: dict) -> DeviceRecord:
        raw: dict[str, str] = {}
        strings: dict[str, str] = {}

        manufacturer = (e.get("Manufacturer") or "").strip()
        if manufacturer:
            strings["manufacturer"] = manufacturer
            if _HEX_CODE.match(manufacturer):
                raw["manufacturer_code"] = manufacturer.upper()  # JEDEC bank/ID bytes as printed by the BIOS
        part = (e.get("PartNumber") or "").strip()
        if e.get("PartNumber") is not None:
            strings["part_number"] = part
        for key, name in (("DeviceLocator", "locator"), ("BankLabel", "bank")):
            if e.get(key):
                strings[name] = str(e[key]).strip()

        serial = e.get("SerialNumber")
        if serial is not None:
            raw["serial_shape"] = serial_shape(str(serial))
            s = str(serial).strip()
            if s:
                strings["serial"] = s if self.include_serials else hash_serial(s)

        for key, name in (
            ("Capacity", "capacity_bytes"), ("Speed", "speed_mhz"), ("ConfiguredClockSpeed", "configured_speed_mhz"),
            ("SMBIOSMemoryType", "smbios_memory_type"), ("FormFactor", "form_factor"),
            ("DataWidth", "data_width"), ("TotalWidth", "total_width"),
        ):
            if e.get(key) is not None:
                raw[name] = str(e[key])
        return DeviceRecord(device_class=DeviceClass.RAM, source=SOURCE_NAME, raw_ids=raw, strings=strings,
                            collected_at=self.clock())
