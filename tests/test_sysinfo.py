import copy
import json
from pathlib import Path

import pytest

from fakehw import i18n, sysinfo
from fakehw.collectors._gpu_io import GpuProbeUnavailable
from fakehw.collectors.powershell import PsQueryError
from fakehw.ui import sysinfo_view as sv

FIX = Path(__file__).parent / "fixtures" / "collectors"


def info():
    return json.loads((FIX / "local_sysinfo.json").read_text(encoding="utf-8"))["info"]


@pytest.fixture(autouse=True)
def _en():
    i18n.set_language("en")
    yield
    i18n.set_language("en")


def section(sections, title):
    return next(s for s in sections if s.title == title)


def rows(sections, title):
    return dict(section(sections, title).rows)


# ---- source ----

def test_source_adds_dxgi_memory(monkeypatch):
    monkeypatch.setattr(sysinfo, "run_json", lambda script, timeout: {"os": {}})
    src = sysinfo.WmiSystemInfoSource(dxgi=lambda: [{"description": "GPU", "dedicated_video_memory": 1024, "vendor_id": 1}])
    assert src.query()["dxgi"] == [{"description": "GPU", "dedicated_video_memory": 1024}]


def test_source_without_dxgi_still_answers(monkeypatch):
    def no_dxgi():
        raise GpuProbeUnavailable("no dxgi")

    monkeypatch.setattr(sysinfo, "run_json", lambda script, timeout: {"os": {}})
    assert sysinfo.WmiSystemInfoSource(dxgi=no_dxgi).query()["dxgi"] == []


def test_source_rejects_unexpected_output(monkeypatch):
    monkeypatch.setattr(sysinfo, "run_json", lambda script, timeout: [])
    with pytest.raises(PsQueryError):
        sysinfo.WmiSystemInfoSource(dxgi=list).query()


def test_script_queries_no_serials_or_addresses():
    script = sysinfo.SCRIPT.lower()
    for word in ("serial", "uuid", "macaddress", "productkey"):
        assert word not in script


# ---- sections ----

def test_sections_in_fixed_order():
    titles = [s.title for s in sv.build_sections(info())]
    assert titles == ["Operating system", "Computer", "Motherboard and BIOS", "Processor", "Memory",
                      "Video adapter", "Drives", "Volumes"]


def test_os_and_computer_rows():
    s = sv.build_sections(info())
    os_rows = rows(s, "Operating system")
    assert os_rows["Name"] == "Майкрософт Windows 11 Pro"
    assert os_rows["Version"] == "25H2" and os_rows["Build"] == "26200.9711"
    assert os_rows["Installed"] == "2026-06-24 19:20" and os_rows["Last boot"] == "2026-10-21 15:08"
    pc = rows(s, "Computer")
    assert pc["Computer name"] == "TEST-PC" and pc["Model"] == "Surface Pro" and pc["Manufacturer"] == "Microsoft Corporation"


def test_board_and_bios():
    r = rows(sv.build_sections(info()), "Motherboard and BIOS")
    assert r["Motherboard"] == "Microsoft Corporation Surface Pro"  # missing version is left out, not "None"
    assert r["BIOS"] == "Microsoft Corporation 239.871.768" and r["BIOS date"] == "2015-11-07"


def test_cpu_rows():
    r = rows(sv.build_sections(info()), "Processor")
    assert r["Model"] == "Intel(R) Core(TM) i5-7300U CPU @ 2.60GHz"
    assert r["Cores / threads"] == "2 / 4" and r["Clock speed"] == "2712 MHz"
    assert r["Cache L2 / L3"] == "512 KB / 3 MB" and r["Socket"] == "U3E1"


def test_memory_rows_sorted_by_slot():
    m = section(sv.build_sections(info()), "Memory")
    r = dict(m.rows)
    assert r["Installed"] == "8 GB" and r["Available to Windows"] == "7.9 GB" and r["Free now"] == "513 MB"
    slots = [label for label, _ in m.rows if label.startswith("Channel")]
    assert slots == ["ChannelA-DIMM0", "ChannelB-DIMM0"]
    assert r["ChannelA-DIMM0"] == "SK Hynix H9CCNNNBJTALAR-NUD, 4 GB, LPDDR3, 1867 MHz"


def test_memory_type_codes_follow_smbios():
    assert sv.SMBIOS_MEMORY_TYPES[26] == "DDR4"  # matches the DDR4 module in local_memory.json
    i = info()
    i["memory"][0]["SMBIOSMemoryType"] = 2  # "Unknown" in SMBIOS: no guess is shown
    i["memory"][0]["ConfiguredClockSpeed"] = 1600
    r = rows(sv.build_sections(i), "Memory")
    assert r["ChannelB-DIMM0"] == "SK Hynix H9CCNNNBJTALAR-NUD, 4 GB, 1867 MHz (running at 1600 MHz)"


def test_video_memory_from_dxgi_only():
    r = rows(sv.build_sections(info()), "Video adapter")
    assert r["Model"] == "Intel(R) HD Graphics 620" and r["Video memory"] == "128 MB"
    assert r["Driver"] == "27.20.100.8682 (2020-09-06)" and r["Display mode"] == "2736 × 1824, 59 Hz"
    i = info()
    del i["dxgi"]
    assert "Video memory" not in rows(sv.build_sections(i), "Video adapter")  # WMI AdapterRAM is capped at 4 GB, not used


def test_several_adapters_are_numbered():
    i = info()
    i["video"].append({"Name": "NVIDIA GeForce RTX 3060 Ti"})
    i["dxgi"] = [{"description": "NVIDIA GeForce RTX 3060 Ti", "dedicated_video_memory": 8 * 1024**3}]
    s = sv.build_sections(i)
    assert rows(s, "Video adapter 2")["Video memory"] == "8 GB"
    assert "Video memory" not in rows(s, "Video adapter 1")


def test_drives_and_volumes():
    s = sv.build_sections(info())
    d = section(s, "Drives").rows
    assert d == [("Disk 0", "KBG30ZPZ256G TOSHIBA, 256 GB, SCSI"), ("Disk 1", "SDXC Card, 484 GB, USB, removable")]
    assert rows(s, "Volumes") == {"C:": "NTFS, 101 GB free of 237 GB"}


def test_missing_data_gives_empty_sections_not_errors():
    s = sv.build_sections({"os": None, "cpu": None})
    assert all(sec.rows == [] for sec in s)
    assert "no data" in sv.sections_html(s)


def test_russian_labels_and_decimal_comma():
    i18n.set_language("ru")
    s = sv.build_sections(info())
    assert s[0].title == "Операционная система"
    assert rows(s, "Оперативная память")["Доступно Windows"] == "7,9 ГБ"


def test_html_escapes_firmware_strings():
    i = info()
    i["computer"]["Model"] = "<b>Board</b> & Co"
    html = sv.sections_html(sv.build_sections(i))
    assert "&lt;b&gt;Board&lt;/b&gt; &amp; Co" in html and "<b>Board</b>" not in html


def test_plain_text_for_clipboard():
    text = sv.sections_text(sv.build_sections(info()))
    assert "[Processor]" in text and "Cores / threads: 2 / 4" in text
    assert "\nC: NTFS, 101 GB free of 237 GB\n" in text  # a label ending in ':' gets no second colon
    assert text == sv.sections_text(sv.build_sections(copy.deepcopy(info())))  # reproducible
