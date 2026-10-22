import copy
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from fakehw.collectors._placeholder import is_placeholder_text, serial_shape
from fakehw.collectors.memory import MemoryCollector
from fakehw.collectors.powershell import PsQueryError

FIX = Path(__file__).parent / "fixtures" / "collectors"
T = datetime(2024, 1, 1, tzinfo=timezone.utc)
CLOCK = lambda: T  # noqa: E731


class FakeSource:
    def __init__(self, entries):
        self.entries = entries

    def query(self):
        return self.entries


def entries():
    return json.loads((FIX / "local_memory.json").read_text(encoding="utf-8"))["entries"]


def collect(es, **kw):
    return MemoryCollector(FakeSource(es), clock=CLOCK, **kw).collect()


def test_real_fixture_fields():
    recs = collect(entries())
    assert len(recs) == 2 and all(r.device_class.value == "ram" for r in recs)
    r = recs[0]
    assert r.source == "wmi:Win32_PhysicalMemory"
    assert r.strings["manufacturer"] == "Kingston"
    assert r.strings["part_number"] == "KHX2666C16/8G"  # trailing padding stripped
    assert r.strings["locator"].startswith("Controller0-ChannelA")
    assert r.raw_ids["capacity_bytes"] == "8589934592"
    assert r.raw_ids["speed_mhz"] == "2667" and r.raw_ids["smbios_memory_type"] == "26"
    assert r.errors == [] and r.privilege_needed is False


def test_manufacturer_name_is_not_treated_as_jedec_code():
    r = collect(entries())[0]
    assert "manufacturer_code" not in r.raw_ids


def test_hex_manufacturer_becomes_code():
    es = copy.deepcopy(entries())
    es[0]["Manufacturer"] = "802c"
    r = collect(es)[0]
    assert r.raw_ids["manufacturer_code"] == "802C"


def test_serial_hashed_by_default_and_plain_with_flag():
    es = entries()
    real = es[0]["SerialNumber"]
    r = collect(es)[0]
    assert r.strings["serial"].startswith("sha256:") and real not in r.model_dump_json()
    assert collect(es, include_serials=True)[0].strings["serial"] == real


def test_serial_shape_is_recorded_without_exposing_serial():
    r = collect(entries())[0]
    assert r.raw_ids["serial_shape"] == "normal"  # real serial contains zeros but is not all zeros
    es = copy.deepcopy(entries())
    es[0]["SerialNumber"] = "00000000"
    assert collect(es)[0].raw_ids["serial_shape"] == "zeros"


def test_missing_fields_are_omitted_not_invented():
    r = collect([{"DeviceLocator": "DIMM0"}])[0]
    assert r.raw_ids == {} and "part_number" not in r.strings


def test_order_independent_of_input_order():
    es = entries()
    sh = es[:]
    random.Random(3).shuffle(sh)
    assert [x.model_dump_json() for x in collect(es)] == [x.model_dump_json() for x in collect(sh)]


def test_source_failure_reported():
    class Broken:
        def query(self):
            raise PsQueryError("no wmi")

    recs = MemoryCollector(Broken(), clock=CLOCK).collect()
    assert len(recs) == 1 and "no wmi" in recs[0].errors[0]


def test_placeholder_table():
    # norm / suspicious table from docs/RULES.md
    for s in ["", "  ", "Unknown", "To Be Filled By O.E.M.", "N/A", "Not Specified", "[Empty]"]:
        assert is_placeholder_text(s), s
    for s in ["KHX2666C16/8G", "M378A1K43CB2-CTD", "0"]:
        assert not is_placeholder_text(s) or s == "0", s
    shapes = {"": "empty", "0000": "zeros", "FFFFFFFF": "ones", "AAAAAA": "repeated",
              "Unknown": "placeholder_text", "0CD214F8": "normal", "ab12": "normal"}
    for value, shape in shapes.items():
        assert serial_shape(value) == shape, value
