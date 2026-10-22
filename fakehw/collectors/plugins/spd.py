"""Optional SPD plugin (disabled by default).

Reading SPD EEPROMs needs SMBus access, which on Windows means a kernel driver (WinRing0 and similar).
This project does not ship or use such drivers, so no reader is bundled: the plugin accepts an injected
`reader` returning raw SPD images. Without one it reports itself as unavailable.
"""

from typing import Callable

from ...models.device import DeviceClass, DeviceRecord
from .._util import Clock, failure_record, hash_serial, utcnow
from ..base import Collector

SOURCE_NAME = "spd"


class SpdUnavailable(RuntimeError):
    pass


def parse_ddr4_spd(image: bytes) -> dict:
    """Module manufacturer ID, serial and part number from a DDR4 SPD image (JEDEC DDR4 SPD annex)."""
    if len(image) < 349:
        raise ValueError("SPD image too short for DDR4 module-specific data")
    if image[2] != 0x0C:
        raise ValueError("not a DDR4 SPD image (DRAM device type byte != 0x0C)")
    return {
        "manufacturer_code": f"{image[320]:02X}{image[321]:02X}",
        "serial": image[325:329].hex().upper(),
        "part_number": image[329:349].decode("ascii", "replace").strip("\x00 ").strip(),
    }


class SpdCollector(Collector):
    enabled_by_default = False

    def __init__(
        self,
        reader: Callable[[], list[bytes]] | None = None,
        enabled: bool = False,
        include_serials: bool = False,
        clock: Clock = utcnow,
    ):
        self.reader = reader
        self.enabled = enabled
        self.include_serials = include_serials
        self.clock = clock

    def collect(self) -> list[DeviceRecord]:
        if not self.enabled or self.reader is None:
            rec = failure_record(
                DeviceClass.RAM, SOURCE_NAME,
                "SPD reading is unavailable: it needs a kernel driver or administrator-level SMBus access, "
                "which this tool does not use",
                self.clock,
            )
            return [rec.model_copy(update={"privilege_needed": True})]
        try:
            images = self.reader()
            parsed = [parse_ddr4_spd(img) for img in images]
        except (SpdUnavailable, ValueError, OSError) as e:
            return [failure_record(DeviceClass.RAM, SOURCE_NAME, str(e), self.clock)]
        records = []
        for p in parsed:
            serial = p["serial"]
            records.append(DeviceRecord(
                device_class=DeviceClass.RAM, source=SOURCE_NAME,
                raw_ids={"manufacturer_code": p["manufacturer_code"]},
                strings={"part_number": p["part_number"],
                         "serial": serial if self.include_serials else hash_serial(serial)},
                collected_at=self.clock(),
            ))
        return records
