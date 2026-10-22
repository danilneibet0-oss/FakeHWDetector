from typing import Callable

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QPushButton,
    QSplitter, QTableView, QTabWidget, QVBoxLayout, QWidget,
)

from .. import branding, i18n
from ..models.report import Report
from ..report.json_export import export_json
from ..report.md_export import export_markdown
from ..rules.scoring import virtualization_state
from ..scan import ScanService
from ..settings import Settings
from . import viewmodel as vm
from .detail_panel import DetailPanel
from .device_table import DeviceTableModel
from .sysinfo_panel import SystemInfoPanel
from .tasks import BackgroundTask

LANGUAGE_NAMES = {"en": "English", "ru": "Русский"}


class MainWindow(QMainWindow):
    def __init__(self, service: ScanService | None = None, choose_export_path: Callable[[], str] | None = None,
                 sysinfo_source=None):
        super().__init__()
        self.service = service or ScanService()
        self._choose_export_path = choose_export_path or self._default_chooser
        self.report: Report | None = None
        self._rows: list[vm.DeviceRow] = []
        self._task: BackgroundTask | None = None
        self._status: tuple[str, dict] = ("ui.status.ready", {})

        self.setWindowTitle(f"{branding.APP_NAME} — {branding.TAGLINE}")
        self.resize(1100, 700)

        self.scan_button = QPushButton()
        self.export_button = QPushButton()
        self.serials_check = QCheckBox()
        self.only_findings_check = QCheckBox()
        self.language_label = QLabel()
        self.language_combo = QComboBox()
        for code in i18n.SUPPORTED_LANGUAGES:
            self.language_combo.addItem(LANGUAGE_NAMES.get(code, code), code)

        bar = QHBoxLayout()
        for w in (self.scan_button, self.export_button, self.serials_check, self.only_findings_check):
            bar.addWidget(w)
        bar.addStretch(1)

        self.table_model = DeviceTableModel()
        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.detail = DetailPanel()

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setSizes([360, 280])

        check_page = QWidget()
        layout = QVBoxLayout(check_page)
        layout.addLayout(bar)
        layout.addWidget(split)
        self.sysinfo = SystemInfoPanel(sysinfo_source)

        language = QWidget()  # shared by both tabs, so it sits in the tab bar corner
        lang_layout = QHBoxLayout(language)
        lang_layout.setContentsMargins(0, 0, 4, 0)
        lang_layout.addWidget(self.language_label)
        lang_layout.addWidget(self.language_combo)

        self.tabs = QTabWidget()
        self.tabs.addTab(check_page, "")
        self.tabs.addTab(self.sysinfo, "")
        self.tabs.setCornerWidget(language, Qt.TopRightCorner)
        self.setCentralWidget(self.tabs)
        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label)

        settings = Settings.load()
        i18n.set_language(settings.language)
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(self.language_combo.findData(settings.language))
        self.language_combo.blockSignals(False)

        self.scan_button.clicked.connect(self.start_scan)
        self.export_button.clicked.connect(self.export_report)
        self.only_findings_check.toggled.connect(lambda _: self._refresh_rows())
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.sysinfo.copied.connect(lambda: self._show_status("ui.sys.copied"))

        self._retranslate()
        self.export_button.setEnabled(False)
        self._show_status("ui.status.ready")

    # ---- texts ----

    def _retranslate(self) -> None:
        t = i18n.t
        self.scan_button.setText(t("ui.scanning") if self._task else t("ui.scan"))
        self.export_button.setText(t("ui.export"))
        self.serials_check.setText(t("ui.include_serials"))
        self.only_findings_check.setText(t("ui.only_findings"))
        self.language_label.setText(t("ui.language"))
        self.tabs.setTabText(0, t("ui.tab.check"))
        self.tabs.setTabText(1, t("ui.tab.sysinfo"))
        self.table_model.refresh()
        self.detail.retranslate()
        self.sysinfo.retranslate()
        self.statusBar().showMessage(i18n.t(self._status[0], **self._status[1]))
        self._update_status()

    def _show_status(self, key: str, **kw) -> None:
        self._status = (key, kw)
        self.statusBar().showMessage(i18n.t(key, **kw))

    def _update_status(self) -> None:
        if not self.report:
            self.status_label.setText("")
            return
        kb = self.report.kb_versions
        virt = vm.virtualization_text(virtualization_state(self.report.devices))
        self.status_label.setText(
            i18n.t("ui.status.kb", pci=kb.get("pci", "?"), usb=kb.get("usb", "?")) + " | "
            + i18n.t("ui.status.virtualization", state=virt))

    # ---- scanning ----

    def start_scan(self) -> None:
        if self._task is not None:
            return
        include_serials, lang = self.serials_check.isChecked(), i18n.get_language()
        self._task = BackgroundTask(lambda: self.service.scan(include_serials, lang))
        self._task.signals.done.connect(self._scan_done)
        self._task.signals.failed.connect(self._scan_failed)
        self.scan_button.setEnabled(False)
        self.scan_button.setText(i18n.t("ui.scanning"))
        QThreadPool.globalInstance().start(self._task)

    def _finish_task(self) -> None:
        self._task = None
        self.scan_button.setEnabled(True)
        self.scan_button.setText(i18n.t("ui.scan"))

    def _scan_done(self, report: Report) -> None:
        self._finish_task()
        self.report = report
        self.export_button.setEnabled(True)
        self._refresh_rows()
        with_findings = sum(1 for r in self._rows if r.has_findings)
        self._show_status("ui.status.done", n=len(self._rows), m=with_findings)
        self._update_status()

    def _scan_failed(self, message: str) -> None:
        self._finish_task()
        self._show_status("ui.status.error", error=message)

    def _refresh_rows(self) -> None:
        self._rows = vm.build_rows(self.report) if self.report else []
        self.table_model.set_rows(vm.filter_rows(self._rows, self.only_findings_check.isChecked()))
        self.table.sortByColumn(0, Qt.DescendingOrder)  # most serious devices first
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.detail.show_row(None)

    def _selection_changed(self, *_args) -> None:
        indexes = self.table.selectionModel().selectedRows()
        self.detail.show_row(self.table_model.rows[indexes[0].row()] if indexes else None)

    def _tab_changed(self, _index: int) -> None:
        if self.tabs.currentWidget() is self.sysinfo:
            self.sysinfo.ensure_loaded()  # queried on first view only, so start-up stays fast

    # ---- language ----

    def _language_changed(self) -> None:
        lang = self.language_combo.currentData()
        i18n.set_language(lang)
        Settings(language=lang).save()
        if self.report:
            self.report = self.service.reassess(self.report, lang)  # regenerate finding texts, no new scan
            self._refresh_rows()
        self._retranslate()

    # ---- export ----

    def _default_chooser(self) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.t("ui.export.title"), "fakehw-report.json", i18n.t("ui.export.filter"))
        return path

    def export_report(self) -> None:
        if not self.report:
            return
        path = self._choose_export_path()
        if not path:
            return
        if str(path).lower().endswith(".md"):
            export_markdown(self.report, path, i18n.get_language())
        else:
            export_json(self.report, path)
        self._show_status("ui.export.saved", path=path)
