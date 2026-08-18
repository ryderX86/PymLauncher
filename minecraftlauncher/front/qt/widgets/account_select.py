"""
minecraftlauncher.front.window.main.account_dropdown

QComboBox drop-down menu for switching between and adding new accounts.
"""

import logging

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QComboBox, QAbstractItemView

from minecraftlauncher.back.account_manager import account_man
from minecraftlauncher.front.resources import symbol
from minecraftlauncher.functions import error_box
from minecraftlauncher.offline import offline_man

log = logging.getLogger(__name__)

ADD_ACCOUNT_TEXT = "Add account"
ADD_ACCOUNT_OFFLINE_ERR_TEXT = "Cannot add account while offline!"


class AccountSelect(QComboBox):
    account_changed = Signal(str)  # XUID
    add_account_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentTextChanged.connect(self._correct_size)
        self.setSizeAdjustPolicy(self.SizeAdjustPolicy.AdjustToContents)

        self._previous_index = -1
        self.currentIndexChanged.connect(self._on_index_changed)
        self.view().setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )

    def _correct_size(self, t: str):
        current_size = self.size()
        current_size.setWidth(current_size.width() + 8)

    def refresh(self):
        """Reload the account list"""
        self.blockSignals(True)

        self.clear()
        accounts = account_man.list()
        active_xuid = account_man.active.xuid if account_man.active else None

        active_idx = 0
        for i, acc in enumerate(accounts):
            gamertag = acc.gamertag
            xuid = acc.xuid
            username = acc.username
            display = username if username else f"No profile ({gamertag})"
            icon = acc.skin_icon()
            self.addItem(icon, display, userData=xuid)
            if xuid == active_xuid:
                active_idx = i

        self.insertSeparator(self.count())
        self.addItem(symbol("profile-add"), ADD_ACCOUNT_TEXT)

        if accounts:
            self.setCurrentIndex(active_idx)
            self._previous_index = active_idx
        else:
            self.setCurrentIndex(self.count() - 1)
            self._previous_index = self.count() - 1

        self.blockSignals(False)

    def revert_selection(self):
        """Revert to previous account"""
        self.blockSignals(True)
        if 0 <= self._previous_index < self.count():
            self.setCurrentIndex(self._previous_index)
        self.blockSignals(False)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        return None

    def setCurrentIndex(self, index: int):
        ci = self.currentIndex()
        if index != ci:
            self._previous_index = ci
        return super().setCurrentIndex(index)

    def _on_index_changed(self, index: int):
        if index < 0:
            return

        text = self.itemText(index)
        if text == ADD_ACCOUNT_TEXT:
            if offline_man.offline:
                error_box(ADD_ACCOUNT_OFFLINE_ERR_TEXT)
                return
            self.add_account_requested.emit()
            return

        xuid = self.itemData(index)
        if xuid:
            self.account_changed.emit(xuid)
        else:
            log.warning("No XUID for selected account!")

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
