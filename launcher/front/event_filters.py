from collections.abc import Callable
from typing import Iterable
import logging

from PySide6.QtCore import (
    QEvent,
    QObject,
    Qt,
    Signal,
)
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


class MiscEventFilter(QObject):
    event_filtered = Signal(QEvent)

    _events: tuple[type[QEvent], ...]
    _catch_return: bool | None
    _catch_return_func: Callable | None

    _active: bool

    def __init__(
        self,
        events: type[QEvent] | Iterable[type[QEvent]],
        return_true_on_catch: bool | Callable[[QEvent], bool] = False,
        parent=None,
    ):
        super().__init__(parent=parent)

        self._active = True
        if isinstance(return_true_on_catch, bool):
            self._catch_return = return_true_on_catch
            self._catch_return_func = None
        else:
            self._catch_return = None
            self._catch_return_func = return_true_on_catch
        if isinstance(events, tuple):
            self._events = events
        elif isinstance(events, Iterable):
            self._events = tuple(events)
        else:
            self._events = (events,)

    def _on_target_destroyed(self):
        self._active = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self._active:
            return False
        if not isinstance(event, tuple(self._events)):
            return False
        self.event_filtered.emit(event)
        if self._catch_return is not None:
            return self._catch_return
        else:
            assert self._catch_return_func
            return self._catch_return_func(event)
