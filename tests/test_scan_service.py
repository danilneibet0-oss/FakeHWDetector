import json
from datetime import datetime, timezone

from fakehw import cli, i18n
from fakehw.collectors.base import Collector
from fakehw.models.device import DeviceClass, DeviceRecord
from fakehw.report.json_export import export_json
from fakehw.scan import ScanService, assess

T = datetime(2024, 1, 1, tzinfo=timezone.utc)


def usb_counterfeit_device():
    return DeviceRecord(device_class=DeviceClass.USB, source="t", raw_ids={"vendor_id": "0001", "product_id": "7778"},
                        collected_at=T)


class Stub(Collector):
    def collect(self):
        return [usb_counterfeit_device()]


def test_assess_builds_report_with_findings_and_kb_versions():
    report = assess([usb_counterfeit_device()], lang="en")
    assert report.assessments[0].level.value == "LIKELY_FAKE"
    assert report.findings[0].rule_id == "kb.entry_marked_counterfeit"
    assert set(report.kb_versions) == {"pci", "usb"}


def test_assess_respects_language():
    en = assess([usb_counterfeit_device()], lang="en").findings[0].explanation
    ru = assess([usb_counterfeit_device()], lang="ru").findings[0].explanation
    assert en != ru and "контрафакт" in ru


def test_service_scan_uses_collectors_and_options():
    seen = {}

    def factory(only, include_serials, enable_spd=False):
        seen.update(only=only, serials=include_serials)
        return [Stub()]

    report = ScanService(collector_factory=factory).scan(include_serials=True, lang="en")
    assert seen == {"only": None, "serials": True}
    assert len(report.devices) == 1


def test_service_reassess_keeps_devices_changes_language():
    svc = ScanService(collector_factory=lambda *a, **k: [Stub()])
    report = svc.scan(False, "en")
    ru = svc.reassess(report, "ru")
    assert ru.devices == report.devices and ru.generated_at == report.generated_at
    assert ru.findings[0].explanation != report.findings[0].explanation


def test_export_json_roundtrip(tmp_path):
    report = assess([usb_counterfeit_device()], lang="en")
    out = tmp_path / "r.json"
    export_json(report, out)
    text = out.read_text(encoding="utf-8")
    assert text.endswith("\n") and json.loads(text)["devices"][0]["class"] == "usb"


def test_cli_gui_command_launches_ui(monkeypatch):
    called = []
    import fakehw.ui.app as app

    monkeypatch.setattr(app, "run", lambda: called.append(True) or 0)
    assert cli.main(["gui"]) == 0 and called
    i18n.set_language("en")
