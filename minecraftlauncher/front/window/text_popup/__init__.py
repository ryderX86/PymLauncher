"""
minecraftlauncher.front.window.text_popup

Module containing a class with a window to show texts.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
)

from minecraftlauncher.functions import copy_to_clipboard, clipboard_present
from minecraftlauncher.front.styles import get_fonts

log = logging.getLogger(__name__)


class TextPopup(QDialog):
    def __init__(
        self,
        text: str,
        text_title: str | None = None,
        window_title: str | None = None,
        parent=None,
    ):
        """
        Text Pop-up
        """
        super().__init__(parent)
        self.fonts = get_fonts()
        if window_title:
            self.setWindowTitle(window_title)
        self.setMinimumSize(600, 500)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
        )
        self._text = text
        self._title = text_title
        self._build_ui()
        # TODO: find out why this won't bring it to the forefront
        self.setWindowState(
            (self.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )
        self.show()
        self.raise_()
        self.activateWindow()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(32, 32, 32, 32)
        self._layout.setSpacing(16)

        if self._title:
            title = QLabel(self._title)
            title.setStyleSheet("font-size: 16px; font-weight: 700;")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.addWidget(title)

        self._text_display = QPlainTextEdit()
        self._text_display.setPlainText(self._text)
        self._text_display.setReadOnly(True)
        self._text_display.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text_display.setStyleSheet(
            self._text_display.styleSheet() + "font-weight: 600; "
            "font-size: 12;"
        )
        self._text_display.setFont(self.fonts.terminal)
        pixel_width = len(max(self._text.splitlines())) * 12
        size = self.size()
        size.setWidth(pixel_width + 96)
        size.setHeight((min(len(self._text.splitlines()), 48) * 12) + 256)
        self.resize(size)
        self._layout.addWidget(self._text_display)

        buttons_parent = QFrame()
        buttons_layout = QHBoxLayout(buttons_parent)

        clipboard_button = QPushButton()
        clipboard_button.setText("Copy to Clipboard")
        clipboard_button.clicked.connect(self._copy_to_clipboard)
        if not self._text:
            clipboard_button.setDisabled(True)
            clipboard_button.setText("Nothing to copy...")
            clipboard_button.setStyleSheet(
                clipboard_button.styleSheet() + " font: italic;"
            )
        elif not clipboard_present:
            log.warning("No clipboard found")
            clipboard_button.setDisabled(True)
        buttons_layout.addWidget(clipboard_button)

        self._layout.addWidget(buttons_parent)

        close_button = QPushButton()
        close_button.setText("Close")
        close_button.clicked.connect(self.close)
        close_button.setMaximumWidth(200)
        self._layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignCenter)

    def _copy_to_clipboard(self):
        copy_to_clipboard(self._text)
        log.debug("Copied text to clipboard.")
        return
