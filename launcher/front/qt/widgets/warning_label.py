from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .icon_display import IconDisplayWidget


def _get_warning_color():
    if (
        hsl := (color := QApplication.palette().brightText().color()).toHsl()
    ).lightness() > 200 and hsl.saturation() < 20:
        if QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            return "#D6C64D"
        else:
            return "#A76917"
    return color


class WarningLabel(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QHBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)
        p = self.palette()
        p.setColor(QPalette.ColorRole.WindowText, _get_warning_color())
        self.setPalette(p)
        label = QLabel(text)
        icon = IconDisplayWidget(
            "emblem-warning", size=QFontMetrics(label.font()).capHeight()
        )
        self._layout.addWidget(icon)
        self._layout.addWidget(label)

    def combine(self, other: QWidget):
        new = QWidget()
        new.setContentsMargins(0, 0, 0, 0)
        lo = QVBoxLayout()
        lo.setContentsMargins(0, 0, 0, 0)
        new.setLayout(lo)
        lo.addWidget(other)
        lo.addWidget(self)
        return new

    @Slot(Qt.CheckState)
    def hide_when_checked(self, state: Qt.CheckState):
        """Helper function to connect to a QCheckBox signal"""
        match state:
            case Qt.CheckState.Checked | Qt.CheckState.PartiallyChecked:
                self.setHidden(True)
            case _:
                self.setHidden(False)

    @Slot(Qt.CheckState)
    def hide_when_unchecked(self, state: Qt.CheckState):
        """Helper function to connect to a QCheckBox signal"""
        match state:
            case Qt.CheckState.Unchecked:
                self.setHidden(True)
            case _:
                self.setHidden(False)
