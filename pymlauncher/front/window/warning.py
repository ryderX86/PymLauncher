from enum import IntEnum, auto
from typing import Literal
import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QMessageBox,
)

from pymlauncher.config import config

log = logging.getLogger(__name__)


class ButtonConfig(IntEnum):
    OK = QMessageBox.StandardButton.Ok
    YES_NO = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No


class UserReturn(IntEnum):
    NO = 0
    OK_YES = 1


type ButtonLabelType = Literal["ok", "yes", "no"]


class WarningType(IntEnum):
    OFFLINE_MODE_LAUNCH = auto()
    ACCOUNTS_BIN_ENCRYPTION = auto()
    DELETE_PROFILE = auto()
    MODLOADER_VERSION_CONFLICT = auto()
    LOG4J_CONFIG_FAILED = auto()


CHECKBOX_TEXT_OK = "Do not show this message again"
CHECKBOX_TEXT_YESNO = "Remember my choice next time"


class WarningDialog(QMessageBox):
    __slots__ = (
        "_warning_type",
        "_button_config",
        "status",
        "_show_once",
        "checkbox",
    )

    def __init__(
        self,
        text: str,
        type_: WarningType | None = None,
        title: str | None = None,
        *,
        icon: QIcon | None = None,
        show_once: bool = False,
        button_config: ButtonConfig = ButtonConfig.OK,
        button_labels: dict[ButtonLabelType, str] | None = None,
        parent=None,
    ):
        super().__init__(parent, text=text)
        self._warning_type = type_
        self._button_config = button_config
        self.status = None
        self._show_once = show_once
        if title:
            self.setWindowTitle(title)
        if icon:
            self.setIconPixmap(icon.pixmap(32, 32))
        match self._button_config:
            case ButtonConfig.OK:
                self.setStandardButtons(
                    self.StandardButton(self._button_config)
                )
                self.button(self.StandardButton.Ok).clicked.connect(
                    self._ok_yes
                )
                if not icon:
                    self.setIcon(self.Icon.Warning)
            case ButtonConfig.YES_NO:
                self.setStandardButtons(
                    self.StandardButton(self._button_config)
                )
                self.button(self.StandardButton.Yes).clicked.connect(
                    self._ok_yes
                )
                self.button(self.StandardButton.No).clicked.connect(self._no)
                if not icon:
                    self.setIcon(self.Icon.Question)
            case _:
                raise ValueError(f"Bad button type: {self._button_config!r}")
        if type_ is not None:
            if type_ not in WarningType:
                log.warning("Unregistered warning type: %r", type_)
            match self._button_config:
                case ButtonConfig.OK:
                    self._checkbox = QCheckBox(CHECKBOX_TEXT_OK)
                case ButtonConfig.YES_NO:
                    self._checkbox = QCheckBox(CHECKBOX_TEXT_YESNO)
            self.setCheckBox(self._checkbox)
            self._checkbox.setChecked(False)
        else:
            self._checkbox = None
        if button_labels:
            if "ok" in button_labels:
                self.button(self.StandardButton.Ok).setText(
                    button_labels["ok"]
                )
            if "yes" in button_labels:
                self.button(self.StandardButton.Yes).setText(
                    button_labels["yes"]
                )
            if "no" in button_labels:
                self.button(self.StandardButton.No).setText(
                    button_labels["no"]
                )

    def _handle_dismissal(self):
        if self._checkbox and (self._checkbox.isChecked() or self._show_once):
            if not isinstance(self._warning_type, WarningType):
                log.warning(
                    "Checkbox was checked without a warning type! Ignoring."
                )
                return
            log.info(
                "User ignored warning type '%s'",
                WarningType(self._warning_type).name,
            )
            config.ignored_messages.add(self._warning_type)
            if self._button_config == ButtonConfig.YES_NO:
                match self.status:
                    case UserReturn.OK_YES:
                        config.dialog_answers[str(self._warning_type)] = True
                    case _:
                        config.dialog_answers[str(self._warning_type)] = False

    def _ok_yes(self):
        self.status = UserReturn.OK_YES
        self.accept()

    def _no(self):
        self.status = UserReturn.NO
        self.accept()

    def exec(self):
        if self._warning_type in config.ignored_messages:
            log.debug(
                "Not showing ignored warning '%s'",
                self._warning_type.value,  # type: ignore
            )
            if str(self._warning_type) in config.dialog_answers:
                if (
                    config.dialog_answers.get(str(self._warning_type), False)
                    is True
                ):
                    self.status = UserReturn.OK_YES
                else:
                    self.status = UserReturn.NO
            return 0
        if config.allow_audio:
            QApplication.beep()
        return super().exec()

    def show(self):
        """
        Same as `.exec()`, but won't block the main window and won't call
        `QApplication.beep()`
        """
        if self._warning_type in config.ignored_messages:
            log.debug(
                "Not showing ignored warning '%s'",
                self._warning_type.value,  # type: ignore
            )
            if str(self._warning_type) in config.dialog_answers:
                if (
                    config.dialog_answers.get(str(self._warning_type), False)
                    is True
                ):
                    self.status = UserReturn.OK_YES
                else:
                    self.status = UserReturn.NO
            return None
        return super().show()

    def accept(self) -> None:
        self._handle_dismissal()
        return super().accept()

    def reject(self) -> None:
        self._handle_dismissal()
        return super().reject()

    def hide(self) -> None:
        self._handle_dismissal()
        return super().hide()

    def close(self) -> bool:
        self._handle_dismissal()
        return super().close()

    @classmethod
    def warn(
        cls,
        parent=None,
        title: str | None = None,
        text: str = "<oops>",
        type_: WarningType | None = None,
        *,
        show_once: bool = False,
        button_config: ButtonConfig = ButtonConfig.OK,
        ico: QIcon | None = None,
        button_labels: dict[ButtonLabelType, str] | None = None,
    ):
        dialog = cls(
            text,
            type_,
            title or "Warning",
            icon=ico,
            button_config=button_config,
            parent=parent,
            show_once=show_once,
            button_labels=button_labels,
        )
        dialog.exec()
        s = dialog.status
        dialog.deleteLater()
        match s:
            case UserReturn.OK_YES:
                return True
            case UserReturn.NO:
                return False
            case _:
                return False
