import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fakehw.collectors import cpu as cpu_mod
from fakehw.collectors.cpu import (
    CpuCollector,
    CpuidUnavailable,
    decode_leaves,
    parse_registry_identifier,
)

FIX = Path(__file__).parent / "fixtures" / "collectors"
T = datetime(2024, 1, 1, tzinfo=timezone.utc)
CLOCK = lambda: T  # noqa: E731


def load_leaves(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))["leaves"]


def make_eax(ext_family=0, ext_model=0, family=0, model=0, stepping=0) -> int:
    return (ext_family << 20) | (ext_model << 16) | (family << 8) | (model << 4) | stepping


def leaves_with_eax(eax: int, vendor="GenuineIntel", ecx=0) -> dict:
    v = vendor.encode()
    ebx, edx, vecx = (int.from_bytes(v[i : i + 4], "little") for i in (0, 4, 8))
    return {
        "0x00000000:0": [0x16, ebx, vecx, edx],
        "0x00000001:0": [eax, 0, ecx, 0],
        "0x80000000:0": [0x80000008, 0, 0, 0],
    }


# ---- raw CPUID executor (real machine) ----

@pytest.mark.skipif(
    not (sys.platform == "win32" and platform.machine().lower() in ("amd64", "x86_64")),
    reason="needs x64 Windows",
)
def test_raw_cpuid_matches_windows_registry():
    import winreg

    from fakehw.collectors._cpuid import cpuid

    eax, ebx, ecx, edx = cpuid(0)
    vendor = b"".join(r.to_bytes(4, "little") for r in (ebx, edx, ecx)).decode("ascii")
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
        assert winreg.QueryValueEx(k, "VendorIdentifier")[0] == vendor
    assert eax >= 1
    assert cpuid(1) == cpuid(1)


# ---- decoding of real captured leaves ----

def test_decode_real_local_leaves():
    info = decode_leaves(load_leaves("local_cpuid.json"))
    assert info.vendor == "GenuineIntel"
    assert (info.family, info.model, info.stepping) == (6, 167, 1)
    assert info.brand == "11th Gen Intel(R) Core(TM) i5-11400 @ 2.60GHz"
    assert info.hypervisor_present is True
    assert info.hypervisor_vendor == "Microsoft Hv"


def test_decode_bare_metal_edited_fixture():
    # hand-edited copy of local_cpuid.json: hypervisor bit cleared, leaf 0x40000000 removed
    info = decode_leaves(load_leaves("edited_bare_metal_cpuid.json"))
    assert info.hypervisor_present is False
    assert info.hypervisor_vendor is None
    assert (info.family, info.model) == (6, 167)


def test_decode_edited_brand_string():
    info = decode_leaves(load_leaves("edited_brand_cpuid.json"))
    assert info.brand != "11th Gen Intel(R) Core(TM) i5-11400 @ 2.60GHz"
    assert info.brand  # non-empty, cleaned of NUL padding
    assert (info.family, info.model, info.stepping) == (6, 167, 1)  # signature untouched


@pytest.mark.parametrize(
    "fields, expected",
    [
        (dict(family=6, model=0x7, ext_model=0xA, stepping=1), (6, 0xA7, 1)),      # family 6 uses extended model
        (dict(family=0xF, model=1, ext_model=2, ext_family=0xA), (0x19, 0x21, 0)),  # family 0xF adds ext family
        (dict(family=5, model=3, ext_model=9, ext_family=7), (5, 3, 0)),           # other families ignore extensions
    ],
)
def test_signature_arithmetic(fields, expected):
    info = decode_leaves(leaves_with_eax(make_eax(**fields)))
    assert (info.family, info.model, info.stepping) == expected


def test_hypervisor_bit_only_from_leaf1_ecx_bit31():
    assert decode_leaves(leaves_with_eax(make_eax(family=6), ecx=1 << 31)).hypervisor_present is True
    assert decode_leaves(leaves_with_eax(make_eax(family=6), ecx=(1 << 31) - 1)).hypervisor_present is False


def test_missing_brand_leaves_gives_none_not_guess():
    info = decode_leaves(leaves_with_eax(make_eax(family=6)))
    assert info.brand is None


def test_decode_missing_leaf1_raises():
    with pytest.raises(ValueError):
        decode_leaves({"0x00000000:0": [1, 0, 0, 0]})


# ---- registry fallback ----

def test_parse_registry_identifier():
    assert parse_registry_identifier("Intel64 Family 6 Model 167 Stepping 1") == (6, 167, 1)
    assert parse_registry_identifier("something else") is None


# ---- collector ----

def test_collector_record_from_fixture():
    leaves = load_leaves("local_cpuid.json")
    rec = CpuCollector(leaves_source=lambda: leaves, clock=CLOCK).collect()
    assert len(rec) == 1
    r = rec[0]
    assert r.device_class.value == "cpu"
    assert r.source == "cpuid"
    assert r.raw_ids["family"] == "6" and r.raw_ids["model"] == "167" and r.raw_ids["stepping"] == "1"
    assert r.raw_ids["hypervisor_present"] == "true"
    assert r.strings["brand"].startswith("11th Gen Intel")
    assert r.strings["vendor"] == "GenuineIntel"
    assert r.strings["hypervisor_vendor"] == "Microsoft Hv"
    assert r.collected_at == T
    assert r.errors == [] and r.privilege_needed is False


def test_collector_is_reproducible():
    leaves = load_leaves("local_cpuid.json")
    a = CpuCollector(leaves_source=lambda: leaves, clock=CLOCK).collect()
    b = CpuCollector(leaves_source=lambda: leaves, clock=CLOCK).collect()
    assert [x.model_dump_json() for x in a] == [x.model_dump_json() for x in b]


def test_collector_falls_back_to_registry():
    def no_cpuid():
        raise CpuidUnavailable("not x64")

    def registry():
        return {"vendor": "GenuineIntel", "brand": "B", "identifier": "Intel64 Family 6 Model 167 Stepping 1"}

    r = CpuCollector(leaves_source=no_cpuid, registry_source=registry, clock=CLOCK).collect()[0]
    assert r.source == "registry"
    assert r.raw_ids["family"] == "6" and r.raw_ids["model"] == "167"
    assert r.raw_ids["hypervisor_present"] == "unknown"
    assert r.strings["brand"] == "B"


def test_collector_total_failure_is_reported_not_raised():
    def boom():
        raise CpuidUnavailable("nope")

    def boom2():
        raise OSError("no registry")

    r = CpuCollector(leaves_source=boom, registry_source=boom2, clock=CLOCK).collect()
    assert len(r) == 1 and r[0].errors and r[0].raw_ids == {}


def test_module_exposes_no_hardcoded_cpu_tables():
    # iteration-3 guard: no invented signature tables in the collector
    src = Path(cpu_mod.__file__).read_text(encoding="utf-8")
    assert "i5-11400" not in src
