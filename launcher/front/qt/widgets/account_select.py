"""
minecraftlauncher.front.window.main.account_dropdown

QComboBox drop-down menu for switching between and adding new accounts.
"""

import logging

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QAction, QContextMenuEvent, Qt
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QMenu, QMessageBox

from launcher import config
from launcher.back.account_manager import account_man
from launcher.front.icon_helpers import IconName, get_icon
from launcher.front.qt.binding_mixin import BindingMixin
from launcher.front.window.skin_change import SkinChange
from launcher.functions import Suppressable, copy_to_clipboard, error_box
from launcher.offline import offline_man

log = logging.getLogger(__name__)

ADD_ACCOUNT_TEXT = "Add account"
ADD_ACCOUNT_OFFLINE_ERR_TEXT = "Cannot add account while offline!"
COPY_USERNAME_TEXT = "Copy Username"
COPY_UUID_TEXT = "Copy UUID"
COPY_GAMERTAG_TEXT = "Copy Xbox Gamertag"
COPY_XUID_TEXT = "Copy XUID"
CHANGE_SKIN_TEXT = "Change Skin"
LOGOUT_TEXT = "Log out"


def _copy_username():
    if not account_man.active:
        return
    copy_to_clipboard(account_man.active.username)


def _copy_uuid():
    if not account_man.active:
        return
    copy_to_clipboard(account_man.active.uuid)


def _copy_gamertag():
    if not account_man.active:
        return
    copy_to_clipboard(account_man.active.gamertag)


def _copy_xuid():
    if not account_man.active:
        return
    copy_to_clipboard(account_man.active.xuid)


class AccountSelect(BindingMixin, QComboBox):
    add_account_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeAdjustPolicy(self.SizeAdjustPolicy.AdjustToContents)

        self._previous_index = -1
        self._idx_change_signal = self.currentIndexChanged.connect(
            self._on_index_changed
        )
        self.view().setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._copy_username = QAction(COPY_USERNAME_TEXT)
        self._copy_username.triggered.connect(_copy_username)
        self._copy_username.setProperty("debug", True)
        self._copy_uuid = QAction(COPY_UUID_TEXT)
        self._copy_uuid.triggered.connect(_copy_uuid)
        self._copy_uuid.setProperty("debug", True)
        self._copy_gamertag = QAction(COPY_GAMERTAG_TEXT)
        self._copy_gamertag.triggered.connect(_copy_gamertag)
        self._copy_gamertag.setProperty("debug", True)
        self._copy_xuid = QAction(COPY_XUID_TEXT)
        self._copy_xuid.triggered.connect(_copy_xuid)
        self._copy_xuid.setProperty("debug", True)
        self.addActions(
            (
                self._copy_username,
                self._copy_uuid,
                self._copy_gamertag,
                self._copy_xuid,
            )
        )
        self._change_skin = QAction(CHANGE_SKIN_TEXT)
        self._change_skin.triggered.connect(self._change_skin_pressed)
        self.addAction(self._change_skin)
        self.addAction(
            get_icon(IconName.ACCOUNT_REMOVE), "Log out", self._logout_pressed
        )
        offline_man.offline_mode_set.connect(self._change_skin.setDisabled)

    def contextMenuEvent(self, e: QContextMenuEvent, /) -> None:
        e.accept()
        menu = QMenu()
        for action in self.actions():
            if (
                action.property("debug") is True
                and Qt.KeyboardModifier.ShiftModifier not in e.modifiers()
                and not config.always_show_debug_options
            ):
                continue
            menu.addAction(action)
        menu.exec(self.mapToGlobal(e.pos()))

    def _change_skin_pressed(self):
        if offline_man.offline:
            return
        if not account_man.active or not (
            account_man.active and account_man.active.has_profile
        ):
            return
        log.debug("Showing skin change dialog")
        dialog = SkinChange(account_man.active)
        dialog.exec()
        dialog.deleteLater()

    def _logout_pressed(self):
        tlw = self.topLevelWidget()
        assert account_man.active
        pressed_button = QMessageBox.warning(
            tlw,
            "Log out",
            f"Are you sure you want to log out of {account_man.active.username}?",
            buttons=QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            defaultButton=QMessageBox.StandardButton.Cancel,
        )
        if pressed_button == QMessageBox.StandardButton.Yes:
            account_man.signals.logout_requested.emit()
        else:
            return

    def bind(self):
        account_man.signals.account_changed.connect(self._set_profile_actions)
        self._set_profile_actions()

    @Slot()
    def _set_profile_actions(self):
        account_has_profile = (
            account_man.active
            and account_man.active.token
            and account_man.active.token.owns_game
        ) or False
        self._copy_username.setEnabled(account_has_profile)
        self._copy_uuid.setEnabled(account_has_profile)
        self._change_skin.setEnabled(account_has_profile)
        if account_has_profile:
            self._copy_username.setText(COPY_USERNAME_TEXT)
            self._copy_uuid.setText(COPY_UUID_TEXT)
            self._change_skin.setText(CHANGE_SKIN_TEXT)
        else:
            self._copy_username.setText("No username")
            self._copy_uuid.setText("No UUID")
            self._change_skin.setText("Cannot change skin")

    def refresh(self):
        """Reload the account list"""
        with self._on_index_changed.suppressed():
            self.clear()
            active_xuid = (
                account_man.active.xuid if account_man.active else None
            )

            for i, acc in enumerate(account_man):
                gamertag = acc.gamertag
                xuid = acc.xuid
                username = acc.username
                display = username if username else f"No profile ({gamertag})"
                icon = acc.skin_icon()
                self.addItem(icon, display, userData=xuid)
                if xuid and xuid == active_xuid:
                    self._previous_index = self.currentIndex()
                    self.setCurrentIndex(i)

            self.insertSeparator(self.count())
            self.addItem(get_icon(IconName.ACCOUNT_ADD), ADD_ACCOUNT_TEXT)

    def revert_selection(self):
        """Revert to previous account"""
        with self._on_index_changed.suppressed():
            if 0 <= self._previous_index < self.count():
                self.setCurrentIndex(self._previous_index)

    def setCurrentIndex(self, index: int):
        ci = self.currentIndex()
        if index != ci and ci >= 0:
            self._previous_index = ci
        super().setCurrentIndex(index)

    @Suppressable
    def _on_index_changed(self, index: int):
        if index < 0:
            return

        if index == (self.count() - 1):
            if offline_man.offline:
                error_box(ADD_ACCOUNT_OFFLINE_ERR_TEXT)
                return
            self.add_account_requested.emit()
            return

        xuid = self.itemData(index)
        if xuid:
            account_man.set_active(xuid, ignore_refreshes=True)
        else:
            log.warning("No XUID for selected account!")
            self.revert_selection()

    def next_account(self):
        add_idx = self.count() - 2
        idx = self.currentIndex()
        if idx + 1 >= add_idx:
            if self.count() < 2:
                return self.setCurrentIndex(1)
            self.setCurrentIndex(idx - 1)
        return None

    # stop user scrolling to "add account"
    def wheelEvent(self, e):
        if not e:
            return super().wheelEvent(e)
        pixels = e.pixelDelta().y()
        degrees = e.angleDelta().y()
        if pixels < 0 or degrees < 0:
            if not self.itemData(self.currentIndex() + 1):
                return None
        return super().wheelEvent(e)
