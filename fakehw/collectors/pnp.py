"""Win32_PnPEntity access via PowerShell Get-CimInstance (no extra Python dependencies, no admin rights)."""

from typing import Protocol

from .powershell import PsQueryError, as_list, run_json

SOURCE_NAME = "wmi:Win32_PnPEntity"

_SCRIPT = r"""
$r = @(Get-CimInstance Win32_PnPEntity |
  Where-Object { $_.DeviceID -match '^(PCI|USB)\\' } |
  Select-Object DeviceID,Name,Manufacturer,PNPClass,HardwareID,CompatibleID,Present)
ConvertTo-Json -InputObject $r -Compress -Depth 3
"""


PnpQueryError = PsQueryError


class PnpSource(Protocol):
    def query(self) -> list[dict]: ...


def normalise_entry(e: dict) -> dict:
    out = dict(e)
    for key in ("HardwareID", "CompatibleID"):
        v = out.get(key)
        out[key] = [] if v is None else ([v] if isinstance(v, str) else list(v))
    return out


class WmiPnpSource:
    """Queries once and caches, so the PCI and USB collectors share a single PowerShell call."""

    def __init__(self, timeout: float = 90.0):
        self.timeout = timeout
        self._cache: list[dict] | None = None

    def query(self) -> list[dict]:
        if self._cache is None:
            self._cache = self._run()
        return self._cache

    def _run(self) -> list[dict]:
        return [normalise_entry(e) for e in as_list(run_json(_SCRIPT, self.timeout))]
