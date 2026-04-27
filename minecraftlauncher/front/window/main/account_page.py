"""
minecraftlauncher.front.window.main.account_page

Page with account info, skin management, log out button.
"""

import logging

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from minecraftlauncher.front.resources import symbol
from minecraftlauncher.auth import LauncherAccount
from minecraftlauncher.functions.error_box import error_box
from minecraftlauncher.functions import copy_to_clipboard, clipboard_present
from minecraftlauncher.constants import CHECKMARK_DELAY
from minecraftlauncher.front.window.skin_change import SkinChange

log = logging.getLogger(__name__)


class AccountPage(QWidget):
    """Account info, skin management, logout button"""

    logout_requested = Signal()
    skin_upload = Signal()
    status_update = Signal()

    log = log.getChild("AccountPage")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._account_info: LauncherAccount | None = None
        self._build_ui()
        self.dialog: SkinChange

    def build(self):
        pass

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        title = QLabel("Account")
        title.setProperty("heading", True)
        layout.addWidget(title)

        self.title = QLabel("<username or gamertag>")
        self.title.setProperty("h2", True)
        # layout.addWidget(self.title)

        # Account info stuff
        info_group = QGroupBox("Details")
        info_layout = QGridLayout(info_group)
        info_layout.setSpacing(0)

        info_layout.addWidget(QLabel("Username:"), 0, 0)
        self.username_label = QLabel("<username>")
        self.username_label.setStyleSheet("font-weight: 600;")
        self.username_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        info_layout.addWidget(self.username_label, 0, 1)

        info_layout.addWidget(QLabel("UUID:"), 1, 0)
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
        self.copy_uuid_button.setEnabled(clipboard_present)
        uuid_row.addWidget(self.copy_uuid_button)

        info_layout.addLayout(uuid_row, 1, 1)

        info_layout.addWidget(QLabel("Xbox Gamertag:"), 2, 0)
        self.gtg_label = QLabel("<gamertag>")
        self.gtg_label.setStyleSheet("font-weight: 600;")
        self.gtg_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        info_layout.addWidget(self.gtg_label, 2, 1)

        info_layout.addWidget(QLabel("XUID:"), 3, 0)
        self.xuid_label = QLabel("<xuid>")
        self.xuid_label.setStyleSheet("font-weight: 600;")
        self.xuid_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        info_layout.addWidget(self.xuid_label, 3, 1)

        for i in range(info_layout.rowCount()):
            info_layout.setRowMinimumHeight(i, 48)

        layout.addWidget(info_group)
        layout.addStretch()

        # TODO: Skin selection/preview

        # Management area
        manage_w = QWidget()
        manage = QHBoxLayout(manage_w)
        manage.setContentsMargins(0, 0, 0, 0)

        self.change_skin_button = QPushButton("Change Skin")
        self.change_skin_button.setMaximumWidth(250)
        self.change_skin_button.clicked.connect(self._change_skin)
        manage.addWidget(self.change_skin_button, 0)

        manage.addStretch()

        # mg_accounts_button = QPushButton("Manage accounts")
        # mg_accounts_button.setFixedWidth(160)
        # # mg_accounts_button.clicked.connect(self._manage_accounts)
        # mg_accounts_button.setDisabled(True)
        # manage.addWidget(mg_accounts_button)

        logout_button = QPushButton("Log out")
        logout_button.setProperty("danger", True)
        logout_button.setFixedWidth(160)
        logout_button.clicked.connect(self._on_logout)
        manage.addWidget(logout_button)

        layout.addWidget(manage_w)

    def set_account_info(self, info: LauncherAccount):
        """Update account info displayed on page"""
        self._account_info = info
        self.gtg_label.setText(info.gamertag)
        username = info.username
        if not username and not info.demo_mode:
            log.warning("Player has no username!")
            username = "[no username]"
            self.username_label.setProperty("danger", True)
        elif info.demo_mode:
            username = "[demo user]"
        self.username_label.setText(username)
        self.uuid_label.setText(info.uuid)
        self.title.setText(username)
        self.xuid_label.setText(info.xuid)
        self.change_skin_button.setDisabled(info.demo_mode)

    def _copy_uuid(self):
        uuid_text = self.uuid_label.text()
        if uuid_text and uuid_text != "<uuid>":
            if not clipboard_present:
                error_box("Failed to get clipboard instance to copy to.")
                log.warning("Couldn't get clipboard instance!")
                return
            copy_to_clipboard(uuid_text)
            self.log.info("Copied '%s' to clipboard.", uuid_text)
            self.copy_uuid_button.setIcon(symbol("clipboard-checked"))

        def reset_button():
            nonlocal self
            self.copy_uuid_button.setIcon(symbol("clipboard"))

        QTimer.singleShot(CHECKMARK_DELAY, reset_button)

    def _on_logout(self):
        self.log.debug("User pressed logout button, opening dialog.")
        reply = QMessageBox.question(
            self,
            "Log out",
            "Are you sure you want to log out?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.logout_requested.emit()
        else:
            self.log.debug("Logout aborted by user.")

    def _change_skin(self):
        log.debug("Showing skin change dialog")
        if self._account_info:
            self.dialog = SkinChange(self._account_info)
            self.dialog.skin_changed.connect(self.skin_upload.emit)
            self.dialog.exec()
            self.dialog.deleteLater()
