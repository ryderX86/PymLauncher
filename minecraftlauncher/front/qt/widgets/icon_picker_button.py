import logging

from PySide6.QtCore import QEvent, QRect, Qt, Signal, QSize
from PySide6.QtGui import QFocusEvent, QIcon, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QPushButton, QLabel, QWidget, QBoxLayout, QHBoxLayout

from .icon_picker import IconPicker
from minecraftlauncher.datatypes.launch_profile import GameProfile
from minecraftlauncher.front import resources

log = logging.getLogger(__name__)

class IconPickerButton(QPushButton):
    icon_changed = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dropdown = IconPicker(self)
        self.dropdown.change_icon.connect(self._on_change_icon)
        self.dropdown.icon_chosen.connect(self._on_change_icon)
        self.dropdown.hide_me.connect(lambda: self.setChecked(False))
        self.setCheckable(True)
        self._icon_name:str = ""
        self.setIconSize(QSize(32, 32))
        self.dropdown._populate_icons()
        self.__ignore_clicks = False
        self.setFixedSize(QSize(64, 40))
        self._lo = QHBoxLayout(self)
        self._icon = QLabel()
        self._lo.addWidget(self._icon)
        self._label = QLabel()
        self._lo.addStretch()
        self._lo.addWidget(self._label)
        self._label.setPixmap(
            resources.symbol("dropdown").pixmap(QSize(12, 12))
        )
        self._label.setAlignment(Qt.AlignmentFlag.AlignVCenter
                                 | Qt.AlignmentFlag.AlignRight)

    def focusInEvent(self, arg__1:QFocusEvent):
        self.setChecked(False)
        return super().focusInEvent(arg__1)

    def checkStateSet(self):
        if self.isChecked():
            self._label.setPixmap(
                resources.symbol("dropdown-up").pixmap(QSize(12, 12))
            )
            self.dropdown.show()
            self.setDown(True)
        else:
            self._label.setPixmap(
                resources.symbol("dropdown").pixmap(QSize(12, 12))
            )
            self.dropdown.hide()
            self.setDown(False)
        return super().checkStateSet()
    
    def focusOutEvent(self, arg__1:QFocusEvent):
        self.__ignore_clicks = True
        return super().focusOutEvent(arg__1)

    def mousePressEvent(self, e:QMouseEvent):
        if self.__ignore_clicks:
            return
        self.setChecked(not self.isChecked())
    
    def mouseReleaseEvent(self, e:QMouseEvent):
        self.__ignore_clicks = False
        return
    
    def mouseMoveEvent(self, arg__1: QMouseEvent):
        self.__ignore_clicks = False
        return super().mouseMoveEvent(arg__1)
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        max_idx = self.dropdown._view.count() - 1
        pixels = event.pixelDelta().y()
        degrees = event.angleDelta().y()
        cur_row = self.dropdown._view.currentRow()
        custom_visible = not self.dropdown._view.isRowHidden(1)
        error_visible = not self.dropdown._view.isRowHidden(2)
        new_row = cur_row
        if pixels < 0 or degrees < 0:
            if cur_row + 1 > max_idx:
                return
            elif cur_row == 0 and not custom_visible and not error_visible:
                new_row += 3
            elif ((cur_row == 0 and not custom_visible) or
                  (cur_row == 1 and not error_visible)):
                new_row += 2
            else:
                new_row += 1
        elif pixels > 0 or degrees > 0:
            if cur_row - 1 <= 0:
                return
            elif cur_row == 3 and not custom_visible and not error_visible:
                new_row -= 3
            elif ((cur_row - 1 == 1 and not custom_visible) or
                  (cur_row - 1 == 2 and not error_visible)):
                new_row -= 2
            else:
                new_row -= 1
        if new_row != cur_row:
            self.dropdown._view.setCurrentRow(new_row)
        return super().wheelEvent(event)
    
    def revert(self):
        self.dropdown.revert()

    def _on_change_icon(self, name:str, ico:QIcon):
        self._icon_name = name
        wh = int(self.height() / 1.6)
        self._icon.setPixmap(ico.pixmap(QSize(wh, wh)))
        if not self.dropdown.automated:
            self.icon_changed.emit(name)

    def text(self):
        return self._icon_name
    
    def setText(self, text:str|None):
        self.dropdown._set_icon_to(text)

    def profile_selected(self, prof:GameProfile):
        self.dropdown.profile_selected(prof)