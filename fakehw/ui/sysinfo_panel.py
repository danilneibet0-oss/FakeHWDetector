from html import escape

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from .. import i18n
from ..sysinfo import WmiSystemInfoSource
from . import sysinfo_view as sv
from .tasks import BackgroundTask


class SystemInfoPanel(QWidget):
    """The "About this computer" tab: queried when first shown, re-rendered (not re-queried) on a language switch."""

    copied = Signal()

    def __init__(self, source=None) -> None:
        super().__init__()
        self.source = source or WmiSystemInfoSource()
        self.info: dict | None = None
        self._error: str | None = None
        self._task: BackgroundTask | None = None

        self.refresh_button = QPushButton()
        self.copy_button = QPushButton()
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)

        bar = QHBoxLayout()
        bar.addWidget(self.refresh_button)
        bar.addWidget(self.copy_button)
        bar.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.view)

        self.refresh_button.clicked.connect(self.refresh)
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        self.retranslate()

    def ensure_loaded(self) -> None:
        if self.info is None and self._error is None and self._task is None:
            self.refresh()

    def refresh(self) -> None:
        if self._task is not None:
            return
        self._error = None
        self._task = BackgroundTask(self.source.query)
        self._task.signals.done.connect(self._done)
        self._task.signals.failed.connect(self._failed)
        self._render()
        QThreadPool.globalInstance().start(self._task)

    def _done(self, info: dict) -> None:
        self._task = None
        self.info = info
        self._render()

    def _failed(self, message: str) -> None:
        self._task = None
        self._error = message
        self._render()

    def copy_to_clipboard(self) -> None:
        if self.info is None:
            return
        QGuiApplication.clipboard().setText(sv.sections_text(sv.build_sections(self.info)))
        self.copied.emit()

    def retranslate(self) -> None:
        self.refresh_button.setText(i18n.t("ui.sys.refresh"))
        self.copy_button.setText(i18n.t("ui.sys.copy"))
        self._render()

    def _render(self) -> None:
        self.refresh_button.setEnabled(self._task is None)
        self.copy_button.setEnabled(self.info is not None)
        error = i18n.t("ui.sys.error", error=self._error) if self._error else ""
        if self.info is not None:
            notice = f"<p>{escape(error)}</p>" if error else ""
            self.view.setHtml(notice + sv.sections_html(sv.build_sections(self.info)))
        else:
            self.view.setPlainText(error or i18n.t("ui.sys.loading"))
