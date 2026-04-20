"""
minecraftlauncher.front.window.main.account_dropdown

QComboBox drop-down menu for switching between and adding new accounts.
"""
import logging

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QComboBox

from minecraftlauncher.back import account_manager
from minecraftlauncher.front.resources import symbol, icon_from_qimg

log = logging.getLogger(__name__)

ADD_ACCOUNT_TEXT = "Add account"

class AccountSelect(QComboBox):
    account_changed = Signal(str) # gamertag
    add_account_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentTextChanged.connect(self._correct_size)
        self.setSizeAdjustPolicy(self.SizeAdjustPolicy.AdjustToContents)

        self._previous_index = -1
        self.currentIndexChanged.connect(self._on_index_changed)

    def _correct_size(self, t:str):
        current_size = self.size()
        current_size.setWidth(current_size.width() + 8)

    def refresh(self):
        """Reload the account list"""
        self.blockSignals(True)

        self.clear()
        accounts, active_gtg = account_manager.load_accounts()

        active_idx = 0
        for i, acc in enumerate(accounts):
            gamertag = acc.gamertag
            username = acc.username
            display = username if username else gamertag
            face = acc.skin_icon()
            self.addItem(face, display, userData=gamertag)
            if gamertag == active_gtg:
                active_idx = i

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

    def _on_index_changed(self, index:int):
        if index < 0:
            return
        
        self._previous_index = index

        text = self.itemText(index)
        if text == ADD_ACCOUNT_TEXT:
            self.add_account_requested.emit()
            return
        
        gamertag = self.itemData(index)
        if gamertag:
            account_manager.set_active_account(gamertag)
            self.account_changed.emit(gamertag)

    def next_account(self):
        add_idx = self.count() - 1
        idx = self.currentIndex()
        if idx + 1 >= add_idx:
            if self.count() < 2:
                return self.setCurrentIndex(1)
            self.setCurrentIndex(idx - 1)
        
    # stop user scrolling to "add account"
    def wheelEvent(self, e):
        if not e:
            return super().wheelEvent(e)
        add_idx = self.count() - 1
        pixels = e.pixelDelta().y()
        degrees = e.angleDelta().y()
        if pixels < 0 or degrees < 0:
            if (self.currentIndex() + 1) == add_idx:
                return
        return super().wheelEvent(e)