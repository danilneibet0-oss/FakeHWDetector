"""GPU probes via ctypes: DXGI (any vendor: IDs, name, dedicated VRAM) and NVML (NVIDIA: bus width, PCIe link).

Neither needs administrator rights. Both return plain dicts and raise GpuProbeUnavailable when the
library is missing, so callers can report "could not verify" instead of failing.
"""

import ctypes
import os
import sys
from ctypes import wintypes


class GpuProbeUnavailable(RuntimeError):
    pass


# ---------------- DXGI ----------------

class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


def _guid(text: str) -> _GUID:
    import uuid

    u = uuid.UUID(text)
    g = _GUID()
    g.a, g.b, g.c = u.time_low, u.time_mid, u.time_hi_version
    for i, byte in enumerate(u.bytes[8:]):
        g.d[i] = byte
    return g


class _AdapterDesc1(ctypes.Structure):
    _fields_ = [
        ("Description", ctypes.c_wchar * 128), ("VendorId", ctypes.c_uint32), ("DeviceId", ctypes.c_uint32),
        ("SubSysId", ctypes.c_uint32), ("Revision", ctypes.c_uint32),
        ("DedicatedVideoMemory", ctypes.c_size_t), ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t), ("AdapterLuid", ctypes.c_int64), ("Flags", ctypes.c_uint32),
    ]


_IID_FACTORY1 = "770aae78-f26f-4dba-a829-253c83d1b387"
_DXGI_ERROR_NOT_FOUND = 0x887A0002


def _vcall(obj, index: int, restype, *argtypes):
    """Call COM method #index of the interface pointer `obj` (a c_void_p)."""
    vtbl = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])


def dxgi_adapters() -> list[dict]:
    """Enumerate DXGI adapters (IDXGIFactory1::EnumAdapters1 -> IDXGIAdapter1::GetDesc1)."""
    if sys.platform != "win32":
        raise GpuProbeUnavailable("DXGI is Windows only")
    try:
        dxgi = ctypes.WinDLL("dxgi")
    except OSError as e:
        raise GpuProbeUnavailable(f"dxgi.dll not available: {e}") from e
    dxgi.CreateDXGIFactory1.restype = ctypes.c_int32
    dxgi.CreateDXGIFactory1.argtypes = [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    factory = ctypes.c_void_p()
    iid = _guid(_IID_FACTORY1)
    hr = dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory))
    if hr != 0:
        raise GpuProbeUnavailable(f"CreateDXGIFactory1 failed: {hr & 0xFFFFFFFF:#x}")
    out: list[dict] = []
    try:
        enum = _vcall(factory, 12, ctypes.c_int32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p))
        i = 0
        while True:
            adapter = ctypes.c_void_p()
            hr = enum(factory, i, ctypes.byref(adapter))
            if hr & 0xFFFFFFFF == _DXGI_ERROR_NOT_FOUND:
                break
            if hr != 0:
                raise GpuProbeUnavailable(f"EnumAdapters1 failed: {hr & 0xFFFFFFFF:#x}")
            try:
                desc = _AdapterDesc1()
                if _vcall(adapter, 10, ctypes.c_int32, ctypes.POINTER(_AdapterDesc1))(adapter, ctypes.byref(desc)) == 0:
                    out.append({
                        "description": desc.Description, "vendor_id": desc.VendorId, "device_id": desc.DeviceId,
                        "subsys_id": desc.SubSysId, "revision": desc.Revision,
                        "dedicated_video_memory": desc.DedicatedVideoMemory, "flags": desc.Flags,
                    })
            finally:
                _vcall(adapter, 2, ctypes.c_uint32)(adapter)  # Release
            i += 1
    finally:
        _vcall(factory, 2, ctypes.c_uint32)(factory)
    return out


# ---------------- NVML ----------------

class _Memory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_uint64), ("free", ctypes.c_uint64), ("used", ctypes.c_uint64)]


def _load_nvml():
    candidates = [
        "nvml.dll",
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvml.dll"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "NVIDIA Corporation", "NVSMI", "nvml.dll"),
    ]
    for path in candidates:
        try:
            return ctypes.CDLL(path)
        except OSError:
            continue
    raise GpuProbeUnavailable("nvml.dll not found (no NVIDIA driver)")


def nvml_devices() -> list[dict]:
    """Query every NVIDIA GPU through NVML. Individual unsupported queries are simply omitted."""
    if sys.platform != "win32":
        raise GpuProbeUnavailable("NVML probe is Windows only here")
    lib = _load_nvml()
    if lib.nvmlInit_v2() != 0:
        raise GpuProbeUnavailable("nvmlInit failed")
    out: list[dict] = []
    try:
        count = ctypes.c_uint()
        if lib.nvmlDeviceGetCount_v2(ctypes.byref(count)) != 0:
            raise GpuProbeUnavailable("nvmlDeviceGetCount failed")
        for i in range(count.value):
            handle = ctypes.c_void_p()
            if lib.nvmlDeviceGetHandleByIndex_v2(i, ctypes.byref(handle)) != 0:
                continue
            info: dict = {}

            def uint(fn: str, key: str) -> None:
                v = ctypes.c_uint()
                if getattr(lib, fn)(handle, ctypes.byref(v)) == 0:
                    info[key] = v.value

            name = ctypes.create_string_buffer(96)
            if lib.nvmlDeviceGetName(handle, name, 96) == 0:
                info["name"] = name.value.decode("ascii", "replace")
            mem = _Memory()
            if lib.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem)) == 0:
                info["memory_total"] = mem.total
            uint("nvmlDeviceGetMemoryBusWidth", "memory_bus_width")
            uint("nvmlDeviceGetCurrPcieLinkGeneration", "pcie_gen_current")
            uint("nvmlDeviceGetMaxPcieLinkGeneration", "pcie_gen_max")
            uint("nvmlDeviceGetCurrPcieLinkWidth", "pcie_width_current")
            uint("nvmlDeviceGetMaxPcieLinkWidth", "pcie_width_max")
            pci = ctypes.create_string_buffer(256)  # nvmlPciInfo_t: 16 + 5*4 + 32 bytes; padded for safety
            if lib.nvmlDeviceGetPciInfo_v3(handle, pci) == 0:
                # busIdLegacy[16], domain, bus, device, pciDeviceId (device<<16 | vendor), pciSubSystemId, busId[32]
                info["pci_device_id"] = int.from_bytes(pci.raw[28:32], "little")
                info["pci_subsystem_id"] = int.from_bytes(pci.raw[32:36], "little")
            out.append(info)
    finally:
        lib.nvmlShutdown()
    return out
