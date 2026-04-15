"""
minecraftlauncher.front.window.main.account_page

Page with account info, skin management, log out button.
"""
import logging
import os

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QClipboard
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget, QStyle)

from minecraftlauncher import style, qapp
from minecraftlauncher.front.resources import symbol
from minecraftlauncher.back import account_manager
from minecraftlauncher.auth import LauncherAccount
from minecraftlauncher.functions.error_box import error_box
from minecraftlauncher.constants import CHECKMARK_DELAY

log = logging.getLogger(__name__)

class AccountPage(QWidget):
    """Account info, skin management, logout button"""

    logout_requested = Signal()
    skin_upload = Signal()
    status_update = Signal()

    log = log.getChild("AccountPage")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._account_info:LauncherAccount|None = None
        self._build_ui()

    def build(self):
        pass

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        layout.addStretch()

        self.title = QLabel("<username or email>")
        self.title.setProperty("heading", True)
        layout.addWidget(self.title)

        layout.addStretch()

        # Account info stuff
        info_group = QGroupBox("Account Info")
        info_layout = QGridLayout(info_group)
        info_layout.setSpacing(10)        

        info_layout.addWidget(QLabel("Email:"), 0, 0)
        self.email_label = QLabel("<email>")
        self.email_label.setStyleSheet("font-weight: 600;")
        info_layout.addWidget(self.email_label, 0, 1)

        info_layout.addWidget(QLabel("Username:"), 1, 0)
        self.username_label = QLabel("<username>")
        self.username_label.setStyleSheet("font-weight: 600;")
        info_layout.addWidget(self.username_label, 1, 1)

        info_layout.addWidget(QLabel("UUID:"), 2, 0)
        uuid_row = QHBoxLayout()
        uuid_row.setSpacing(10)
        self.uuid_label = QLabel("<uuid1-uuid2-uuid3-uuid4-uuid5>")
        self.uuid_label.setStyleSheet("font-weight: 600;")
        self.uuid_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        uuid_row.addWidget(self.uuid_label)
        icon = symbol("clipboard")
        self.copy_uuid_button = QPushButton()
        self.copy_uuid_button.setIcon(icon)
        self.copy_uuid_button.setFixedWidth(40)
        self.copy_uuid_button.setFixedHeight(40)
        self.copy_uuid_button.clicked.connect(self._copy_uuid)
        uuid_row.addWidget(self.copy_uuid_button)

        info_layout.addLayout(uuid_row, 2, 1)

        for i in range(info_layout.rowCount()):
            info_layout.setRowMinimumHeight(i, 48)

        layout.addWidget(info_group)

        # TODO: Skin selection/preview

        # Logout
        logout_button = QPushButton("Log out")
        logout_button.setProperty("danger", True)
        logout_button.setFixedWidth(160)
        logout_button.clicked.connect(self._on_logout)
        layout.addWidget(logout_button)

    def set_account_info(self, info:LauncherAccount):
        """Update account info displayed on page"""
        self._account_info = info
        self.email_label.setText(info.msa.email)
        username = info.username
        if not username:
            username = "None"
            self.username_label.setProperty("danger", True)
        self.username_label.setText(username)
        self.uuid_label.setText(info.uuid)
        self.title.setText(username)
    
    def _copy_uuid(self):
        uuid_text = self.uuid_label.text()
        if uuid_text and uuid_text != "<uuid>":
            clipboard = qapp().clipboard()
            if not clipboard:
                error_box("Failed to get clipboard instance to copy to.")
                log.warning("Couldn't get clipboard instance!")
                return
            clipboard.setText(uuid_text, clipboard.Mode.Clipboard)
            self.log.info("Copied '%s' to clipboard." % uuid_text)
            self.copy_uuid_button.setIcon(symbol("clipboard-checked"))

        def reset_button():
            nonlocal self
            self.copy_uuid_button.setIcon(symbol("clipboard"))

        QTimer.singleShot(CHECKMARK_DELAY, reset_button)
    
    def _on_logout(self):
        self.log.debug("User pressed logout button, opening dialog.")
        reply = QMessageBox.question(
            self, "Log out",
            "Are you sure you want to log out?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.logout_requested.emit()
        else:
            self.log.debug("Logout aborted by user.")