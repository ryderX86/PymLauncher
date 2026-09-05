from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout


class HRow(QWidget):
    def __init__(
        self, parent: QWidget | None = None, flags: Qt.WindowType | None = None
    ):
        if flags:
            super().__init__(parent, flags)
        else:
            super().__init__(parent)
        self._row = QHBoxLayout(self)

    def addWidget(self, widget: QWidget):
        self._row.addWidget(widget)

    def removeWidget(self, widget: QWidget):
        self._row.removeWidget(widget)

    def setAlignment(
        self,
        w: QWidget | Qt.AlignmentFlag,
        align: Qt.AlignmentFlag | None = None,
    ):
        if align and isinstance(w, QWidget):
            self._row.setAlignment(w, align)
        elif isinstance(w, Qt.AlignmentFlag):
            self._row.setAlignment(w)
        else:
            raise TypeError("Unexpected type in args")
