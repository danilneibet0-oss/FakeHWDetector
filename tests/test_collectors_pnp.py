import json
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fakehw.collectors.pci import PciCollector
from fakehw.collectors.pnp import PnpQueryError
from fakehw.collectors.usb import UsbCollector

FIX = Path(__file__).parent / "fixtures" / "collectors"
T = datetime(2024, 1, 1, tzinfo=timezone.utc)
CLOCK = lambda: T  # noqa: E731


def load_entries() -> list[dict]:
    return json.loads((FIX / "local_pnp.json").read_text(encoding="utf-8"))["entries"]


class FakeSource:
    def __init__(self, entries):
        self.entries = entries

    def query(self):
        return self.entries


def entry(device_id, hardware_id=(), compatible_id=(), name="N", manufacturer="M", pnp_class="C", present=True):
    return {
        "DeviceID": device_id, "Name": name, "Manufacturer": manufacturer, "PNPClass": pnp_class,
        "HardwareID": list(hardware_id), "CompatibleID": list(compatible_id), "Present": present,
    }


# ---- PCI ----

def test_pci_real_fixture_basic():
    recs = PciCollector(FakeSource(load_entries()), clock=CLOCK).collect()
    assert recs and all(r.device_class.value in ("pci", "gpu") for r in recs)
    assert all(r.source == "wmi:Win32_PnPEntity" and r.collected_at == T for r in recs)
    r0 = next(r for r in recs if r.raw_ids.get("vendor_id") == "8086" and r.raw_ids.get("device_id") == "4C11")
    # DeviceID: PCI\VEN_8086&DEV_4C11&SUBSYS_4C111849&REV_01 -> subsystem device 4C11, subsystem vendor 1849
    assert r0.raw_ids["subsys_device_id"] == "4C11"
    assert r0.raw_ids["subsys_vendor_id"] == "1849"
    assert r0.raw_ids["revision"] == "01"
    assert r0.raw_ids["class_code"] == "088000"


def test_pci_display_controllers_become_gpu_class():
    recs = PciCollector(FakeSource(load_entries()), clock=CLOCK).collect()
    for r in recs:
        cc = r.raw_ids.get("class_code") or ""
        assert (r.device_class.value == "gpu") == cc.startswith("03")


def test_pci_all_ids_are_normalised_uppercase_hex():
    for r in PciCollector(FakeSource(load_entries()), clock=CLOCK).collect():
        for k in ("vendor_id", "device_id"):
            v = r.raw_ids[k]
            assert len(v) == 4 and v == v.upper()
            int(v, 16)


def test_pci_unparsable_device_id_recorded_as_error():
    recs = PciCollector(FakeSource([entry("PCI\\GARBAGE\\1")]), clock=CLOCK).collect()
    assert len(recs) == 1 and recs[0].errors and recs[0].raw_ids == {}


def test_pci_ignores_non_pci_and_not_present():
    entries = [
        entry("USB\\VID_046D&PID_C08F\\X"),
        entry("PCI\\VEN_8086&DEV_4C11&SUBSYS_4C111849&REV_01\\3&1&0&40", present=False),
    ]
    assert PciCollector(FakeSource(entries), clock=CLOCK).collect() == []


def test_pci_missing_class_code_is_none_not_guess():
    e = entry("PCI\\VEN_8086&DEV_4C11&SUBSYS_4C111849&REV_01\\3&1&0&40", hardware_id=["PCI\\VEN_8086&DEV_4C11"])
    r = PciCollector(FakeSource([e]), clock=CLOCK).collect()[0]
    assert "class_code" not in r.raw_ids and r.device_class.value == "pci"


def test_pci_order_independent_of_input_order():
    entries = load_entries()
    shuffled = entries[:]
    random.Random(1).shuffle(shuffled)
    a = PciCollector(FakeSource(entries), clock=CLOCK).collect()
    b = PciCollector(FakeSource(shuffled), clock=CLOCK).collect()
    assert [x.model_dump_json() for x in a] == [x.model_dump_json() for x in b]


def test_pci_source_failure_reported():
    class Broken:
        def query(self):
            raise PnpQueryError("powershell missing")

    recs = PciCollector(Broken(), clock=CLOCK).collect()
    assert len(recs) == 1 and "powershell missing" in recs[0].errors[0]


