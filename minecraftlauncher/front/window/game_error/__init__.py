"""
minecraftlauncher.front.window.game_error

Module containing a class with a window to show game errors/logs.
"""

from pathlib import Path
import logging
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QApplication,
)

from minecraftlauncher.functions import copy_to_clipboard, clipboard_present
from minecraftlauncher.front.styles import get_fonts
from minecraftlauncher import constants

log = logging.getLogger(__name__)


class ErrorDisplay(QDialog):
    def __init__(
        self,
        parent=None,
        exit_code: str | None = None,
        logs: str | None = None,
        log_path: str | Path | None = None,
    ):
        """
        Game crash display.

        No args required, but are preferred.

        `logs` should be a str of the crash report, and `log_path` should be
        the location of the report (if applicable).
        """
        self.fonts = get_fonts()
        super().__init__(parent)
        self.setWindowTitle("Minecraft Error")
        self.resize(600, 500)
        self.setMinimumSize(500, 500)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
        )
        self._log = logs if logs else "<No game logs are available>"
        self._exit_code = exit_code if exit_code else "<unknown>"
        if isinstance(log_path, Path):
            log_path = str(log_path)
        self._log_file = log_path
        self._truncate_logs()
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

        title = QLabel("The game crashed!")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(title)

        exit_code = QLabel(f"Exit code: {self._exit_code}")
        exit_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(exit_code)

        self._log_display = QPlainTextEdit()
        self._log_display.setPlainText(self._log)
        self._log_display.setReadOnly(True)
        self._log_display.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._log_display.setStyleSheet(
            self._log_display.styleSheet() + "font-weight: 600; "
            "font-size: 12;"
        )
        self._log_display.setFont(self.fonts.terminal)
        self._layout.addWidget(self._log_display)

        buttons_parent = QFrame()
        buttons_layout = QHBoxLayout(buttons_parent)

        clipboard_button = QPushButton()
        clipboard_button.setText("Copy to Clipboard")
        clipboard_button.clicked.connect(self._copy_logs_to_clipboard)
        if not self._log:
            clipboard_button.setDisabled(True)
            clipboard_button.setText("No logs to copy...")
            clipboard_button.setStyleSheet(
                clipboard_button.styleSheet() + " font: italic;"
            )
        elif not clipboard_present:
            log.warning("No clipboard found")
            clipboard_button.setDisabled(True)
        buttons_layout.addWidget(clipboard_button)

        open_log_button = QPushButton()
        open_log_button.setText("Open Log File")
        open_log_button.clicked.connect(self._open_log_file)
        if (not self._log_file) or (not os.path.isfile(self._log_file)):
            open_log_button.setDisabled(True)
            open_log_button.setText("No file...")
            open_log_button.setStyleSheet(
                open_log_button.styleSheet() + " font: italic;"
            )
        buttons_layout.addWidget(open_log_button)

        self._layout.addWidget(buttons_parent)

        close_button = QPushButton()
        close_button.setText("Close")
        close_button.setProperty("danger", True)
        close_button.clicked.connect(self.close)
        close_button.setMaximumWidth(200)
        self._layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignCenter)

    def _truncate_logs(self):
        if not self._log:
            return
        CRASH_START = "---- Minecraft Crash Report ----"
        CRASH_END = "#@!@# Game crashed! Crash report saved to: #@!@# "
        crash_start_index = -1
        crash_end_index = -1
        logs = self._log.splitlines()
        for line in logs:
            if CRASH_START in line:
                crash_start_index = logs.index(line)
            elif CRASH_END in line:
                crash_end_index = logs.index(line)
        if crash_start_index < 0 or crash_end_index < 0:
            return
        crash_log_fp = logs[crash_end_index][len(CRASH_END) :].strip()

        if os.path.isfile(crash_log_fp) and (
            (not self._log_file) or not os.path.isdir(self._log_file)
        ):
            self._log_file = crash_log_fp

        self._log = "\n".join(logs[crash_start_index : crash_end_index + 1])

    def _copy_logs_to_clipboard(self):
        copy_to_clipboard(self._log)
        log.debug("Copied game crash log to clipboard.")
        return

    def _open_log_file(self):
        if (not self._log_file) or (not os.path.isfile(self._log_file)):
            log.warning("No log file! Function shouldn't have been called")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._log_file))
        log.debug("Opened log file with PC default editor")
        return
