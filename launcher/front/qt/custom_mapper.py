from types import (
    FunctionType,
    MethodType,
    BuiltinFunctionType,
    BuiltinMethodType,
)
from collections.abc import Callable
from typing import Any
import logging

from PySide6.QtCore import Signal, SignalInstance, QObject
from PySide6.QtWidgets import QWidget, QLineEdit, QComboBox, QCheckBox

from .widgets.config_checkbox import ConfigCheckbox

log = logging.getLogger(__name__)

LiterallyAnyFunction = (
    FunctionType | MethodType | BuiltinMethodType | BuiltinFunctionType
)


class CustomMapper(QObject):
    """
    Entirely custom implementation of a QWidgetDataMapper object for Qt widgets
    """

    changes_made = Signal(bool)
    saved = Signal()
    widgets_set = Signal()
    """Signal fired off when reset() or set_initial_values() is done"""

    def __init__(self, parent=None, strict: bool = True):
        """
        QWidgetDataMapper alternative.

        Setting `strict` to `False` will disable any exceptions being raised
        for getter errors when saving.

        Use `start()` after adding mappings using `add_mapping()`; `stop()` to
        stop monitoring either permenantly or temporarily.

        If `saver` is provided when adding widgets, you can use `save()` to get
        all of the data from the widgets, otherwise the data will be returned.
        If some widgets are given data but not others, save will return the
        data for widgets that don't have savers.
        """
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
        self._strict = strict
        self._save_hooks: set[Callable[[], None]] = set()

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
        """
        ## Arguments
        `widget`: Widget to monitor

        `getter`: Method/function that will be used to get the widget's current
        value for comparison. If not provided, there will be an attempt to
        match the widget's type and get the function from that. If that fails,
        a `ValueError` will be raised.

        `setter`: Method/function that takes one argument that will be used to
        set the widget's current value. Same as `getter`, if this isn't
        provided, the widget type will be matched, etc.

        `signal`: Signal to monitor for widget's data changing. Same as
        `getter` and `setter`, this will be matched to the widget type if not
        provided.

        `saver`: Method/function to call for saving this widget's data. Must
        take exactly one argument of type `str`, `int`, or `bool`. Can return
        anything.

        `saver_getter`: Method/function to call for getting this widget's data
        when saving. If not provided, this will default to `getter`
        """
        id_ = id(widget)
        match widget:
            case QLineEdit() if not all((getter, setter, signal)):
                if not getter:
                    getter = widget.text
                if not setter:
                    setter = widget.setText
                if not signal:
                    signal = widget.textChanged
            case QComboBox() if (
                not all((getter, setter, signal)) and not widget.isEditable()
            ):
                if not getter:
                    getter = widget.currentIndex
                if not setter:
                    setter = widget.setCurrentIndex
                if not signal:
                    signal = widget.currentIndexChanged
            case QComboBox() if (
                not all((getter, setter, signal)) and widget.isEditable()
            ):
                if not getter:
                    getter = widget.currentText
                if not setter:
                    setter = widget.setCurrentText
                if not signal:
                    signal = widget.currentTextChanged
            case QCheckBox() if not all((getter, setter, signal)):
                if not getter:
                    getter = widget.isChecked
                if not setter:
                    setter = widget.setChecked
                if not signal:
                    signal = widget.checkStateChanged
            case ConfigCheckbox():
                if not all((getter, setter, signal, saver)):
                    return self.add_mapping(**widget.mapper_objects())
            case _ if not all((getter, setter, signal)):
                raise ValueError(
                    "Must be given all of 'getter', 'setter', and 'signal' if "
                    "widget is not one of: QLineEdit, QComboBox, QCheckBox"
                )
        if not isinstance(getter, LiterallyAnyFunction):
            raise TypeError(
                "'getter' must be FunctionType or MethodType, "
                f"not {type(getter).__name__!r}"
            )
        if not isinstance(setter, LiterallyAnyFunction):
            raise TypeError(
                "'setter' must be FunctionType or MethodType, "
                f"not {type(setter).__name__!r}"
            )
        if not isinstance(signal, SignalInstance):
            raise TypeError(
                "'signal' must be PySide6.QtCore.Signal, "
                f"not {type(signal).__name__!r}"
            )
        assert getter
        assert setter
        assert signal
        if not saver_getter:
            saver_getter = getter
        self._widgets[id_] = (widget, getter, setter, saver, saver_getter)
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
        self.widgets_set.emit()
        return

    reset = set_initial_values
    """Alias for `set_initial_values()`"""

    def revert_changes(self):
        self._active = False
        for id_, (_, _, setter, _, _) in self._widgets.items():
            setter(self._initial_values[id_])
        self._active = True
        self.changes_made.emit(False)
        return

    def save(self) -> dict[QWidget, Any]:
        other_vals = {}
        for id_, (widget, _, _, saver, saver_getter) in self._widgets.items():
            try:
                data = saver_getter()
            except Exception as err:
                log.error(
                    "Failed to run saver_getter() on object at address %r:",
                    hex(id_),
                    exc_info=err,
                )
                if self._strict:
                    raise err
                continue
            if saver:
                try:
                    saver(data)
                except Exception as err:
                    log.error(
                        "Failed to run saver(saver_getter()) on object at "
                        "memory address %s\n"
                        "Result of 'saver_getter()': %s",
                        hex(id_),
                        data,
                        exc_info=err,
                    )
            else:
                other_vals[widget] = data
        self.set_initial_values()
        self._data_changed()
        for h in self._save_hooks:
            h()
        self.saved.emit()
        return other_vals

    def start(self):
        self.set_initial_values()
        self._active = True
        self.blockSignals(False)

    def stop(self):
        self._active = False
        self.blockSignals(True)

    def add_save_hook(self, hook: Callable[[], None]):
        """
        Add a method/function to be called when `save()` is finished.

        Must be a callable that takes zero arguments.
        """
        self._save_hooks.add(hook)

    def remove_save_hook(self, hook: Callable[[], None]):
        """
        Remove a method/function from being called when `save()` is finished.

        Must be a callable that has already been added to `add_save_hook()`
        """
        self._save_hooks.remove(hook)
