"""
minecraftlauncher.front.window.game_error

Module containing a class with a window to show game errors/logs.

Needs some clean-up since it's moved from getting logs from the home page
to getting them from the file path
"""

__lazy_modules__ = [
    "launcher.front.styles",
    "launcher.front.qt.widgets",
]

from pathlib import Path
import logging
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from launcher.front.qt.widgets import CopyToClipboardButton

# lazy
from launcher.front.styles import get_fonts

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
        self.setWindowTitle("Minecraft Crash Report")
        self.resize(650, 500)
        self.setMinimumSize(500, 500)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
        )
        if logs:
            self._log = logs
        elif log_path:
            file_logs = []
            try:
                with open(log_path, "r") as file:
                    while True:
                        ln = file.readline(7500)
                        if ln:
                            # iterates so it'll work for both win32/everything else
                            file_logs.append(ln.rstrip("\r\n"))
                            if len(file_logs) > 1024:
                                file_logs.pop(0)
                        else:
                            break
            except Exception as err:
                log.error(
                    "Failed to read text from %r:",
                    log_path,
                    exc_info=err,
                )
                self._log = f'<failed to read file at "{log_path}>"'
            else:
                if file_logs:
                    self._log = "\n".join(file_logs)
        else:
            self._log = "<No logs could be found>"
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
        self.clipboard = QApplication.clipboard()
        self._layout = QVBoxLayout(self)

        title = QLabel("<h1>The game crashed!</h1>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(title)

        exit_code_row = QHBoxLayout()
        exit_code_row.addStretch(1)
        exit_code = QLabel(f"Exit code: {self._exit_code or "<unspecified>"}")
        exit_code_row.addWidget(exit_code, stretch=0)
        copy_code_button = CopyToClipboardButton(
            self,
            lambda: getattr(self, "_exit_code", "<unknown>"),
        )
        exit_code_row.addWidget(copy_code_button, stretch=0)
        exit_code_row.addStretch(1)
        self._layout.addLayout(exit_code_row)

        self._log_display = QPlainTextEdit()
        self._log_display.setPlainText(self._log)
        self._log_display.setReadOnly(True)
        self._log_display.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        f = QFont(self.fonts.terminal)
        f.setPointSize(10)
        f.setWeight(QFont.Weight.Normal)
        self._log_display.setFont(f)
        self._layout.addWidget(self._log_display)

        buttons_parent = QFrame()
        buttons_layout = QHBoxLayout(buttons_parent)

        self.clipboard_button = CopyToClipboardButton(
            self, self._copy_logs_to_clipboard, is_icon_button=False
        )
        if not self._log:
            self.clipboard_button.setDisabled(True)
            self.clipboard_button.setText("No logs to copy...")
            f = QFont(self.clipboard_button.font())
            f.setItalic(True)
            self.clipboard_button.setFont(f)
        elif not self.clipboard:
            log.warning("No clipboard found")
            self.clipboard_button.setDisabled(True)
        buttons_layout.addWidget(self.clipboard_button)

        open_log_button = QPushButton()
        open_log_button.setText("Open Log File")
        open_log_button.clicked.connect(self._open_log_file)
        if (not self._log_file) or (not os.path.isfile(self._log_file)):
            open_log_button.setDisabled(True)
            open_log_button.setText("No file...")
            f = QFont(open_log_button.font())
            f.setItalic(True)
            open_log_button.setFont(f)
        buttons_layout.addWidget(open_log_button)

        self._layout.addWidget(buttons_parent)

        box = QDialogButtonBox(
            standardButtons=QDialogButtonBox.StandardButton.Close
        )
        box.button(QDialogButtonBox.StandardButton.Close).clicked.connect(
            self.close
        )
        self._layout.addWidget(box)

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
        if self._log:
            self.clipboard.setText(self._log)
            log.debug("Copied game crash log to clipboard.")
        return

    def _open_log_file(self):
        if (not self._log_file) or (not os.path.isfile(self._log_file)):
            log.warning("No log file! Function shouldn't have been called")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._log_file))
        log.debug("Opened log file with PC default editor")
        return
