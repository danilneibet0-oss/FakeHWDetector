from abc import ABC, abstractmethod

from ..models.device import DeviceRecord


class Collector(ABC):
    """A collector must not raise on missing privileges or data: it reports them in DeviceRecord."""

    @abstractmethod
    def collect(self) -> list[DeviceRecord]: ...
