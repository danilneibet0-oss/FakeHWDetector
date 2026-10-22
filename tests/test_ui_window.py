import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from fakehw import branding, i18n  # noqa: E402
from fakehw.settings import Settings  # noqa: E402
from fakehw.ui.main_window import MainWindow  # noqa: E402
from fakehw.rules.engine import Engine  # noqa: E402

from test_ui_viewmodel import make_report  # noqa: E402


class FakeService:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def scan(self, include_serials, lang):
        self.calls.append(("scan", include_serials, lang))
        if self.fail:
            raise RuntimeError("boom")
        return make_report()

    def reassess(self, report, lang):
        self.calls.append(("reassess", lang))
        return report


class FakeSysInfo:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def query(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("no wmi")
        path = Path(__file__).parent / "fixtures" / "collectors" / "local_sysinfo.json"
        return json.loads(path.read_text(encoding="utf-8"))["info"]


@pytest.fixture(autouse=True)
def _en():
    i18n.set_language("en")
    yield
    i18n.set_language("en")


def make_window(qtbot, service=None, chooser=None, sysinfo=None):
    w = MainWindow(service=service or FakeService(), choose_export_path=chooser, sysinfo_source=sysinfo or FakeSysInfo())
    qtbot.addWidget(w)
    return w


def open_sysinfo(qtbot, sysinfo=None):
    src = sysinfo or FakeSysInfo()
    w = make_window(qtbot, sysinfo=src)
    w.tabs.setCurrentWidget(w.sysinfo)
    qtbot.waitUntil(lambda: w.sysinfo.refresh_button.isEnabled(), timeout=5000)
    return w, src


def scanned(qtbot, **kw):
    w = make_window(qtbot, **kw)
    w.scan_button.click()
    qtbot.waitUntil(lambda: w.table_model.rowCount() > 0, timeout=5000)
    return w


def pos(w, device_index):
    """Table position of a device: after a scan the most serious devices are listed first."""
    return next(i for i, r in enumerate(w.table_model.rows) if r.index == device_index)


def test_most_serious_devices_are_listed_first(qtbot):
    w = scanned(qtbot)
    assert [r.index for r in w.table_model.rows][:2] == [1, 4]  # likely counterfeit, then unverified
    assert [r.index for r in w.table_model.rows][2:] == [0, 2, 3]  # ties keep device order


def test_window_title_comes_from_branding(qtbot):
    w = make_window(qtbot)
    assert branding.APP_NAME in w.windowTitle() and branding.TAGLINE in w.windowTitle()


def test_scan_fills_table_with_colours(qtbot):
    w = scanned(qtbot)
    m = w.table_model
    assert m.rowCount() == 5
    level_col = 0
    bg_likely = m.data(m.index(pos(w, 1), level_col), Qt.BackgroundRole)
    bg_info = m.data(m.index(pos(w, 0), level_col), Qt.BackgroundRole)
    assert bg_likely is not None and bg_info is not None and bg_likely != bg_info
    assert m.data(m.index(pos(w, 1), level_col), Qt.DisplayRole).endswith("Likely counterfeit")


def test_selecting_a_row_shows_details(qtbot):
    w = scanned(qtbot)
    w.table.selectRow(pos(w, 1))
    qtbot.waitUntil(lambda: "kb.entry_marked_counterfeit" in w.detail.toHtml(), timeout=3000)
    html = w.detail.toHtml()
    assert "7778" in html and "Check origin." in html


def test_initial_detail_prompts_to_select(qtbot):
    w = make_window(qtbot)
    assert "Select a device" in w.detail.toPlainText()


def test_scan_runs_off_the_ui_thread_and_passes_options(qtbot):
    svc = FakeService()
    w = make_window(qtbot, service=svc)
    w.serials_check.setChecked(True)
    w.scan_button.click()
    assert not w.scan_button.isEnabled()  # busy while scanning
    qtbot.waitUntil(lambda: w.scan_button.isEnabled() and w.table_model.rowCount() > 0, timeout=5000)
    assert svc.calls[0] == ("scan", True, "en")


def test_scan_error_is_shown_not_raised(qtbot):
    w = make_window(qtbot, service=FakeService(fail=True))
    w.scan_button.click()
    qtbot.waitUntil(lambda: w.scan_button.isEnabled() and "boom" in w.statusBar().currentMessage(), timeout=5000)
    assert w.table_model.rowCount() == 0


def test_export_writes_json_report(qtbot, tmp_path):
    out = tmp_path / "report.json"
    w = scanned(qtbot, chooser=lambda: str(out))
    w.export_button.click()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["devices"]) == 5 and data["assessments"][1]["level"] == "LIKELY_FAKE"


def test_export_disabled_until_a_scan_exists(qtbot):
    w = make_window(qtbot)
    assert not w.export_button.isEnabled()
    w2 = scanned(qtbot)
    assert w2.export_button.isEnabled()


