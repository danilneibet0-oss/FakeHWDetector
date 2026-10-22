from datetime import datetime, timezone

import pytest

from fakehw import i18n
from fakehw.models.device import DeviceClass, DeviceRecord
from fakehw.models.finding import Assessment, Finding, Level
from fakehw.models.report import Report
from fakehw.ui import viewmodel as vm

T = datetime(2024, 1, 1, tzinfo=timezone.utc)


def dev(cls, source="t", raw=None, strings=None, **kw):
    return DeviceRecord(device_class=cls, source=source, raw_ids=raw or {}, strings=strings or {}, collected_at=T, **kw)


def make_report():
    devices = [
        dev(DeviceClass.GPU, raw={"vendor_id": "10DE", "device_id": "2486", "subsys_vendor_id": "1B4C", "subsys_device_id": "146C"},
            strings={"name": "NVIDIA GeForce RTX 3060 Ti"}),
        dev(DeviceClass.USB, raw={"vendor_id": "0001", "product_id": "7778"}, strings={"name": "<b>Flash</b> drive"}),
        dev(DeviceClass.CPU, raw={"family": "6", "model": "167", "stepping": "1"}, strings={"brand": "Some CPU"}),
        dev(DeviceClass.RAM, raw={"capacity_bytes": "8589934592"}, strings={"manufacturer": "Kingston", "part_number": "KHX2666C16/8G"}),
        dev(DeviceClass.STORAGE, raw={"bus_type": "SATA", "size_bytes": "120031511040"}, strings={"model": "ADATA SU650"},
            privilege_needed=True, errors=["requires administrator rights"]),
    ]
    findings = [
        Finding(rule_id="kb.entry_marked_counterfeit", level=Level.LIKELY_FAKE, score=0.65, explanation="Entry is marked. Based on signals: db_marks_counterfeit=True.",
                evidence=["db_marks_counterfeit=True"], recommendation="Check origin.", device_index=1),
        Finding(rule_id="storage.nvme_vid_unregistered", level=Level.UNVERIFIED, score=0.0, explanation="Could not verify: required data is unavailable (nvme_vid_known).",
                evidence=["nvme_vid_known=unknown"], device_index=4),
    ]
    assessments = [
        Assessment(device_index=0, level=Level.INFO, score=0.0),
        Assessment(device_index=1, level=Level.LIKELY_FAKE, score=0.65, rule_ids=["kb.entry_marked_counterfeit"]),
        Assessment(device_index=2, level=Level.INFO, score=0.0),
        Assessment(device_index=3, level=Level.INFO, score=0.0),
        Assessment(device_index=4, level=Level.UNVERIFIED, score=0.0),
    ]
    return Report(generated_at=T, devices=devices, findings=findings, assessments=assessments,
                  kb_versions={"pci": "2026.10.20", "usb": "2026.06.26"})


@pytest.fixture(autouse=True)
def _en():
    i18n.set_language("en")
    yield
    i18n.set_language("en")


def test_rows_follow_device_order_and_carry_levels():
    rows = vm.build_rows(make_report())
    assert [r.index for r in rows] == [0, 1, 2, 3, 4]
    assert [r.level for r in rows] == [Level.INFO, Level.LIKELY_FAKE, Level.INFO, Level.INFO, Level.UNVERIFIED]
    assert rows[1].score == 0.65


def test_display_names_per_class():
    names = [r.name for r in vm.build_rows(make_report())]
    assert names[0] == "NVIDIA GeForce RTX 3060 Ti"
    assert names[2] == "Some CPU"
    assert names[3] == "Kingston KHX2666C16/8G (8 GB)"
    assert names[4].startswith("ADATA SU650")


def test_id_summaries():
    ids = [r.ids for r in vm.build_rows(make_report())]
    assert ids[0] == "10DE:2486 (1B4C:146C)"
    assert ids[1] == "0001:7778"
    assert ids[2] == "6/167/1"


def test_notes_for_privilege_and_errors():
    notes = vm.build_rows(make_report())[4].note
    assert "administrator" in notes


def test_findings_attached_to_the_right_row():
    rows = vm.build_rows(make_report())
    assert [f.rule_id for f in rows[1].findings] == ["kb.entry_marked_counterfeit"]
    assert rows[0].findings == []


def test_level_colors_and_symbols_are_distinct():
    colors = {vm.level_color(l) for l in Level}
    symbols = {vm.level_symbol(l) for l in Level}
    assert len(colors) == 4 and len(symbols) == 4  # colour is never the only cue


def test_labels_follow_language():
    rows = vm.build_rows(make_report())
    assert vm.level_label(rows[1].level) == "Likely counterfeit"
    i18n.set_language("ru")
    assert vm.level_label(rows[1].level) == "Вероятная подделка"
    assert vm.class_label(DeviceClass.CPU) == "Процессор"


def test_detail_html_contains_ids_rules_and_recommendation():
    row = vm.build_rows(make_report())[1]
    html = vm.detail_html(row)
    assert "0001" in html and "7778" in html
    assert "kb.entry_marked_counterfeit" in html and "Check origin." in html
    assert "db_marks_counterfeit=True" in html


def test_detail_html_escapes_device_strings():
    html = vm.detail_html(vm.build_rows(make_report())[1])
    assert "<b>Flash</b>" not in html and "&lt;b&gt;Flash&lt;/b&gt;" in html


def test_detail_html_lists_unverified_and_problems():
    html = vm.detail_html(vm.build_rows(make_report())[4])
    assert "nvme_vid_unregistered" in html
    assert "requires administrator rights" in html


def test_detail_html_without_findings_says_so():
    html = vm.detail_html(vm.build_rows(make_report())[0])
    assert "No rules triggered" in html


def test_detail_never_uses_verdict_word_fake_outside_rule_ids():
    for row in vm.build_rows(make_report()):
        text = vm.detail_html(row).replace("kb.entry_marked_counterfeit", "")
        assert "fake" not in text.lower()


def test_virtualization_text_localised():
    assert "Hyper-V" in vm.virtualization_text("ambiguous")
    i18n.set_language("ru")
    assert vm.virtualization_text("none") == "нет"


def test_only_findings_filter():
    rows = vm.build_rows(make_report())
    shown = vm.filter_rows(rows, only_findings=True)
    assert [r.index for r in shown] == [1, 4]
    assert len(vm.filter_rows(rows, only_findings=False)) == 5
