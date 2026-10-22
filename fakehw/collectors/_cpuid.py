"""Raw CPUID via ctypes: a 24-byte x64 stub in executable memory. No kernel driver, no admin rights.

The stub follows the Windows x64 calling convention: ecx=leaf, edx=subleaf, r8=uint32[4] out.
    push rbx; mov eax,ecx; mov ecx,edx; cpuid
    mov [r8],eax; mov [r8+4],ebx; mov [r8+8],ecx; mov [r8+12],edx; pop rbx; ret
"""

import ctypes
import platform
import sys

_CODE = bytes([
    0x53, 0x89, 0xC8, 0x89, 0xD1, 0x0F, 0xA2,
    0x41, 0x89, 0x00, 0x41, 0x89, 0x58, 0x04, 0x41, 0x89, 0x48, 0x08, 0x41, 0x89, 0x50, 0x0C,
    0x5B, 0xC3,
])

_MEM_COMMIT_RESERVE = 0x3000
_PAGE_READWRITE = 0x04
_PAGE_EXECUTE_READ = 0x20


class CpuidUnavailable(RuntimeError):
    pass


_fn = None


def _build():
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise CpuidUnavailable("raw CPUID is only implemented for x64 Windows")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.VirtualAlloc.restype = ctypes.c_void_p
    k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
    k32.VirtualProtect.restype = ctypes.c_int
    k32.VirtualProtect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    ptr = k32.VirtualAlloc(None, len(_CODE), _MEM_COMMIT_RESERVE, _PAGE_READWRITE)
    if not ptr:
        raise CpuidUnavailable("VirtualAlloc failed")
    ctypes.memmove(ptr, _CODE, len(_CODE))
    old = ctypes.c_uint32()
    if not k32.VirtualProtect(ptr, len(_CODE), _PAGE_EXECUTE_READ, ctypes.byref(old)):
        raise CpuidUnavailable("VirtualProtect failed")
    proto = ctypes.CFUNCTYPE(None, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32))
    return proto(ptr)


def cpuid(leaf: int, subleaf: int = 0) -> tuple[int, int, int, int]:
    """Return (eax, ebx, ecx, edx)."""
    global _fn
    if _fn is None:
        _fn = _build()
    out = (ctypes.c_uint32 * 4)()
    _fn(leaf, subleaf, out)
    return out[0], out[1], out[2], out[3]