# ---- USB ----

def test_usb_real_fixture_basic():
    recs = UsbCollector(FakeSource(load_entries()), clock=CLOCK).collect()
    assert recs and all(r.device_class.value == "usb" for r in recs)
    ch340 = next(r for r in recs if r.raw_ids.get("vendor_id") == "1A86")
    assert ch340.raw_ids["product_id"] == "7523"
    assert ch340.raw_ids["revision"] == "8134"  # from HardwareID USB\VID_1A86&PID_7523&REV_8134


def test_usb_interface_children_are_skipped():
    recs = UsbCollector(FakeSource(load_entries()), clock=CLOCK).collect()
    assert not any("MI_" in (r.strings.get("device_id") or "") for r in recs)
    logi = [r for r in recs if r.raw_ids.get("vendor_id") == "046D"]
    assert len(logi) == 1  # parent device only, MI_00 / MI_01 interfaces dropped


def test_usb_non_mi_child_devices_are_skipped():
    # seen on a real machine: Windows exposes a LampArray child under the keyboard/mouse
    e = entry(r"USB\VID_046D&PID_C08F&LAMPARRAY" + "\\" + r"6&25B3A71A&0&0F6934543336_SLOT00")
    assert UsbCollector(FakeSource([e]), clock=CLOCK).collect() == []


def test_usb_descriptor_failure_is_flagged():
    recs = UsbCollector(FakeSource(load_entries()), clock=CLOCK).collect()
    bad = [r for r in recs if r.raw_ids.get("vendor_id") == "0000"]
    assert bad and all(r.errors for r in bad)


def test_usb_serial_hashed_by_default():
    e = entry("USB\\VID_046D&PID_C08F\\SERIAL123", hardware_id=["USB\\VID_046D&PID_C08F&REV_4501", "USB\\VID_046D&PID_C08F"])
    r = UsbCollector(FakeSource([e]), clock=CLOCK).collect()[0]
    assert r.strings["serial"].startswith("sha256:")
    assert "SERIAL123" not in r.model_dump_json()


def test_usb_serial_plain_with_flag():
    e = entry("USB\\VID_046D&PID_C08F\\SERIAL123", hardware_id=["USB\\VID_046D&PID_C08F"])
    r = UsbCollector(FakeSource([e]), include_serials=True, clock=CLOCK).collect()[0]
    assert r.strings["serial"] == "SERIAL123"


def test_usb_hash_is_stable():
    e = entry("USB\\VID_046D&PID_C08F\\SERIAL123", hardware_id=["USB\\VID_046D&PID_C08F"])
    a = UsbCollector(FakeSource([e]), clock=CLOCK).collect()[0].strings["serial"]
    b = UsbCollector(FakeSource([e]), clock=CLOCK).collect()[0].strings["serial"]
    assert a == b


def test_usb_windows_generated_instance_is_not_a_serial():
    e = entry("USB\\VID_1A86&PID_7523\\5&244075AE&0&14", hardware_id=["USB\\VID_1A86&PID_7523&REV_8134"])
    r = UsbCollector(FakeSource([e]), clock=CLOCK).collect()[0]
    assert "serial" not in r.strings


def test_usb_hubs_without_vid_are_ignored():
    assert UsbCollector(FakeSource([entry("USB\\ROOT_HUB30\\4&1&0&0")]), clock=CLOCK).collect() == []


def test_usb_order_independent_of_input_order():
    entries = load_entries()
    shuffled = entries[:]
    random.Random(2).shuffle(shuffled)
    a = UsbCollector(FakeSource(entries), clock=CLOCK).collect()
    b = UsbCollector(FakeSource(shuffled), clock=CLOCK).collect()
    assert [x.model_dump_json() for x in a] == [x.model_dump_json() for x in b]


def test_usb_source_failure_reported():
    class Broken:
        def query(self):
            raise PnpQueryError("boom")

    recs = UsbCollector(Broken(), clock=CLOCK).collect()
    assert len(recs) == 1 and recs[0].errors


# ---- real-machine smoke (Windows only) ----

@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
def test_live_wmi_source_returns_entries():
    from fakehw.collectors.pnp import WmiPnpSource

    entries = WmiPnpSource().query()
    assert isinstance(entries, list) and entries
    assert all("DeviceID" in e for e in entries)