def test_export_cancel_writes_nothing(qtbot, tmp_path):
    w = scanned(qtbot, chooser=lambda: "")
    w.export_button.click()
    assert list(tmp_path.iterdir()) == []


def test_language_switch_relabels_and_persists(qtbot):
    svc = FakeService()
    w = scanned(qtbot, service=svc)
    w.language_combo.setCurrentIndex(w.language_combo.findData("ru"))
    assert w.scan_button.text() == "Сканировать"
    assert w.table_model.data(w.table_model.index(pos(w, 1), 0), Qt.DisplayRole).endswith("Вероятная подделка")
    assert ("reassess", "ru") in svc.calls  # texts of findings are regenerated, no new scan
    assert Settings.load().language == "ru"


def test_language_from_settings_is_applied_at_start(qtbot):
    Settings(language="ru").save()
    w = make_window(qtbot)
    assert w.scan_button.text() == "Сканировать"
    assert w.language_combo.currentData() == "ru"


def test_only_findings_filter(qtbot):
    w = scanned(qtbot)
    w.only_findings_check.setChecked(True)
    assert w.table_model.rowCount() == 2


def test_status_bar_reports_kb_versions_and_counts(qtbot):
    w = scanned(qtbot)
    msg = w.statusBar().currentMessage() + w.status_label.text()
    assert "2026.10.20" in msg and "5" in msg


def test_privilege_note_visible_in_table(qtbot):
    w = scanned(qtbot)
    note = w.table_model.data(w.table_model.index(pos(w, 4), 5), Qt.DisplayRole)
    assert "administrator" in note


def test_status_message_is_translated_on_language_switch(qtbot):
    w = scanned(qtbot)
    assert "devices" in w.statusBar().currentMessage()
    w.language_combo.setCurrentIndex(w.language_combo.findData("ru"))
    assert "Устройств" in w.statusBar().currentMessage()


def test_tabs_are_translated(qtbot):
    w = make_window(qtbot)
    assert [w.tabs.tabText(i) for i in range(2)] == ["Device check", "About this computer"]
    w.language_combo.setCurrentIndex(w.language_combo.findData("ru"))
    assert [w.tabs.tabText(i) for i in range(2)] == ["Проверка устройств", "Сведения о компьютере"]


def test_sysinfo_is_queried_only_when_its_tab_is_opened(qtbot):
    src = FakeSysInfo()
    w = make_window(qtbot, sysinfo=src)
    assert src.calls == 0 and not w.sysinfo.copy_button.isEnabled()
    w.tabs.setCurrentWidget(w.sysinfo)
    qtbot.waitUntil(lambda: "Surface Pro" in w.sysinfo.view.toPlainText(), timeout=5000)
    text = w.sysinfo.view.toPlainText()
    assert "Intel(R) Core(TM) i5-7300U" in text and "KBG30ZPZ256G TOSHIBA" in text
    w.tabs.setCurrentIndex(0)
    w.tabs.setCurrentWidget(w.sysinfo)
    assert src.calls == 1  # switching tabs does not query again


def test_sysinfo_refresh_queries_again(qtbot):
    w, src = open_sysinfo(qtbot)
    w.sysinfo.refresh_button.click()
    qtbot.waitUntil(lambda: src.calls == 2 and w.sysinfo.refresh_button.isEnabled(), timeout=5000)


def test_sysinfo_copy_puts_text_on_clipboard(qtbot):
    w, _ = open_sysinfo(qtbot)
    w.sysinfo.copy_button.click()
    clip = QGuiApplication.clipboard().text()
    assert "[Processor]" in clip and "Cores / threads: 2 / 4" in clip
    assert "Copied" in w.statusBar().currentMessage()


def test_sysinfo_error_is_shown_not_raised(qtbot):
    w, _ = open_sysinfo(qtbot, FakeSysInfo(fail=True))
    assert "no wmi" in w.sysinfo.view.toPlainText() and not w.sysinfo.copy_button.isEnabled()


def test_sysinfo_language_switch_rerenders_without_query(qtbot):
    w, src = open_sysinfo(qtbot)
    w.language_combo.setCurrentIndex(w.language_combo.findData("ru"))
    text = w.sysinfo.view.toPlainText()
    assert "Процессор" in text and "Ядра / потоки" in text and w.sysinfo.refresh_button.text() == "Обновить"
    assert src.calls == 1


def test_export_markdown_by_extension(qtbot, tmp_path):
    out = tmp_path / "report.md"
    w = scanned(qtbot, chooser=lambda: str(out))
    w.export_button.click()
    text = out.read_text(encoding="utf-8")
    assert text.startswith(f"# {branding.APP_NAME}") and "kb.entry_marked_counterfeit" in text
