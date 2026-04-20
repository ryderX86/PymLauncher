from pathlib import Path
import logging
import base64

from PySide6.QtCore import Qt, Signal, QSize, QByteArray, QBuffer
from PySide6.QtGui import (
    QFocusEvent, QIcon, QPixmap, QImage, QScreen, QGuiApplication
)
from PySide6.QtWidgets import (
    QWidget, QListWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QListWidgetItem, QFileDialog, QApplication
)

from minecraftlauncher.datatypes.launch_profile import GameProfile
from minecraftlauncher.front import resources
from minecraftlauncher.functions.error_box import error_box

log = logging.getLogger(__name__)

class IconPicker(QWidget):
    _DEFAULT_ICO_SIZE = 64
    _DEFAULT_COLUMNS = 8
    _DEFAULT_ROWS = 6
    _WIN_TYPE = Qt.WindowType.Popup
    _MODALITY = Qt.WindowModality.ApplicationModal
    blank_icon = QIcon()

    icon_chosen = Signal(str, QIcon)
    icon_automated = Signal(bool)
    add_icon = Signal(int, QIcon)
    change_icon = Signal(str, QIcon)
    clear_icons = Signal()
    lost_focus = Signal()
    hide_me = Signal()
    def __init__(self, parent:QWidget|None=None):
        super().__init__(parent)
        self._parent = parent
        self.setWindowFlags(self._WIN_TYPE)
        self.hide()
        self._ico_size:int|None = None
        self._size_hint = QSize(self.iconsize, self.iconsize)
        self._icon_indexes = []
        self._build_ui()
        self.loaded = False
        self.setWindowModality(self._MODALITY)
        self.icon_automated.connect(self._set_automated)
        self._automated_status = False
        self._previous:QListWidgetItem|None = None
        self._current_profile:GameProfile|None = None
        self._view.setIconSize(
            QSize(self._DEFAULT_ICO_SIZE, self._DEFAULT_ICO_SIZE)
        )
        self._view.setUniformItemSizes(True)
        cols = self._DEFAULT_COLUMNS
        rows = self._DEFAULT_ROWS
        self.setFixedWidth(((self._DEFAULT_ICO_SIZE + 2) * 8) + (cols * 3))
        self.setFixedHeight(((self._DEFAULT_ICO_SIZE + 2) * 6) - (rows // 2))

    def _set_automated(self, auto:bool):
        self._automated_status = auto

    @property
    def automated(self):
        return self._automated_status

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._add_button = QPushButton(resources.symbol("file-image"),
                                       "Custom Icon")
        self._add_button.clicked.connect(self._add_custom_icon)
        self._layout.addWidget(self._add_button)

        self._view = QListWidget()
        self._view.setViewMode(QListWidget.ViewMode.IconMode)
        self._view.currentItemChanged.connect(self._emit_item_change)
        self._view.setContextMenuPolicy(
            Qt.ContextMenuPolicy.PreventContextMenu
        )
        self._view.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._view.setDragEnabled(False)
        self._layout.addWidget(self._view, 1)

    @property
    def iconsize(self):
        if self._ico_size:
            return self._ico_size
        return self._DEFAULT_ICO_SIZE
    
    @property
    def sizehint(self):
        return self._size_hint
    
    @iconsize.setter
    def iconsize(self, new_val:int|None):
        self._ico_size = new_val
        self._size_hint.setHeight(self.iconsize)
        self._size_hint.setWidth(self.iconsize)

    def focusOutEvent(self, event: QFocusEvent):
        self.lost_focus.emit()
        return super().focusOutEvent(event)

    def _populate_icons(self):
        self.icon_automated.emit(True)
        idx = self._view.currentRow()
        self._view.clear()
        self._icon_indexes.clear()
        i = QListWidgetItem()
        i.setSizeHint(self.sizehint)
        i.setData(256, "")
        i.setIcon(self.blank_icon)
        self._view.addItem(i)
        self._icon_indexes.extend([None, None, None])
        i = QListWidgetItem()
        i.setSizeHint(self.sizehint)
        i.setData(256, "<CUSTOM>")
        i.setIcon(self.blank_icon)
        self._view.addItem(i)
        self._view.setRowHidden(1, True)
        i = QListWidgetItem()
        i.setSizeHint(self.sizehint)
        i.setData(256, "<UNKNOWN>")
        i.setIcon(resources.get_unknown_icon())
        self._view.addItem(i)
        self._view.setRowHidden(2, True)
        for name, icon in resources.get_all_default_icons().items():
            i = QListWidgetItem()
            i.setData(256, name)
            i.setIcon(icon)
            i.setSizeHint(self.sizehint)
            self._view.addItem(i)
            self._icon_indexes.append(name)
            self.add_icon.emit(self._icon_indexes.index(name), icon)
        self.blockSignals(True)
        if idx > 0:
            self._view.setCurrentRow(idx)
        self.blockSignals(False)
        self.loaded = True
        self.icon_automated.emit(False)

    def profile_selected(self, prof:GameProfile):
        self._current_profile = prof
        if not self.loaded:
            return
        self.icon_automated.emit(True)
        if not prof.icon:
            self._previous = self._view.item(0)
            self._view.item(1).setData(256, "<CUSTOM>")
            self._view.setRowHidden(1, True)
            self._view.setCurrentRow(0)
            self._view.setRowHidden(2, True)
            self._view.item(1).setIcon(self.blank_icon)
            self._view.item(2).setIcon(self.blank_icon)
            self.change_icon.emit("", self.blank_icon)
            self.icon_automated.emit(False)
            return
        if not prof.has_custom_icon():
            self._view.item(1).setData(256, "<CUSTOM>")
            self._view.setRowHidden(1, True)
            self._view.item(1).setIcon(self.blank_icon)
        ico = prof.icon
        if ico and ico in self._icon_indexes:
            i = self._icon_indexes.index(ico)
            self._previous = self._view.item(i)
            self._view.setCurrentRow(i)
            self._view.setRowHidden(2, True)
        elif prof.has_custom_icon():
            self._previous = self._view.item(1)
            self._view.setRowHidden(1, False)
            self._view.setCurrentRow(1)
            self._view.item(1).setIcon(resources.profile_icon(prof.icon))
            self.change_icon.emit("<CUSTOM>", resources.profile_icon(prof.icon))
            self._view.setRowHidden(2, True)
        else:
            self._previous = self._view.item(2)
            self._view.setRowHidden(2, False)
            self._view.setCurrentRow(2)
        self.icon_automated.emit(False)

    def revert(self):
        if self._current_profile:
            if self._view.item(1).data(256) != "<CUSTOM>":
                if self._current_profile.has_custom_icon():
                    assert self._current_profile.icon
                    ico = resources.profile_icon(self._current_profile.icon)
                    self._view.item(1).setData(256, "<CUSTOM>")
                    self._view.item(1).setIcon(ico)
                    self._view.setCurrentRow(1)
                    self.change_icon.emit("<CUSTOM>", ico)
        if not self._previous:
            return
        self._view.setCurrentItem(self._previous)

    def _emit_item_change(self, item:QListWidgetItem):
        ico = item.icon()
        name = item.data(256)
        self.icon_chosen.emit(name, ico)
        if self.isVisible():
            self.hide_me.emit()

    def _set_icon_to(self, name:str|None):
        if not name:
            name = ""
        current_name = None
        match_found = False
        idx = 0
        if not name.startswith("data:image/"):
            for i in range(self._view.count()):
                current_name = self._view.item(i).data(256)
                idx += 1
                if current_name == name:
                    match_found = True
                    break
        else:
            match_found = True
            idx = 1
        if match_found:
            self._view.setCurrentRow(idx)
            return
        else:
            if (current_name and current_name.startswith("data:image/")
                or current_name == "<CUSTOM>"):
                self._view.setRowHidden(1, False)
                self._view.setCurrentRow(1)
            else:
                self._view.setRowHidden(2, False)
                self._view.setCurrentRow(2)
    
    def show(self):
        if self._parent and self._parent.parent():
            try:
                screen = QGuiApplication.screenAt(
                    self._parent.parent().mapToGlobal( # type: ignore
                        self._parent.pos()
                    )
                )
            except Exception as err:
                log.error("Error raised trying to get screen from "
                          "QGuiApplication, silently failing instead.")
                screen = None
            if not screen:
                screen = self.screen()
                log.warning("Couldn't get screen through QGuiApplication")
            geo = self._parent.parent().mapToGlobal(  # type: ignore
                self._parent.pos()
            )
            x = geo.x() + int(self._parent.width() / 2) - int(self.width() / 2)
            y = geo.y() + self._parent.height()
            outer_x = x + self.width()
            screen_geo = screen.geometry()
            if x < screen_geo.x():
                x = screen_geo.x()
            elif outer_x > screen_geo.width() + screen_geo.x():
                x -= outer_x - screen_geo.width() - screen_geo.x()
            if y < 0:
                y = 0
            self.move(int(x), y)
        super().show()
        self.setFocus()
        return
    
    def hide(self):
        return super().hide()
    
    def _add_custom_icon(self):
        def errout(fp:str):
            error_box("Failed to read image at \"%s\"" % fp)
            return
        if not self._current_profile:
            return
        idx = self._view.item(1)
        file_filter = "Image Files (*.png *.jpeg *.jpg *.bmp "\
                      "*.gif *.pbm *.pgm *.ppm *.xbm *.xpm)"
        
        dialog = QFileDialog()
        dialog.setNameFilter(file_filter)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return
        fp = dialog.selectedFiles()[0]

        fp_path = Path(fp)
        if not fp_path.exists():
            log.warning("File '%s' doesn't exist?" % fp)
            error_box("Failed to load image at \"%s\"" % fp)
            return
        
        pix = QPixmap(128, 128)
        if pix.isNull() or not pix.load(fp):
            return errout(fp)
        img_bytes = QByteArray()
        buffer = QBuffer(img_bytes)
        try:
            pix.save(buffer, "png")
        except Exception as err:
            log.error("Failed reading image into QBuffer:", exc_info=err)
            errout(fp)
        img_b64 = base64.b64encode(img_bytes.data()).decode("utf-8")
        ico = resources.icon_highlight_fix(QIcon(pix), pix)
        idx.setIcon(ico)
        idx.setData(256, img_b64)
        self._view.setCurrentRow(1)
        self.change_icon.emit(f"data:image/png;base64,{img_b64}", ico)
        return