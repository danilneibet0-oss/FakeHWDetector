import pytest

from fakehw.kb.cpu_tables import CpuTables, CpuTablesError


def test_builtin_table_loads_with_sources():
    t = CpuTables.load()
    assert t.entries
    for e in t.entries:
        assert e.source and e.microarch and e.brand_patterns


def test_lookup_hit_and_miss():
    t = CpuTables.load()
    e = t.lookup("GenuineIntel", 6, 167)
    assert e is not None and e.microarch
    assert t.lookup("GenuineIntel", 6, 1) is None
    assert t.lookup("AuthenticAMD", 6, 167) is None  # vendor is part of the key


def test_brand_matching():
    t = CpuTables.load()
    e = t.lookup("GenuineIntel", 6, 167)
    assert e.matches("11th Gen Intel(R) Core(TM) i5-11400 @ 2.60GHz")
    assert not e.matches("Intel(R) Core(TM) i9-12900K CPU @ 3.20GHz")


def write(tmp_path, text):
    p = tmp_path / "t.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_entry_without_source_rejected(tmp_path):
    p = write(tmp_path, "entries:\n  - {vendor: GenuineIntel, family: 6, model: 1, microarch: X, brand_patterns: ['a']}\n")
    with pytest.raises(CpuTablesError):
        CpuTables.load(p)


def test_bad_regex_rejected(tmp_path):
    p = write(tmp_path, "entries:\n  - {vendor: V, family: 6, model: 1, microarch: X, brand_patterns: ['('], source: s}\n")
    with pytest.raises(CpuTablesError):
        CpuTables.load(p)


def test_duplicate_key_rejected(tmp_path):
    e = "  - {vendor: V, family: 6, model: 1, microarch: X, brand_patterns: ['a'], source: s}\n"
    with pytest.raises(CpuTablesError):
        CpuTables.load(write(tmp_path, "entries:\n" + e + e))


def test_missing_file(tmp_path):
    with pytest.raises(CpuTablesError):
        CpuTables.load(tmp_path / "nope.yaml")
