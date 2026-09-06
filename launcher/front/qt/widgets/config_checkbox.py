import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from launcher.config import config

from .tooltip_hint import TooltipHint

log = logging.getLogger(__name__)


class ConfigCheckbox(QWidget):
    check_state_changed = Signal(bool)

    config_mapping: str
    _checkbox: QCheckBox
    _tooltip: TooltipHint | None
    _lo: QHBoxLayout

    def __init__(
        self,
        text: str,
        config_mapping: str,
        *,
        tooltip_text: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self._lo = QHBoxLayout(self)
        self._lo.setContentsMargins(0, 0, 0, 0)
        self._lo.setSpacing(12)
        self._checkbox = QCheckBox(text)
        try:
            self._checkbox.setChecked(getattr(config, config_mapping))
        except AttributeError as err:
            raise KeyError(
                f"Config member {config_mapping!r} not found"
            ) from err
        else:
            self.config_mapping = config_mapping
        self._lo.addWidget(self._checkbox)
        if tooltip_text:
            self._init_tooltip()
            self.set_tooltip_text(tooltip_text)
        else:
            self._tooltip = None

        self._checkbox.checkStateChanged.connect(self._check_state_changed)

    def _check_state_changed(self, check_state: Qt.CheckState):
        match check_state:
            case Qt.CheckState.Checked | Qt.CheckState.PartiallyChecked:
                self.check_state_changed.emit(True)
            case Qt.CheckState.Unchecked:
                self.check_state_changed.emit(False)
            case _:
                log.warning("Unknown check state: %r", check_state)
                self.check_state_changed.emit(False)

    def _init_tooltip(self):
        self._tooltip = TooltipHint()
        self._lo.addWidget(self._tooltip)

    def _rm_tooltip(self):
        if self._tooltip is None:
            log.warning("_rm_tooltip() called without a tooltip existing")
            return
        self._lo.removeWidget(self._tooltip)
        self._tooltip.deleteLater()
        self._tooltip = None
        return

    def set_tooltip_text(self, new_text: str):
        if self._tooltip is None:
            self._init_tooltip()
        assert self._tooltip is not None

        self._tooltip.setText(new_text)

    @property
    def state(self):
        return self._checkbox.isChecked()

    def state_(self):
        """Member for CustomMapper to use"""
        return self.state

    def save_(self):
        """Member for CustomMapper to use"""
        setattr(config, self.config_mapping, self.state)

    def reset(self):
        self._checkbox.setChecked(getattr(config, self.config_mapping))

    def set_checked(self, checked: bool):
        self._checkbox.setChecked(checked)

    def mapper_objects(self):
        """
        Use this to get the objects needed for the CustomMapper object.

        Example: `mapper.add_mapping(**checkbox.mapper_objects())`
        """
        return {
            "widget": self,
            "getter": self.state_,
            "setter": self.set_checked,
            "signal": self.check_state_changed,
            "saver": self.save_,
            "saver_getter": None,
        }
