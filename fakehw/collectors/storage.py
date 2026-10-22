"""Storage collector: Win32_DiskDrive + Get-PhysicalDisk, plus the drive's own Identify data when readable.

NVMe Identify works without administrator rights. SATA IDENTIFY and SMART need them: such drives are
reported with privilege_needed=True instead of failing.
"""

import ctypes
import sys
from typing import Callable

from ..models.device import DeviceClass, DeviceRecord
from . import _storage_io as io
from ._placeholder import names_match, serial_shape
from ._util import Clock, failure_record, hash_serial, utcnow
from .base import Collector
from .powershell import PsQueryError, as_list, run_json

SOURCE_NAME = "wmi:Win32_DiskDrive"

_SCRIPT = r"""
$pd = @{}
try { Get-PhysicalDisk | ForEach-Object { $pd[[string]$_.DeviceId] = $_ } } catch {}
$r = @(Get-CimInstance Win32_DiskDrive | ForEach-Object {
  $p = $pd[[string]$_.Index]
  [pscustomobject]@{
    Index = $_.Index; Model = $_.Model; SerialNumber = $_.SerialNumber; FirmwareRevision = $_.FirmwareRevision
    Size = $_.Size; InterfaceType = $_.InterfaceType; MediaType = $_.MediaType; PNPDeviceID = $_.PNPDeviceID
    BusType = [string]$p.BusType; PhysicalMediaType = [string]$p.MediaType; HealthStatus = [string]$p.HealthStatus
  } })
ConvertTo-Json -InputObject $r -Compress -Depth 3
"""

IdentifyReader = Callable[[dict], dict | None]
PROBED_BUSES = ("NVMe", "SATA", "ATA")  # USB bridges, RAID and virtual disks are not probed


class WmiStorageSource:
    def __init__(self, timeout: float = 90.0):
        self.timeout = timeout

    def query(self) -> list[dict]:
        return as_list(run_json(_SCRIPT, self.timeout))


def default_identify_reader(entry: dict) -> dict | None:
    """Read Identify data for NVMe and SATA drives; other buses (USB bridges, RAID) are not probed."""
    index, bus = int(entry["Index"]), entry.get("BusType") or ""
    if bus == "NVMe":
        return {"source": "nvme", **io.parse_nvme_identify(io.read_nvme_identify(index))}
    if bus in ("SATA", "ATA"):
        return {"source": "ata", **io.parse_ata_identify(io.read_ata_identify(index))}
    return None


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin()) if sys.platform == "win32" else False
    except OSError:
        return False


class StorageCollector(Collector):
    def __init__(
        self,
        source=None,
        identify_reader: IdentifyReader = default_identify_reader,
        include_serials: bool = False,
        clock: Clock = utcnow,
    ):
        self.source = source or WmiStorageSource()
        self.identify_reader = identify_reader
        self.include_serials = include_serials
        self.clock = clock

    def collect(self) -> list[DeviceRecord]:
        try:
            entries = self.source.query()
        except PsQueryError as e:
            return [failure_record(DeviceClass.STORAGE, SOURCE_NAME, str(e), self.clock)]
        records = [self._record(e) for e in entries]
        return sorted(records, key=lambda r: int(r.raw_ids.get("disk_index", "0")))

    def _record(self, e: dict) -> DeviceRecord:
        raw: dict[str, str] = {}
        strings: dict[str, str] = {}
        errors: list[str] = []
        privilege = False

        if e.get("Index") is not None:
            raw["disk_index"] = str(e["Index"])
        for key, name in (("BusType", "bus_type"), ("InterfaceType", "interface_type")):
            if e.get(key):
                raw[name] = str(e[key])
        if e.get("Size") is not None:
            raw["size_bytes"] = str(e["Size"])
        for key, name in (("Model", "model"), ("FirmwareRevision", "firmware"), ("MediaType", "media_type"),
                          ("PhysicalMediaType", "physical_media_type"), ("HealthStatus", "health_status")):
            if e.get(key):
                strings[name] = str(e[key]).strip()
        serial = e.get("SerialNumber")
        if serial is not None:
            raw["serial_shape"] = serial_shape(str(serial))
            if str(serial).strip():
                s = str(serial).strip()
                strings["serial"] = s if self.include_serials else hash_serial(s)

        raw["identify_source"] = "none"
        try:
            info = self.identify_reader(e) if e.get("BusType") in PROBED_BUSES else None
        except io.PrivilegeRequired:
            privilege = True
            errors.append("requires administrator rights: drive Identify data and SMART were not read")
            info = None
        except (io.StorageIoError, ValueError, OSError) as ex:
            errors.append(f"identify failed: {ex}")
            info = None
        if info:
            raw["identify_source"] = info["source"]
            strings["identify_model"] = info["model"]
            if info.get("firmware"):
                strings["identify_firmware"] = info["firmware"]
            if info.get("model") and strings.get("model"):
                raw["identify_model_matches"] = "true" if names_match(strings["model"], info["model"]) else "false"
            if info["source"] == "nvme":
                raw["nvme_vid"], raw["nvme_ssvid"] = f"{info['vid']:04X}", f"{info['ssvid']:04X}"
                raw["nvme_tnvmcap_bytes"] = str(info["tnvmcap"])
                if info["tnvmcap"] and e.get("Size") is not None:
                    raw["size_exceeds_nvme_capacity"] = "true" if int(e["Size"]) > info["tnvmcap"] else "false"
        # Note: Windows reports the namespace EUI-64 as an NVMe disk's serial, not the controller SN,
        # so serials are deliberately not compared with Identify data.
        return DeviceRecord(
            device_class=DeviceClass.STORAGE, source=SOURCE_NAME, raw_ids=raw, strings=strings,
            collected_at=self.clock(), privilege_needed=privilege, errors=errors,
        )
