import logging

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent

from launcher import get_qapp
from launcher.front.styles import STYLESHEET, get_fonts

log = logging.getLogger(__name__)


class KonamiCode(QObject):
    def __init__(
        self, parent: QObject | None = None, objectName: str | None = None
    ):
        self.qapp = get_qapp()
        self.fonts = get_fonts()
        super().__init__(parent, objectName=objectName)

    konami_code = [
        {Qt.Key.Key_Up},
        {Qt.Key.Key_Up},
        {Qt.Key.Key_Down},
        {Qt.Key.Key_Down},
        {Qt.Key.Key_Left},
        {Qt.Key.Key_Right},
        {Qt.Key.Key_Left},
        {Qt.Key.Key_Right},
        {Qt.Key.Key_B},
        {Qt.Key.Key_A},
        {Qt.Key.Key_Enter, Qt.Key.Key_Return},
    ]
    konami_code_idx = 0
    current_font_is_csans: bool = False
    activated = Signal()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(event, QKeyEvent):
            self.konami_code_event(event)
        return super().eventFilter(watched, event)

    def step_konami_code(self):
        self.konami_code_idx += 1
        if self.konami_code_idx >= len(self.konami_code):
            self.konami_code_idx = 0
            if self.current_font_is_csans:
                log.debug("Setting font back to normal...")
                self.qapp.setFont(self.fonts.main)
                self.qapp.setStyleSheet(STYLESHEET)
                self.current_font_is_csans = False
            else:
                log.debug("Setting font to Comic Sans")
                self.qapp.setFont(self.fonts.csans)
                self.qapp.setStyleSheet(STYLESHEET)
                self.current_font_is_csans = True

    def konami_code_event(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat() or event.count() > 1 or event.isAccepted():
            return
        if event.key() in self.konami_code[self.konami_code_idx]:
            self.step_konami_code()
        else:
            self.konami_code_idx = 0
