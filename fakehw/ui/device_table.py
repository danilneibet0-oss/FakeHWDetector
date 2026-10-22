from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from .. import i18n
from ..models.finding import Level
from . import viewmodel as vm

COLUMNS = ("level", "class", "name", "ids", "score", "notes")
_SEVERITY = {Level.LIKELY_FAKE: 3, Level.SUSPICIOUS: 2, Level.UNVERIFIED: 1, Level.INFO: 0}


class DeviceTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[vm.DeviceRow] = []

    def set_rows(self, rows: list[vm.DeviceRow]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def refresh(self) -> None:
        """Re-read translated texts (language switch)."""
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return i18n.t(f"ui.col.{COLUMNS[section]}")
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = self.rows[index.row()], COLUMNS[index.column()]
        if role == Qt.DisplayRole:
            return {
                "level": f"{vm.level_symbol(row.level)} {vm.level_label(row.level)}",
                "class": vm.class_label(row.device.device_class),
                "name": row.name, "ids": row.ids, "score": f"{row.score:.2f}", "notes": row.note,
            }[col]
        if role == Qt.BackgroundRole:
            return QColor(vm.level_color(row.level))
        if role == Qt.ForegroundRole:
            return QColor("#111111")  # dark text on the light level colours, readable in dark themes too
        if role == Qt.TextAlignmentRole and col == "score":
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    @staticmethod
    def _sort_key(row: vm.DeviceRow, column: str):
        if column == "level":
            return (_SEVERITY[row.level], row.score)  # within a level, triggered low-weight rules come first
        if column == "score":
            return row.score
        return {"class": vm.class_label(row.device.device_class), "name": row.name, "ids": row.ids,
                "notes": row.note}[column].lower()

    def sort(self, column: int, order=Qt.AscendingOrder) -> None:
        name = COLUMNS[column]
        self.beginResetModel()
        # secondary key = original device index keeps the order stable and reproducible
        self.rows.sort(key=lambda r: (self._sort_key(r, name), -r.index if order == Qt.DescendingOrder else r.index),
                       reverse=order == Qt.DescendingOrder)
        self.endResetModel()
