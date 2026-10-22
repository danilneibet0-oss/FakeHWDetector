import hashlib
from datetime import datetime, timezone
from typing import Callable

from ..models.device import DeviceClass, DeviceRecord

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def hash_serial(serial: str) -> str:
    return "sha256:" + hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16]


def failure_record(device_class: DeviceClass, source: str, message: str, clock: Clock) -> DeviceRecord:
    """A collector that cannot run reports it as a record instead of raising or staying silent."""
    return DeviceRecord(device_class=device_class, source=source, collected_at=clock(), errors=[message])
