from pathlib import Path

import pytest

from fakehw.kb.pci_ids import parse_pci_ids
from fakehw.kb.usb_ids import parse_usb_ids

KB = Path(__file__).parent / "fixtures" / "kb"


@pytest.fixture(scope="module")
def pci():
    return parse_pci_ids((KB / "pci_fragment.ids").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def usb():
    return parse_usb_ids((KB / "usb_fragment.ids").read_text(encoding="utf-8"))


# ---- PCI ----

def test_pci_header(pci):
    assert pci.version == "2026.10.20"
    assert pci.date == "2026-10-20 03:15:01"


def test_pci_vendor_and_devices(pci):
    assert pci.vendor_name(0x10DE) == "NVIDIA Corporation"
    assert pci.device_name(0x10DE, 0x0020) == "NV4 [Riva TNT]"
    assert pci.has_vendor(0x10DE)
    assert pci.has_device(0x10DE, 0x0009)


def test_pci_subsystem(pci):
    assert pci.subsystem_name(0x10DE, 0x0020, 0x1043, 0x0200) == "V3400 TNT"
    assert pci.subsystem_name(0x10DE, 0x0020, 0x1048, 0x0C18) == "Erazor II SGRAM"


def test_pci_unknown_lookups_return_none_and_false(pci):
    assert pci.vendor_name(0xFFFF) is None
    assert pci.device_name(0x10DE, 0xFFFF) is None
    assert pci.device_name(0xFFFF, 0x0020) is None
    assert pci.subsystem_name(0x10DE, 0x0020, 0xFFFF, 0xFFFF) is None
    assert not pci.has_vendor(0xFFFF)
    assert not pci.has_device(0x10DE, 0xFFFF)


def test_pci_classes(pci):
    assert pci.class_name(0x00) == "Unclassified device"
    assert pci.class_name(0x01, 0x00) == "SCSI storage controller"
    assert pci.class_name(0x01, 0x00, 0x11).startswith("SCSI storage device (SOP target port using PQI)")
    assert pci.class_name(0x7F) is None


def test_pci_classes_do_not_leak_into_vendors(pci):
    assert not pci.has_vendor(0x00)
    assert len(pci.vendors) == 1


def test_pci_counts(pci):
    assert len(pci.vendors[0x10DE].devices) == 5
    assert pci.parse_errors == 0


def test_pci_crlf_input_equivalent():
    text = (KB / "pci_fragment.ids").read_text(encoding="utf-8")
    a = parse_pci_ids(text)
    b = parse_pci_ids(text.replace("\n", "\r\n"))
    assert a.vendors == b.vendors and a.version == b.version


def test_pci_malformed_lines_are_counted_not_fatal():
    text = "10de  NVIDIA Corporation\n\tzzzz  broken\n\t0020  NV4 [Riva TNT]\n???\n"
    db = parse_pci_ids(text)
    assert db.parse_errors == 2
    assert db.device_name(0x10DE, 0x0020) == "NV4 [Riva TNT]"


def test_pci_orphan_device_line_is_error():
    db = parse_pci_ids("\t0020  NV4 [Riva TNT]\n")
    assert db.parse_errors == 1 and not db.vendors


def test_pci_no_version_header():
    assert parse_pci_ids("10de  NVIDIA Corporation\n").version is None


# ---- USB ----

def test_usb_header(usb):
    assert usb.version == "2026.06.26"
    assert usb.date == "2026-06-26 20:34:02"


def test_usb_vendor_device(usb):
    assert usb.vendor_name(0x046D) == "Logitech, Inc."
    assert usb.device_name(0x046D, 0x0200) == "WingMan Extreme Joystick"
    assert usb.has_device(0x046D, 0x0242)
    assert not usb.has_device(0x046D, 0xFFFF)
    assert usb.vendor_name(0xFFFF) is None


def test_usb_db_marks_counterfeit_entry_verbatim(usb):
    # The upstream database itself lists this entry; later rules may use it.
    assert usb.device_name(0x0001, 0x7778) == "Counterfeit flash drive [Kingston]"


def test_usb_classes(usb):
    assert usb.class_name(0x03) == "Human Interface Device"
    assert usb.class_name(0x03, 0x01) == "Boot Interface Subclass"
    assert usb.class_name(0x03, 0x00, 0x02) == "Mouse"
    assert usb.class_name(0x7F) is None


def test_usb_other_sections_are_ignored(usb):
    assert usb.parse_errors == 0
    assert len(usb.vendors) == 3


def test_usb_malformed_counted():
    db = parse_usb_ids("046d  Logitech, Inc.\n\txyz  broken\n")
    assert db.parse_errors == 1 and db.vendor_name(0x046D) == "Logitech, Inc."


# ---- bundled full snapshots ----

def test_bundled_pci_snapshot_parses_fully():
    from fakehw.kb.updater import KbStore

    db = KbStore().pci()
    assert db.parse_errors == 0
    assert db.vendor_name(0x10DE) == "NVIDIA Corporation"
    assert db.device_name(0x10DE, 0x0020) == "NV4 [Riva TNT]"
    assert len(db.vendors) > 2000


def test_bundled_usb_snapshot_parses_fully():
    from fakehw.kb.updater import KbStore

    db = KbStore().usb()
    assert db.parse_errors == 0
    assert db.vendor_name(0x046D) == "Logitech, Inc."
    assert len(db.vendors) > 2000


def test_decode_ids_tolerates_stray_non_utf8_byte():
    from fakehw.kb._common import decode_ids

    # real upstream usb.ids line contains byte 0xb4 in the HID tables
    text = decode_ids(b"046d  Logitech, Inc.\n\t034  \xb4 and \" (Accent Acute)\n")
    assert "Logitech" in text


def test_usb_extra_spaces_after_id_tolerated():
    # real upstream line: "\t10ad   Cinergy H5 Rev. 2" (three spaces)
    db = parse_usb_ids("0ccd  TerraTec Electronic GmbH\n\t10ad   Cinergy H5 Rev. 2\n")
    assert db.parse_errors == 0
    assert db.device_name(0x0CCD, 0x10AD) == "Cinergy H5 Rev. 2"
