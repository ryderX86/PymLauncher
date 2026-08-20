import logging

from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)


class FocusEventFilter(QObject):
    log = log.getChild("FocusEventFilter")

    def eventFilter(self, target: QObject, event: QEvent):
        match event, target:
            case QFocusEvent(), QWidget():

                match event.type():
                    case event.Type.FocusIn if event.reason() in {
                        Qt.FocusReason.TabFocusReason,
                        Qt.FocusReason.BacktabFocusReason,
                        Qt.FocusReason.ShortcutFocusReason,
                    }:
                        target.setProperty("keyFocus", True)
                    case _:
                        target.setProperty("keyFocus", False)
                style = target.style()
                if style:
                    style.polish(target)
                else:
                    self.log.warning(
                        "Couldn't get QStyle object for %r",
                        type(target).__name__,
                    )
        return False
