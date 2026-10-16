import base64
import logging
import os
import re
import sys

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QEvent,
    QIODevice,
    QItemSelectionModel,
    QMargins,
    QObject,
    QSize,
    Slot,
)
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap, Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStyle,
)

from launcher import lifecycle
from launcher.front import resources
from launcher.front.icon_helpers import IconName, get_icon
from launcher.front.qt.binding_mixin import BindingMixin
from launcher.functions import truncate

log = logging.getLogger(__name__)
B64_RE = re.compile(r"(data:image/)(png|jpg|jpeg);(base64),([a-zA-Z0-9+/=]+)")

if sys.version_info.minor < 15:

    class MissingType:
        def __bool__(self):
            pass

    MISSING = MissingType()
else:
    # pylint: disable-next=undefined-variable
    MISSING = sentinel("MISSING")  # type: ignore

DATA_TEXT_ROLE = 0x100
QICON_ROLE = 0x101

_icon_size = QSize(96, 96)
_list_icon_size = QSize(64, 64)
_list_grid_size = QSize(72, 72)


def _padded_icon(ico: QIcon | QPixmap) -> QIcon:
    if isinstance(ico, QIcon):
        size = sorted(ico.availableSizes(), key=QSize.width, reverse=True)[0]
        base_pix = ico.pixmap(size)
        pix = base_pix.scaled(
            _icon_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        old_list_pix = base_pix.scaled(
            _list_icon_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    else:
        pix = ico.scaled(
            _icon_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        old_list_pix = ico.scaled(
            _list_icon_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    list_pix = QPixmap(_list_grid_size)
    list_pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(list_pix)
    wh = int((_list_grid_size - _list_icon_size).height() / 2)
    painter.drawPixmap(wh, wh + 2, old_list_pix)
    painter.end()

    new = QIcon()
    new.addPixmap(pix)
    new.addPixmap(list_pix)
    return new


class IconPicker(BindingMixin, QComboBox):
    # instance attributes
    _view: QListWidget
    _default_icon_names: list[str]
    """Don't use .index() on this, use IconPicker()._index_default_icon"""
    _default_icons: dict[str, QIcon]
    _current_custom_icon: QIcon | None
    _no_icon: QIcon
    _frame: QFrame | None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view = QListWidget()
        self._view.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._view.setSelectionBehavior(
            QListWidget.SelectionBehavior.SelectRows
        )
        self._view.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._view.setWrapping(True)
        self._view.setMovement(QListWidget.Movement.Static)
        self.setModel(self._view.model())
        self.setView(self._view)
        # add the picker button to the inside of the listview and then adjust
        # margins accordingly
        self._picker_button = QPushButton(
            get_icon(IconName.OPEN_IMAGE), "Choose image"
        )
        self._picker_button.clicked.connect(self._open_image_picker)
        self._picker_button_view = QHBoxLayout()
        self._picker_button_view.setObjectName("picker_button")
        self._picker_button_view.setContentsMargins(0, 0, 0, 0)
        self._picker_button_view.addWidget(self._picker_button, 0)

        p = QPixmap(_list_grid_size)
        p.fill(Qt.GlobalColor.transparent)
        self._no_icon = QIcon(p)
        none = QListWidgetItem()
        none.setData(DATA_TEXT_ROLE, None)
        none.setData(QICON_ROLE, None)
        none.setIcon(self._no_icon)
        custom = QListWidgetItem()
        custom.setData(DATA_TEXT_ROLE, MISSING)
        custom.setData(QICON_ROLE, MISSING)
        custom.setIcon(self._no_icon)
        self._view.addItem(none)
        self._view.addItem(custom)
        self._default_icon_names = []
        self._frame = None
        self.currentIndexChanged.connect(self._on_item_change)
        self.setMaximumWidth(int(_list_grid_size.width() * 1.55))

    @Slot(int)
    def _on_item_change(self, index: int):
        if index == 1:
            self.setToolTip("Custom Icon")
            return
        self.setToolTip(
            str(self.currentData(DATA_TEXT_ROLE)).replace("_", " ")
        )

    def _pm(self, metric: QStyle.PixelMetric):
        return self.style().pixelMetric(metric)

    def _fix_highlighting(self, index: int):
        model_index = self.model().index(index, 0)
        self._view.selectionModel().setCurrentIndex(
            model_index, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

    def showPopup(self) -> None:
        # the most disgusting hack known to man (but hey, it works!)
        frame = self.findChild(QFrame)
        if frame and frame != self._frame:
            assert frame
            frame.installEventFilter(self)
            self._frame = frame
            layout = frame.findChild(QBoxLayout)
            if layout:
                if not layout.findChild(QHBoxLayout, "picker_button"):
                    spacing = self._pm(
                        QStyle.PixelMetric.PM_LayoutVerticalSpacing
                    )
                    margin = QMargins(
                        self._pm(QStyle.PixelMetric.PM_LayoutLeftMargin),
                        self._pm(QStyle.PixelMetric.PM_LayoutTopMargin),
                        self._pm(QStyle.PixelMetric.PM_LayoutRightMargin),
                        self._pm(QStyle.PixelMetric.PM_LayoutBottomMargin),
                    )
                    layout.setContentsMargins(margin)
                    self._picker_button_view.setParent(None)
                    layout.insertLayout(0, self._picker_button_view, 0)
                    layout.insertSpacing(1, spacing)
                    frame.setMaximumHeight(layout.sizeHint().height())
        self._fix_highlighting(self.currentIndex())
        super().showPopup()

    def eventFilter(self, watched: QObject, event: QEvent, /) -> bool:
        if self._frame:
            if watched == self._frame and event.type() is QEvent.Type.Paint:
                r = self.rect()
                fp = self.mapToGlobal(r.bottomLeft())
                fw = self._frame.width()
                w = self.width()

                fp.setX((fp.x() - (fw // 2)) + (w // 2))
                self._frame.move(fp)
        return super().eventFilter(watched, event)

    @Slot()
    def _open_image_picker(self):
        path, _ = QFileDialog.getOpenFileName(
            self.topLevelWidget(),
            "Choose a file",
            os.path.expanduser("~"),
            "Image Files (*.png, *.jpg, *.jpeg, *.tif, *.tiff, *.bmp, *.gif);;All Files(*)",
        )
        if not path:
            return
        tmp_img = QImage()
        if not tmp_img.load(path):
            log.warning("Invalid icon chosen, aborting...")
            QMessageBox.warning(
                self.topLevelWidget(), "Error", "Could not read image file"
            )
            return
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        tmp_img.save(buffer, "PNG")  # type: ignore
        buffer.close()
        b64 = base64.b64encode(ba.data()).decode("utf-8")
        b64_full = f"data:image/png;base64,{b64}"
        self.setItemData(1, b64_full, DATA_TEXT_ROLE)
        ico = _padded_icon(QPixmap.fromImage(tmp_img))
        self._set_custom_icon_visible(True)
        self.setItemData(1, ico, QICON_ROLE)
        self.setItemIcon(1, ico)
        self.setCurrentIndex(1)
        self.currentIndexChanged.emit(1)

    def _index_default_icon(self, icon: str):
        return self._default_icon_names.index(icon) + 2

    def _set_custom_icon_visible(self, visible: bool):
        self.view().setRowHidden(1, not visible)
        if not visible:
            self.setItemData(1, MISSING, DATA_TEXT_ROLE)
            self.setItemData(1, MISSING, QICON_ROLE)
            self.setItemIcon(1, self._no_icon)

    def view(self) -> QListWidget:
        return self._view

    def bind(self):
        self._default_icons = resources.get_all_default_icons()
        for name, icon in self._default_icons.items():
            ico = _padded_icon(icon)
            item = QListWidgetItem()
            item.setIcon(ico)
            item.setData(DATA_TEXT_ROLE, name)
            item.setData(QICON_ROLE, icon)
            self._view.addItem(item)
            self._default_icon_names.append(name)
        self._view.setViewMode(QListWidget.ViewMode.IconMode)
        self._view.setDragEnabled(False)
        self._reset_size()
        lifecycle.config_updated.connect(self._reset_size)

    @Slot()
    def _reset_size(self):
        self.setIconSize(_list_grid_size)
        self._view.setItemAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setIconSize(_list_grid_size)
        self._view.setFixedWidth(
            (self._view.sizeHintForColumn(0) * 7)
            + self._pm(QStyle.PixelMetric.PM_ScrollBarExtent)
            + self._pm(QStyle.PixelMetric.PM_ScrollBarExtent)
        )
        self._view.setFixedHeight(self._view.sizeHintForRow(0) * 5)
        self._view.setIconSize(_list_grid_size)
        self._view.setUniformItemSizes(True)
        if self._frame and (layout := self._frame.findChild(QBoxLayout)):
            margin = QMargins(
                self._pm(QStyle.PixelMetric.PM_LayoutLeftMargin),
                self._pm(QStyle.PixelMetric.PM_LayoutTopMargin),
                self._pm(QStyle.PixelMetric.PM_LayoutRightMargin),
                self._pm(QStyle.PixelMetric.PM_LayoutBottomMargin),
            )
            layout.setContentsMargins(margin)
            self._frame.setMaximumHeight(layout.sizeHint().height())
            self._frame.setMaximumWidth(layout.sizeHint().width())

    def set_icon(self, icon_data: str | None):
        if icon_data is None or icon_data in self._default_icon_names:
            if icon_data is None:
                self.setCurrentIndex(0)
            else:
                self.setCurrentIndex(self._index_default_icon(icon_data))
            self._set_custom_icon_visible(False)
            return
        elif (match := B64_RE.match(icon_data)) and match[0] == icon_data:
            ico = _padded_icon(resources.profile_icon(icon_data))
            self._set_custom_icon_visible(True)
            self.setItemIcon(1, ico)
            self.setItemData(1, icon_data, DATA_TEXT_ROLE)
            self.setItemData(1, ico, QICON_ROLE)
            self.setCurrentIndex(1)
        else:
            log.warning("Invalid icon: %r", truncate(icon_data, 32))

    def current_b64(self):
        if self.currentIndex() != 1:
            return None
        if (data := self.itemData(1, DATA_TEXT_ROLE)) is not MISSING:
            return data
        return None

    def current_qicon(self):
        if ico := self.itemData(1, QICON_ROLE):
            return ico
        return None

    def for_profile_saving(self) -> str | None:
        if data := self.currentData(DATA_TEXT_ROLE):
            return data
        return None

    def custom_icon_selected(self):
        if self.currentIndex() == 1:
            return True
        return False
