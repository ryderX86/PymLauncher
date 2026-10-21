from PySide6.QtCore import QRectF, Qt, QRect
from PySide6.QtGui import QPalette, QColor, QPainterPath, QPen
from PySide6.QtWidgets import (
    QWidget,
    QProxyStyle,
    QStyle,
    QStyleOption,
    QStyleFactory,
)

from launcher import lifecycle


class Win11StyleOverrides(QProxyStyle):
    def __init__(self, base: str | QStyle | None = None):
        if isinstance(base, str):
            base = QStyleFactory.create(base)
        elif not base:
            base = lifecycle.qapp.style()
        base_name = base.name()
        super().__init__(base)
        if base:
            self._style_name = base_name.lower()
            self.setObjectName(base_name)

    def drawPrimitive(self, el, option, painter, widget=None):
        super().drawPrimitive(el, option, painter, widget)
        if self._style_name != "windows11":
            return
        match el:
            case QStyle.PrimitiveElement.PE_FrameTabWidget:
                painter.save()

                match lifecycle.qapp.styleHints().colorScheme():
                    case Qt.ColorScheme.Dark | _ if (
                        option.palette.color(
                            QPalette.ColorRole.Window
                        ).lightness()
                        < 128
                    ):
                        pen = QPen(QColor(255, 255, 255, 9))
                    case _:
                        pen = QPen(QColor(0, 0, 0, 9))

                pen.setWidth(1)
                painter.setPen(pen)
                radius = 5

                rect = (
                    QRectF(option.rect)
                    .adjusted(-1, -1, 0, 0)
                    .translated(0.5, 0.5)
                )

                path = QPainterPath()
                path.moveTo(rect.x(), rect.y())
                path.lineTo(rect.x() + rect.width(), rect.y())
                path.lineTo(
                    rect.x() + rect.width(), rect.y() + rect.height() - radius
                )
                path.arcTo(
                    rect.x() + rect.width() - 2 * radius,
                    rect.y() + rect.height() - 2 * radius,
                    2 * radius,
                    2 * radius,
                    0.0,
                    -90.0,
                )
                path.arcTo(
                    rect.x(),
                    rect.y() + rect.height() - 2 * radius,
                    2 * radius,
                    2 * radius,
                    270.0,
                    -90.0,
                )

                path.closeSubpath()
                painter.drawPath(path)
                painter.restore()
        return

    def subElementRect(
        self, element: QStyle.SubElement, option: QStyleOption, widget: QWidget
    ) -> QRect:
        rect = super().subElementRect(element, option, widget)
        if self._style_name != "windows11":
            return rect
        match element:
            case (
                QStyle.SubElement.SE_TabWidgetTabPane
                | QStyle.SubElement.SE_TabWidgetTabContents
            ):
                return rect.adjusted(1, 1, -1, -1)
        return rect
