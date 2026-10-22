import pytest

from fakehw.kb.gpu_refs import GpuRefs, GpuRefsError


def test_builtin_loads_with_sources():
    refs = GpuRefs.load()
    assert refs.entries
    for e in refs.entries:
        assert e.source and e.vram_mib and e.bus_width_bits


def test_lookup():
    refs = GpuRefs.load()
    e = refs.lookup(0x10DE, 0x2486)
    assert e is not None and e.bus_width_bits == (256,) and e.pcie_max_gen == 4 and e.pcie_max_width == 16
    assert refs.lookup(0x10DE, 0xFFFF) is None


def test_vram_tolerance():
    e = GpuRefs.load().lookup(0x10DE, 0x2486)
    assert e.vram_matches(8192) and e.vram_matches(8024)      # driver-reserved memory is a few percent
    assert not e.vram_matches(4096) and not e.vram_matches(16384)


def write(tmp_path, text):
    p = tmp_path / "g.yaml"
    p.write_text(text, encoding="utf-8")
    return p


BASE = "vendor: 0x10DE\n    device: 0x2486\n    vram_mib: [8192]\n    bus_width_bits: [256]\n    pcie_max_gen: 4\n    pcie_max_width: 16\n"


def test_entry_without_source_rejected(tmp_path):
    with pytest.raises(GpuRefsError):
        GpuRefs.load(write(tmp_path, f"entries:\n  - {BASE}"))


def test_duplicate_rejected(tmp_path):
    e = f"  - {BASE}    source: s\n"
    with pytest.raises(GpuRefsError):
        GpuRefs.load(write(tmp_path, "entries:\n" + e + e))


def test_missing_file(tmp_path):
    with pytest.raises(GpuRefsError):
        GpuRefs.load(tmp_path / "nope.yaml")
