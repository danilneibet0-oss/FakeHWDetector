import copy
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fakehw.collectors import _storage_io as io
from fakehw.collectors.powershell import PsQueryError
from fakehw.collectors.storage import StorageCollector

FIX = Path(__file__).parent / "fixtures" / "collectors"
T = datetime(2024, 1, 1, tzinfo=timezone.utc)
CLOCK = lambda: T  # noqa: E731


class FakeSource:
    def __init__(self, entries):
        self.entries = entries

    def query(self):
        return self.entries


def disks():
    return json.loads((FIX / "local_storage.json").read_text(encoding="utf-8"))["entries"]


def nvme_buf(index="2") -> bytes:
    return bytes.fromhex(json.loads((FIX / "local_nvme_identify.json").read_text(encoding="utf-8"))["identify"][index])


def reader(entry):
    """Fake identify reader: real captured NVMe data; SATA needs admin (as on the non-elevated dev machine)."""
    if entry["BusType"] == "NVMe":
        return {"source": "nvme", **io.parse_nvme_identify(nvme_buf(str(entry["Index"])))}
    raise io.PrivilegeRequired("denied")


def collect(es, rd=reader, **kw):
    return StorageCollector(FakeSource(es), identify_reader=rd, clock=CLOCK, **kw).collect()


def by_bus(recs, bus):
    return next(r for r in recs if r.raw_ids.get("bus_type") == bus)


# ---- pure parsers ----

def test_parse_nvme_identify_real_capture():
    info = io.parse_nvme_identify(nvme_buf())
    assert info["model"] == "GAMER GA1J0240N" and info["firmware"] == "ECFM12.3"
    assert info["vid"] == info["ssvid"] == 0x1987
    assert info["tnvmcap"] == 240057409536
    assert info["serial"].startswith("SN")  # fixture serial was replaced


def test_parse_nvme_short_buffer():
    with pytest.raises(ValueError):
        io.parse_nvme_identify(b"\x00" * 100)


def make_ata(model="TESTMODEL 123", serial="SERIAL0001", fw="FW1.0", sectors=1000, lba48=False) -> bytes:
    """Constructed (not captured) IDENTIFY buffer: strings are stored byte-swapped per word."""
    buf = bytearray(512)

    def put(word, text, nwords):
        raw = text.ljust(nwords * 2).encode("ascii")
        for i in range(0, len(raw), 2):
            buf[2 * word + i], buf[2 * word + i + 1] = raw[i + 1], raw[i]

    put(10, serial, 10)
    put(23, fw, 4)
    put(27, model, 20)
    if lba48:
        buf[2 * 83 : 2 * 83 + 2] = (1 << 10).to_bytes(2, "little")
        buf[200:208] = sectors.to_bytes(8, "little")
    else:
        buf[120:124] = sectors.to_bytes(4, "little")
    return bytes(buf)


def test_parse_ata_identify_constructed():
    info = io.parse_ata_identify(make_ata())
    assert info["model"] == "TESTMODEL 123" and info["serial"] == "SERIAL0001" and info["firmware"] == "FW1.0"
    assert info["sectors"] == 1000


def test_parse_ata_identify_lba48():
    assert io.parse_ata_identify(make_ata(sectors=5_000_000_000, lba48=True))["sectors"] == 5_000_000_000


# ---- collector on real fixtures ----

def test_real_fixture_records():
    recs = collect(disks())
    assert len(recs) == 3 and all(r.device_class.value == "storage" for r in recs)
    nvme = by_bus(recs, "NVMe")
    assert nvme.strings["model"] == "GAMER GA1J0240N"
    assert nvme.raw_ids["identify_source"] == "nvme"
    assert nvme.raw_ids["nvme_vid"] == "1987" and nvme.raw_ids["nvme_ssvid"] == "1987"
    assert nvme.raw_ids["nvme_tnvmcap_bytes"] == "240057409536"
    assert nvme.raw_ids["identify_model_matches"] == "true"
    assert nvme.raw_ids["size_exceeds_nvme_capacity"] == "false"
    assert nvme.errors == [] and nvme.privilege_needed is False


def test_sata_without_admin_is_flagged_not_failed():
    sata = by_bus(collect(disks()), "SATA")
    assert sata.privilege_needed is True
    assert sata.raw_ids["identify_source"] == "none"
    assert any("administrator" in e for e in sata.errors)
    assert "identify_model_matches" not in sata.raw_ids  # unknown, not guessed


def test_nvme_windows_serial_differs_from_identify_serial_but_no_flag():
    # Real finding: Windows reports the namespace EUI-64 as the serial of an NVMe disk, not the controller SN.
    nvme = by_bus(collect(disks()), "NVMe")
    assert "serial_matches_identify" not in nvme.raw_ids


def test_serial_hashed_and_shape_recorded():
    recs = collect(disks())
    for r in recs:
        assert r.strings["serial"].startswith("sha256:")
        assert r.raw_ids["serial_shape"] == "normal"
    plain = collect(disks(), include_serials=True)
    assert not plain[0].strings["serial"].startswith("sha256:")


def test_edited_model_mismatch_detected():
    es = copy.deepcopy(disks())
    nv = next(e for e in es if e["BusType"] == "NVMe")
    nv["Model"] = "SOME OTHER SSD 2TB"
    assert by_bus(collect(es), "NVMe").raw_ids["identify_model_matches"] == "false"


def test_edited_size_above_nvme_capacity_detected():
    es = copy.deepcopy(disks())
    nv = next(e for e in es if e["BusType"] == "NVMe")
    nv["Size"] = 2_000_000_000_000
    assert by_bus(collect(es), "NVMe").raw_ids["size_exceeds_nvme_capacity"] == "true"


def test_truncated_model_still_matches():
    es = copy.deepcopy(disks())
    nv = next(e for e in es if e["BusType"] == "NVMe")
    nv["Model"] = "GAMER GA1J0240"  # driver truncation is normal
    assert by_bus(collect(es), "NVMe").raw_ids["identify_model_matches"] == "true"


def test_edited_serial_placeholder_detected():
    es = copy.deepcopy(disks())
    es[0]["SerialNumber"] = "0000000000"
    assert any(r.raw_ids["serial_shape"] == "zeros" for r in collect(es))


def test_identify_io_error_is_recorded():
    def bad(entry):
        raise io.StorageIoError("boom")

    r = by_bus(collect(disks(), rd=bad), "NVMe")
    assert r.privilege_needed is False and any("boom" in e for e in r.errors)


def test_non_sata_non_nvme_bus_is_not_probed():
    es = copy.deepcopy(disks())
    es[0]["BusType"] = "USB"
    calls = []

    def spy(entry):
        calls.append(entry["BusType"])
        raise io.PrivilegeRequired("x")

    collect(es, rd=spy)
    assert "USB" not in calls


def test_order_independent_of_input_order():
    es = disks()
    sh = es[:]
    random.Random(4).shuffle(sh)
    assert [x.model_dump_json() for x in collect(es)] == [x.model_dump_json() for x in collect(sh)]


def test_source_failure_reported():
    class Broken:
        def query(self):
            raise PsQueryError("no storage module")

    recs = StorageCollector(Broken(), clock=CLOCK).collect()
    assert len(recs) == 1 and "no storage module" in recs[0].errors[0]
