"""Data for the "About this computer" tab: OS, computer, board, BIOS, CPU, memory, video, drives.

Read-only WMI (CIM) queries plus DXGI for video memory; no administrator rights. Serial numbers, UUIDs
and MAC addresses are not queried at all. The result is raw and language-independent, so the tab can be
re-rendered in another language without querying again (see fakehw/ui/sysinfo_view.py).
"""

from typing import Callable

from .collectors._gpu_io import GpuProbeUnavailable, dxgi_adapters
from .collectors.powershell import PsQueryError, run_json

# Every part is queried on its own: one failing WMI class leaves its section empty instead of failing the tab.
SCRIPT = r"""
function D($v) { if ($v) { $v.ToString('s') } }
function Q([scriptblock]$b) { try { & $b } catch { } }
$os = Q { Get-CimInstance Win32_OperatingSystem }
$cs = Q { Get-CimInstance Win32_ComputerSystem }
$cv = Q { Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' }
$r = [ordered]@{
  os = [ordered]@{ Caption = $os.Caption; Version = $os.Version; BuildNumber = $os.BuildNumber; UBR = $cv.UBR
    DisplayVersion = $cv.DisplayVersion; OSArchitecture = $os.OSArchitecture; InstallDate = D $os.InstallDate
    LastBootUpTime = D $os.LastBootUpTime; TotalVisibleMemorySize = $os.TotalVisibleMemorySize
    FreePhysicalMemory = $os.FreePhysicalMemory }
  computer = [ordered]@{ Name = $cs.Name; Manufacturer = $cs.Manufacturer; Model = $cs.Model; SystemType = $cs.SystemType
    TotalPhysicalMemory = $cs.TotalPhysicalMemory }
  board = @(Q { Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product,Version })
  bios = @(Q { Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion,@{n='ReleaseDate';e={D $_.ReleaseDate}} })
  cpu = @(Q { Get-CimInstance Win32_Processor |
    Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,SocketDesignation,L2CacheSize,L3CacheSize })
  memory = @(Q { Get-CimInstance Win32_PhysicalMemory |
    Select-Object DeviceLocator,BankLabel,Manufacturer,PartNumber,Capacity,Speed,ConfiguredClockSpeed,SMBIOSMemoryType })
  video = @(Q { Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,@{n='DriverDate';e={D $_.DriverDate}},
    AdapterRAM,CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate })
  disks = @(Q { Get-CimInstance Win32_DiskDrive | Select-Object Index,Model,Size,InterfaceType,MediaType })
  volumes = @(Q { Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,VolumeName,FileSystem,Size,FreeSpace })
}
ConvertTo-Json -InputObject $r -Compress -Depth 4
"""


class WmiSystemInfoSource:
    def __init__(self, timeout: float = 90.0, dxgi: Callable[[], list[dict]] = dxgi_adapters):
        self.timeout = timeout
        self.dxgi = dxgi

    def query(self) -> dict:
        data = run_json(SCRIPT, self.timeout)
        if not isinstance(data, dict):
            raise PsQueryError("unexpected PowerShell output")
        try:
            adapters = self.dxgi()
        except (GpuProbeUnavailable, OSError):
            adapters = []  # video memory is then simply not shown
        data["dxgi"] = [{"description": a.get("description"), "dedicated_video_memory": a.get("dedicated_video_memory")}
                        for a in adapters]
        return data
