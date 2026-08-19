import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
)

from minecraftlauncher.constants import OS
from minecraftlauncher import get_qapp

match OS:
    case "windows" | "osx":
        _FLAGS = Qt.WindowType.SplashScreen
    case _:
        _FLAGS = Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint

log = logging.getLogger(__name__)


class LoadingBlockerWindow(QDialog):
    __slots__ = ("label",)

    def __init__(self, parent=None, flags=_FLAGS):
        log.debug("Making loading blocker window")
        super().__init__(parent, flags)
        self.setMinimumSize(500, 360)
        self.setMaximumSize(500, 360)
        self.resize(500, 360)
        self._build_layout()
        self.qapp = get_qapp()

    def _build_layout(self):
        _layout = QVBoxLayout(self)

        self.label = QLabel("Loading...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        _layout.addWidget(self.label)
        return

    def set_text(self, text: str = "Loading..."):
        if not text.endswith("..."):
            text = text + "..."
        self.label.setText(text)
        self.qapp.processEvents()

    def open(self) -> None:
        super().open()
        self.qapp.processEvents()

    def show(self) -> None:
        super().show()
        self.qapp.processEvents()

    def hide(self):
        self.set_text()
        super().hide()
