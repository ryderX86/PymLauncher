"""
minecraftlauncher.front.window.main.account_dropdown

QComboBox drop-down menu for switching between and adding new accounts.
"""

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractItemView, QComboBox

from minecraftlauncher.back.account_manager import account_man
from minecraftlauncher.front.resources import symbol
from minecraftlauncher.functions import error_box, suppressable
from minecraftlauncher.offline import offline_man

log = logging.getLogger(__name__)

ADD_ACCOUNT_TEXT = "Add account"
ADD_ACCOUNT_OFFLINE_ERR_TEXT = "Cannot add account while offline!"


class AccountSelect(QComboBox):
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

    def refresh(self):
        """Reload the account list"""
        self._on_index_changed.suppress()

        self.clear()
        active_xuid = account_man.active.xuid if account_man.active else None

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
        self.addItem(symbol("profile-add"), ADD_ACCOUNT_TEXT)

        self._on_index_changed.unsuppress()

    def revert_selection(self):
        """Revert to previous account"""
        self._on_index_changed.suppress()
        if 0 <= self._previous_index < self.count():
            self.setCurrentIndex(self._previous_index)
        self._on_index_changed.unsuppress()

    def setCurrentIndex(self, index: int):
        ci = self.currentIndex()
        if index != ci and ci >= 0:
            self._previous_index = ci
        super().setCurrentIndex(index)

    @suppressable
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
