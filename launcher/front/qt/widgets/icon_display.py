from typing import assert_never

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QIcon, QImage, QPainter, QPaintEvent, QPixmap, Qt
from PySide6.QtWidgets import QStyle, QWidget


def _mshv(size: QSize | QRect):
    return min(size.width(), size.height())


def _si(img: str | QIcon.ThemeIcon | QIcon | QPixmap | QImage) -> QIcon:
    match img:
        case str() if img.startswith(":/"):
            return QIcon(img)
        case str() | QIcon.ThemeIcon():
            return QIcon.fromTheme(img)
        case QImage():
            return QIcon(QPixmap.fromImage(img))
        case QPixmap():
            return QIcon(img)
        case QIcon():
            return img
        case _:
            assert_never(img)


class IconDisplayWidget(QWidget):
    def __init__(
        self,
        icon: str | QIcon.ThemeIcon | QIcon | QPixmap | QImage,
        parent: QWidget | None = None,
        *,
        size: int | QSize | None = None,
    ):
        super().__init__(parent)
        self._icon = _si(icon)

        if size:
            if isinstance(size, QSize):
                self._size = size
            else:
                self._size = QSize(size, size)
        else:
            self._size = sorted(self._icon.availableSizes(), key=_mshv)[0]

        self.setFixedSize(self._size)

    def sizeHint(self, /) -> QSize:
        return self._size

    def paintEvent(self, event: QPaintEvent, /) -> None:
        painter = QPainter(self)
        r = self.rect()
        new_size = _mshv(r)
        new_qsize = QSize(new_size, new_size)
        self._icon.paint(
            painter,
            QStyle.alignedRect(
                Qt.LayoutDirection.LeftToRight,
                Qt.AlignmentFlag.AlignCenter,
                new_qsize,
                r,
            ),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

    def set_icon(
        self,
        new: str | QIcon.ThemeIcon | QIcon | QPixmap | QImage,
        *,
        size: int | QSize | None,
    ):
        self._icon = _si(new)
        if size and isinstance(size, QSize):
            self._size = size
        elif size:
            assert isinstance(size, int)
            self._size = QSize(size, size)
        else:
            # automatically get smallest(?) size
            self._size = sorted(self._icon.availableSizes(), key=_mshv)[0]

        self.setFixedSize(self._size)

    def icon(self):
        return self._icon
