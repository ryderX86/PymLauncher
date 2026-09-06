import weakref

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QLabel

from launcher.config import config
from launcher.front import resources


class TooltipHint(QLabel):
    hide_all = Signal(bool)
    _instances = []

    def __init__(self, tooltip: str | None = None, parent=None):
        super().__init__(parent)
        self.setPixmap(resources.symbol("info").pixmap(12, 12))
        self.setProperty("tooltipHint", True)
        self._tooltip_text = tooltip
        if tooltip:
            self.setText(tooltip)
        self.setMargin(0)
        self.setContentsMargins(0, 0, 0, 0)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.hide_all.connect(self._hide_all_sig)
        self.ref = weakref.ref(self)
        self._instances.append(self.ref)
        if not config.tooltip_icons_enabled:
            self.setHidden(not config.tooltip_icons_enabled)

    def deleteLater(self) -> None:
        self._instances.remove(self.ref)
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
        lines = text.splitlines()
        if len(lines) > 0:
            lines[0] = f"<nobr>{lines[0]}</nobr>"
            text = f"<font>{"<br>".join(lines)}</font>"
        self.setToolTip(text)

    def text(self):
        return self.toolTip()

    def setIconSize(self, w: int | QSize, h: int | None = None):
        if isinstance(w, QSize):
            self.setPixmap(resources.symbol("info").pixmap(w))
        elif h:
            self.setPixmap(resources.symbol("info").pixmap(w, h))
        if w and h:
            return
        raise ValueError("Missing height argument!")

    @classmethod
    def refresh_visibility(cls):
        _remove = []
        for ref in cls._instances:
            obj = ref()
            if not obj:
                _remove.append(ref)
                continue
            obj.setHidden(not config.tooltip_icons_enabled)
        if _remove:
            for ref in _remove:
                cls._instances.remove(ref)
        return
