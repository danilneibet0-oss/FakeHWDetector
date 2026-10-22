from PySide6.QtWidgets import QTextBrowser

from .. import i18n
from . import viewmodel as vm


class DetailPanel(QTextBrowser):
    """Shows all IDs, triggered rules and recommendations of the selected device."""

    def __init__(self) -> None:
        super().__init__()
        self.setOpenLinks(False)
        self._row: vm.DeviceRow | None = None
        self.show_row(None)

    def show_row(self, row: vm.DeviceRow | None) -> None:
        self._row = row
        if row is None:
            self.setPlainText(i18n.t("ui.detail.empty"))
        else:
            self.setHtml(vm.detail_html(row))

    def retranslate(self) -> None:
        self.show_row(self._row)
