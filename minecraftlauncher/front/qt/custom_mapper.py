from collections.abc import Callable
from typing import Any
import logging

from PySide6.QtCore import Signal, SignalInstance, QObject
from PySide6.QtWidgets import QWidget, QLineEdit, QComboBox, QCheckBox

log = logging.getLogger(__name__)


class CustomMapper(QObject):
    """
    Entirely custom implementation of a QWidgetDataMapper object for Qt widgets
    """

    changes_made = Signal(bool)
    saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widgets = {}
        """
        Dict containing the widgets to be mapped to/from.

        Indexes will be generated from `id(<widget>)`
        """

        self._initial_values = {}
        """
        Dict containing values to compare to/from.

        Indexes will be generated from `id(<widget>)` and
        `self._widgets[<result of id()>][1 (getter)]()`
        """

        self._active: bool = False
        self.blockSignals(True)

    def add_mapping(
        self,
        widget: QWidget,
        getter: (
            Callable[[], str] | Callable[[], bool] | Callable[[], int] | None
        ) = None,
        setter: (
            Callable[[str], Any]
            | Callable[[int], Any]
            | Callable[[bool], Any]
            | None
        ) = None,
        signal: SignalInstance | None = None,
        saver: (
            Callable[[str], Any]
            | Callable[[int], Any]
            | Callable[[bool], Any]
            | None
        ) = None,
        saver_getter: (
            Callable[[], str] | Callable[[], int] | Callable[[], bool] | None
        ) = None,
    ):
        id_ = id(widget)
        match widget:
            case QLineEdit() if not all([getter, setter, signal]):
                if not getter:
                    getter = widget.text
                if not setter:
                    setter = widget.setText
                if not signal:
                    signal = widget.textChanged
            case QComboBox() if (
                not all([getter, setter, signal]) and not widget.isEditable()
            ):
                if not getter:
                    getter = widget.currentIndex
                if not setter:
                    setter = widget.setCurrentIndex
                if not signal:
                    signal = widget.currentIndexChanged
            case QComboBox() if (
                not all([getter, setter, signal]) and widget.isEditable()
            ):
                if not getter:
                    getter = widget.currentText
                if not setter:
                    setter = widget.setCurrentText
                if not signal:
                    signal = widget.currentTextChanged
            case QCheckBox() if not all([getter, setter, signal]):
                if not getter:
                    getter = widget.isChecked
                    setter = widget.setChecked
                    signal = widget.checkStateChanged
        if not saver_getter:
            saver_getter = getter
        self._widgets[id_] = (widget, getter, setter, saver, saver_getter)
        if not signal or not getter or not setter:
            raise ValueError(
                "Must be given all of 'getter', 'setter', and 'signal' if "
                "widget is not one of: QLineEdit, QComboBox, QCheckBox"
            )
        signal.connect(self._data_changed)

    def _data_changed(self, *args, **kwargs):
        if not self._active:
            return
        if len(args) + len(kwargs) > 1:
            log.warning(
                "Excess values given to _data_changed(): %s",
                ", ".join([str(args), str(kwargs)]),
            )
        changed_state = False
        for id_, (widget, getter, _, _, _) in self._widgets.items():
            if id_ not in self._initial_values:
                log.warning(
                    "Couldn't get widget's initial data for instance of '%s' at memory address %s",
                    type(widget).__name__,
                    hex(id_),
                )
                continue
            if getter() != self._initial_values[id_]:
                changed_state = True
        self.changes_made.emit(changed_state)

    def set_initial_values(self):
        for id_, (_, getter, _, _, _) in self._widgets.items():
            self._initial_values[id_] = getter()
        return

    def revert_changes(self):
        self._active = False
        for id_, (_, _, setter, _, _) in self._widgets.items():
            setter(self._initial_values[id_])
        self._active = True
        self.changes_made.emit(False)
        return

    def save(self):
        for id_, (_, _, _, saver, saver_getter) in self._widgets.items():
            if saver:
                try:
                    saver(saver_getter())
                except Exception as err:
                    log.error(
                        "Failed to run saver(saver_getter()) on object at "
                        "memory address %s\n"
                        "Result of 'saver_getter()': %s",
                        hex(id_),
                        saver_getter(),
                        exc_info=err,
                    )
        self.set_initial_values()
        self._data_changed()
        self.saved.emit()

    def start(self):
        self.set_initial_values()
        self._active = True
        self.blockSignals(False)

    def stop(self):
        self._active = False
        self.blockSignals(True)
