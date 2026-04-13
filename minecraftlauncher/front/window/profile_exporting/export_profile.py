import logging
import time
import json

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QClipboard, QPainter
from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QWidget, QComboBox, QHBoxLayout,
    QCheckBox, QMessageBox, QLineEdit
)
from PySide6.QtSvgWidgets import QSvgWidget

from minecraftlauncher.datatypes.GameProfile import GameProfile
from minecraftlauncher.back import fabric, version_manager
from minecraftlauncher import constants

log = logging.getLogger(__name__)

class ExportProfileDialog(QDialog):
    def __init__(self, prof:GameProfile, parent=None):
        super().__init__(parent)
        self._profile = prof

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        
        fmt_sel = QComboBox()
        fmt_sel.addItem("Vanilla", "zip_fmt")
        self._layout.addWidget(fmt_sel)

        output_row = QHBoxLayout()
        
        dest_path_text = QLineEdit()
        output_row.addWidget(dest_path_text, 1)

        dest_path_browse = QPushButton()
        
        self._layout.addItem(output_row)
