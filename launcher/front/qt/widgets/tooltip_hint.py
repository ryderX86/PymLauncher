import weakref

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QIcon, QPainter, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QStyle, QWidget

from launcher import config
from launcher.front.icon_helpers import AdaptiveIconEngine, IconName
from launcher.front.qt.binding_mixin import BindingMixin


class TooltipHint(BindingMixin, QWidget):
    hide_all = Signal(bool)
    instances = []

    def __init__(
        self, tooltip: str | None = None, size: int | QSize = 12, parent=None
    ):
        super().__init__(parent)
        self._icon = AdaptiveIconEngine(IconName.TOOLTIP)
        if isinstance(size, QSize):
            if size.width() > size.height():
                size.setWidth(size.height())
            elif size.height() > size.width():
                size.setHeight(size.width())
            self._size = size
        else:
            self._size = QSize(size, size)
        self.setMinimumSize(self._size)
        self.setProperty("tooltipHint", True)
        self._tooltip_text = tooltip
        if tooltip:
            self.setText(tooltip)
        self.hide_all.connect(self._hide_all_sig)
        self.ref = weakref.ref(self)
        self.instances.append(self.ref)

    def bind(self):
        if not config.tooltip_icons_enabled:
            self.setHidden(not config.tooltip_icons_enabled)

    def deleteLater(self) -> None:
        self.instances.remove(self.ref)
        return super().deleteLater()

    def _hide_all_sig(self, hide: bool):
        if hide:
            self.setHidden(True)
        else:
            self.setHidden(False)

    def setText(self, text: str):
        """NOT Qt builtin"""
        if not text:
            self.setToolTip("")
            self.setHidden(True)
            return
        self.setHidden(False)
        self.setToolTip(text)

    def text(self):
        return self.toolTip()

    def setIconSize(self, size: int | QSize):
        if isinstance(size, int):
            self._size = QSize(size, size)
        else:
            self._size = size
        self.setMinimumSize(self._size)

    def paintEvent(self, event: QPaintEvent, /) -> None:
        if not config.tooltip_icons_enabled:
            return
        painter = QPainter(self)
        r = self.rect()
        new_size = min(r.width(), r.height())
        new_qsize = QSize(new_size, new_size)
        p = self._icon.pixmap(new_qsize, QIcon.Mode.Normal, QIcon.State.Off)
        painter.drawPixmap(
            QStyle.alignedRect(
                Qt.LayoutDirection.LeftToRight,
                Qt.AlignmentFlag.AlignCenter,
                p.size(),
                r,
            ),
            p,
        )
        painter.end()

    @classmethod
    def widget_tooltip(cls, tooltip: str, w: QWidget) -> QWidget:
        p = QWidget()
        p.setContentsMargins(0, 0, 0, 0)
        lo = QHBoxLayout(p)
        lo.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lo.setSpacing(0)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.addWidget(w, 0)
        lo.addWidget(cls(), 0)
        tooltip = tooltip.replace("\n", "<br>")
        if "<" not in tooltip and ">" not in tooltip:
            tooltip = f"<p>{tooltip}</p>"
        p.setToolTip(tooltip)
        return p


@Slot()
def refresh_visibility():
    _remove = []
    for ref in TooltipHint.instances:  # type: ignore
        obj = ref()
        if not obj:
            _remove.append(ref)
            continue
        obj.setHidden(not config.tooltip_icons_enabled)
    if _remove:
        for ref in _remove:
            TooltipHint.instances.remove(ref)  # type: ignore
    return
