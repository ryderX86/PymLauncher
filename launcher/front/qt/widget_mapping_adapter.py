from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
import logging

from PySide6.QtCore import SignalInstance
from PySide6.QtWidgets import QComboBox, QLineEdit, QWidget

log = logging.getLogger(__name__)


def _def_normalize(a: Any):
    return a


def _def_valid():
    return True


@dataclass(slots=True, kw_only=True, eq=False)
class WidgetMappingAdapter:
    # dataclass values
    read: Callable[[], str | int | bool | None]
    """Function that we use to read what's inside the widget"""
    write: (
        Callable[[str | None], None]
        | Callable[[int | None], None]
        | Callable[[bool | None], None]
        | Callable[[str], None]
        | Callable[[int], None]
        | Callable[[bool], None]
    )
    """Function we call to write to the widget's value"""
    normalize: Callable[[Any], Any] = field(default=_def_normalize)
    """Normalize the value for saving/comparison"""
    attr_name: str
    """The profile's attribute name"""
    signal: SignalInstance
    """The "value edited" signal"""
    widget: QWidget | None = field(default=None)

    # private/instance attributes
    _startup_val: str | int | bool = field(init=False, hash=True, compare=True)

    def __post_init__(self):
        self._startup_val = self.normalize(self.read())

    def reset_known(self, prof):
        """
        Use after setting an attribute to reset what this adapter thinks is the
        previous "clean" value.
        """
        self._startup_val = self.normalize(getattr(prof, self.attr_name))

    def reset(self):
        """
        Resets the widget's value.
        """
        self.write(self._startup_val)  # type: ignore

    def changed(self) -> bool:
        return self.normalize(self.read()) != self._startup_val

    @property
    def data_valid(self) -> bool:
        match self.widget:
            case QLineEdit():
                return self.widget.hasAcceptableInput()
            case QComboBox() if self.widget.lineEdit():
                return (
                    self.widget.lineEdit().hasAcceptableInput()  # type: ignore
                )
            case _:
                return True

    def set_invalid_display(self, invalid: bool):
        if not self.widget:
            log.warning(
                "%s: No widget to set invalid property for",
                type(self).__name__,
            )
            return
        self.widget.setProperty("invalid", invalid)
        self.widget.style().unpolish(self.widget)
        self.widget.style().polish(self.widget)
