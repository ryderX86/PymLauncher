from typing import assert_never
from copy import copy

from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import (
    QPixmap,
    QIcon,
    QIconEngine,
    QImage,
    QPalette,
    QPainter,
)

from launcher import lifecycle


def _use_dark_icon():
    match lifecycle.qapp.styleHints().colorScheme():
        case Qt.ColorScheme.Dark:
            return False
        case Qt.ColorScheme.Light:
            return True
        case _ if (
            lifecycle.qapp.palette()
            .color(QPalette.ColorRole.Window)
            .lightness()
            < 128
        ):
            return False
        case _:
            return True


class IconEngine(QIconEngine):
    _icon_normal_light: QPixmap
    _icon_normal_dark: QPixmap
    _icon_disabled_light: QPixmap
    _icon_disabled_dark: QPixmap
    _icon_active_light: QPixmap
    _icon_active_dark: QPixmap
    _icon_selected_light: QPixmap
    _icon_selected_dark: QPixmap

    def __init__(self, other: QIconEngine | IconEngine | None = None):
        if other:
            super().__init__(other)
        else:
            super().__init__()

    def addPixmap(
        self,
        pixmap: QPixmap | QImage,
        mode: QIcon.Mode,
        state: QIcon.State,
        dark: bool = True,
    ) -> None:
        super().addPixmap(pixmap, mode, state)
        if isinstance(pixmap, QImage):
            p = QPixmap.fromImage(pixmap)
        else:
            p = pixmap
        match mode, dark:
            case QIcon.Mode.Active, True:
                self._icon_active_dark = p
            case QIcon.Mode.Active, False:
                self._icon_active_light = p
            case QIcon.Mode.Disabled, True:
                self._icon_disabled_dark = p
            case QIcon.Mode.Disabled, False:
                self._icon_disabled_light = p
            case QIcon.Mode.Normal, True:
                self._icon_normal_dark = p
            case QIcon.Mode.Normal, False:
                self._icon_normal_light = p
            case QIcon.Mode.Selected, True:
                self._icon_selected_dark = p
            case QIcon.Mode.Selected, False:
                self._icon_selected_light = p
            case _, _:
                assert_never(mode)  # type: ignore

    def _has_icon(self, mode: QIcon.Mode):
        if _use_dark_icon():
            name = f"_icon_{mode.name.lower()}_dark"
        else:
            name = f"_icon_{mode.name.lower()}_light"
        return name in self.__dict__

    def _get_icon(
        self, size: QSize, mode: QIcon.Mode | None, state: QIcon.State
    ):
        match mode, _use_dark_icon():
            case QIcon.Mode.Selected, True if self._has_icon(mode):
                i = self._icon_selected_dark
            case QIcon.Mode.Selected, False if self._has_icon(mode):
                i = self._icon_selected_light
            case QIcon.Mode.Normal, True:
                i = self._icon_selected_dark
            case QIcon.Mode.Normal, False:
                i = self._icon_selected_light
            case QIcon.Mode.Active, True if self._has_icon(mode):
                i = self._icon_active_dark
            case QIcon.Mode.Active, False if self._has_icon(mode):
                i = self._icon_active_light
            case QIcon.Mode.Disabled, True if self._has_icon(mode):
                i = self._icon_disabled_dark
            case QIcon.Mode.Disabled, False if self._has_icon(mode):
                i = self._icon_disabled_light
            case _, True:
                i = self._icon_normal_dark
            case _, False:
                i = self._icon_normal_light
            case _, _:
                assert_never(mode)  # type: ignore
        return i

    def pixmap(
        self, size: QSize, mode: QIcon.Mode, state: QIcon.State, /
    ) -> QPixmap:
        i = self._get_icon(size, mode, state)
        if i.size() == size:
            return i
        return i.scaled(size)

    def paint(
        self,
        painter: QPainter,
        rect: QRect,
        mode: QIcon.Mode,
        state: QIcon.State,
        /,
    ) -> None:
        i = self._get_icon(rect.size(), mode, state)
        painter.drawPixmap(rect, i)
        return

    def clone(self):
        return copy(self)
