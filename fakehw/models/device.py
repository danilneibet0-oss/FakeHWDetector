from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DeviceClass(str, Enum):
    CPU = "cpu"
    GPU = "gpu"
    RAM = "ram"
    USB = "usb"
    STORAGE = "storage"
    PCI = "pci"


class DeviceRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    device_class: DeviceClass = Field(alias="class")
    source: str
    raw_ids: dict[str, str] = Field(default_factory=dict)
    strings: dict[str, str] = Field(default_factory=dict)
    collected_at: datetime
    privilege_needed: bool = False
    errors: list[str] = Field(default_factory=list)
