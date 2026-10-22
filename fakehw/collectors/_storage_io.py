"""Low-level storage queries via DeviceIoControl (ctypes). No kernel driver; may need admin rights.

NVMe Identify Controller uses IOCTL_STORAGE_QUERY_PROPERTY (documented, usually works unprivileged).
ATA IDENTIFY DEVICE uses IOCTL_ATA_PASS_THROUGH, which needs administrator rights.
"""

import ctypes
import struct
import sys
from ctypes import wintypes


class PrivilegeRequired(PermissionError):
    pass


class StorageIoError(OSError):
    pass


# ---- pure parsers (tested on captured / constructed buffers) ----

def _ascii(b: bytes) -> str:
    return b.split(b"\x00", 1)[0].decode("ascii", "replace").strip()


def parse_nvme_identify(buf: bytes) -> dict:
    """NVMe Identify Controller data structure (4096 bytes); offsets per the NVMe base specification."""
    if len(buf) < 312:
        raise ValueError("NVMe identify buffer too short")
    return {
        "vid": struct.unpack_from("<H", buf, 0)[0],
        "ssvid": struct.unpack_from("<H", buf, 2)[0],
        "serial": _ascii(buf[4:24]),
        "model": _ascii(buf[24:64]),
        "firmware": _ascii(buf[64:72]),
        "ieee_oui": buf[73:76][::-1].hex().upper(),
        "tnvmcap": int.from_bytes(buf[280:296], "little"),
    }


def _ata_string(words: bytes) -> str:
    swapped = b"".join(words[i + 1 : i + 2] + words[i : i + 1] for i in range(0, len(words), 2))
    return swapped.decode("ascii", "replace").strip()


def parse_ata_identify(buf: bytes) -> dict:
    """ATA IDENTIFY DEVICE data (512 bytes, 256 little-endian words)."""
    if len(buf) < 512:
        raise ValueError("ATA identify buffer too short")
    word = lambda n: struct.unpack_from("<H", buf, 2 * n)[0]  # noqa: E731
    lba48 = bool(word(83) & (1 << 10))
    sectors = (
        word(100) | word(101) << 16 | word(102) << 32 | word(103) << 48 if lba48 else word(60) | word(61) << 16
    )
    return {
        "serial": _ata_string(buf[20:40]),        # words 10-19
        "firmware": _ata_string(buf[46:54]),      # words 23-26
        "model": _ata_string(buf[54:94]),         # words 27-46
        "sectors": sectors,                       # logical sectors of 512 bytes (word 106 not decoded)
    }


# ---- Windows I/O ----

_GENERIC_READ, _GENERIC_WRITE = 0x80000000, 0x40000000
_SHARE_RW = 3
_OPEN_EXISTING = 3
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_ERROR_ACCESS_DENIED = 5

_IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
_IOCTL_ATA_PASS_THROUGH = 0x0004D02C


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                              wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    k.DeviceIoControl.restype = wintypes.BOOL
    k.DeviceIoControl.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    return k


def _open(k, index: int, access: int):
    h = k.CreateFileW(rf"\\.\PhysicalDrive{index}", access, _SHARE_RW, None, _OPEN_EXISTING, 0, None)
    if h is None or h == _INVALID_HANDLE:
        err = ctypes.get_last_error()
        if err == _ERROR_ACCESS_DENIED:
            raise PrivilegeRequired(f"access denied opening PhysicalDrive{index}")
        raise StorageIoError(f"CreateFile PhysicalDrive{index} failed: {err}")
    return h


def _ioctl(k, h, code: int, inbuf, outbuf) -> int:
    returned = wintypes.DWORD(0)
    ok = k.DeviceIoControl(h, code, inbuf, ctypes.sizeof(inbuf), outbuf, ctypes.sizeof(outbuf),
                           ctypes.byref(returned), None)
    if not ok:
        err = ctypes.get_last_error()
        if err == _ERROR_ACCESS_DENIED:
            raise PrivilegeRequired(f"IOCTL {code:#x} denied")
        raise StorageIoError(f"IOCTL {code:#x} failed: {err}")
    return returned.value


def read_nvme_identify(index: int) -> bytes:
    """Identify Controller via StorageAdapterProtocolSpecificProperty (NVMe); returns 4096 bytes."""
    if sys.platform != "win32":
        raise StorageIoError("Windows only")
    k = _kernel32()
    psd_size, data_len = 40, 4096  # STORAGE_PROTOCOL_SPECIFIC_DATA (extended layout) + identify data
    total = 8 + psd_size + data_len
    buf = (ctypes.c_ubyte * total)()
    struct.pack_into("<II", buf, 0, 49, 0)  # PropertyId=StorageAdapterProtocolSpecificProperty, PropertyStandardQuery
    # ProtocolType=Nvme(3), DataType=NVMeDataTypeIdentify(1), RequestValue=CNS 1 (controller), SubValue=0,
    # DataOffset=psd_size, DataLength=4096
    struct.pack_into("<IIIIII", buf, 8, 3, 1, 1, 0, psd_size, data_len)
    h = _open(k, index, 0)
    try:
        _ioctl(k, h, _IOCTL_STORAGE_QUERY_PROPERTY, buf, buf)
    finally:
        k.CloseHandle(h)
    offset = struct.unpack_from("<I", buf, 8 + 16)[0]  # ProtocolDataOffset in the returned descriptor
    start = 8 + offset
    return bytes(buf[start : start + data_len])


def read_ata_identify(index: int) -> bytes:
    """ATA IDENTIFY DEVICE via IOCTL_ATA_PASS_THROUGH; needs administrator rights. Returns 512 bytes."""
    if sys.platform != "win32":
        raise StorageIoError("Windows only")
    k = _kernel32()
    hdr = 48  # sizeof(ATA_PASS_THROUGH_EX) on x64
    total = hdr + 512
    buf = (ctypes.c_ubyte * total)()
    # Length, AtaFlags(DATA_IN=2), PathId, TargetId, Lun, Reserved, DataTransferLength, TimeOut, Reserved, DataBufferOffset
    struct.pack_into("<HHBBBBIIIQ", buf, 0, hdr, 0x02, 0, 0, 0, 0, 512, 10, 0, hdr)
    buf[hdr - 8 + 6] = 0xEC  # CurrentTaskFile[6] = command: IDENTIFY DEVICE
    h = _open(k, index, _GENERIC_READ | _GENERIC_WRITE)
    try:
        _ioctl(k, h, _IOCTL_ATA_PASS_THROUGH, buf, buf)
    finally:
        k.CloseHandle(h)
    return bytes(buf[hdr : hdr + 512])
