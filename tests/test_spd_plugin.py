from datetime import datetime, timezone

import pytest

from fakehw import cli
from fakehw.collectors.plugins.spd import SpdCollector, SpdUnavailable, parse_ddr4_spd

T = datetime(2024, 1, 1, tzinfo=timezone.utc)
CLOCK = lambda: T  # noqa: E731


def make_spd(code_hi=0x80, code_lo=0x2C, serial=b"\x01\x02\x03\x04", part="PARTNUMBER-0001") -> bytes:
    """Constructed DDR4 SPD image (512 bytes): offsets per JEDEC DDR4 SPD annex (320-321, 325-328, 329-348)."""
    buf = bytearray(512)
    buf[2] = 0x0C  # DRAM device type: DDR4
    buf[320], buf[321] = code_hi, code_lo
    buf[325:329] = serial
    buf[329:349] = part.ljust(20).encode("ascii")
    return bytes(buf)


def test_parse_ddr4_spd():
    info = parse_ddr4_spd(make_spd())
    assert info["manufacturer_code"] == "802C"
    assert info["part_number"] == "PARTNUMBER-0001"
    assert info["serial"] == "01020304"


def test_parse_rejects_non_ddr4_or_short():
    with pytest.raises(ValueError):
        parse_ddr4_spd(b"\x00" * 10)
    bad = bytearray(make_spd())
    bad[2] = 0x0B
    with pytest.raises(ValueError):
        parse_ddr4_spd(bytes(bad))


def test_plugin_is_disabled_by_default():
    assert SpdCollector.enabled_by_default is False
    recs = SpdCollector(clock=CLOCK).collect()
    assert len(recs) == 1 and recs[0].privilege_needed is True and recs[0].errors


def test_plugin_with_injected_reader_produces_ram_records():
    recs = SpdCollector(reader=lambda: [make_spd()], enabled=True, clock=CLOCK).collect()
    assert recs[0].device_class.value == "ram" and recs[0].source == "spd"
    assert recs[0].raw_ids["manufacturer_code"] == "802C"
    assert recs[0].strings["serial"].startswith("sha256:")


def test_reader_failure_reported():
    def boom():
        raise SpdUnavailable("no driver-free SPD access")

    recs = SpdCollector(reader=boom, enabled=True, clock=CLOCK).collect()
    assert recs[0].errors and "no driver-free" in recs[0].errors[0]


def test_cli_does_not_enable_spd_unless_asked(monkeypatch):
    seen = {}

    def fake(only, include_serials, enable_spd=False):
        seen["spd"] = enable_spd
        return []

    monkeypatch.setattr(cli, "build_collectors", fake)
    cli.main(["scan"])
    assert seen["spd"] is False
    cli.main(["scan", "--enable-spd"])
    assert seen["spd"] is True
