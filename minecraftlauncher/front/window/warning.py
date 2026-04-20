from enum import IntEnum
import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QCheckBox, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QLabel)

from minecraftlauncher import config
from minecraftlauncher.front.qt.widgets import TooltipHint

log = logging.getLogger(__name__)

class ButtonConfig(IntEnum):
    OK = 0
    YES_NO = 1

class UserReturn(IntEnum):
    NO = 0
    OK_YES = 1

class WarningType(IntEnum):
    OFFLINE_MODE_LAUNCH = 0

class Warning(QDialog):
    def __init__(self, text: str, type_: WarningType | None = None,
                 title: str | None = None, ico: QIcon | None = None,
                 button_config: ButtonConfig = ButtonConfig.OK, parent=None):
        super().__init__(parent)
        self._text = text
        self._title = title
        self._ico = ico
        self._warning_type = type_
        self._button_config = button_config
        self.status = None

    def _build_ui(self):
        root = QVBoxLayout(self)

        msg = QLabel(self._text)
        if self._ico:
            msg.setPixmap(self._ico.pixmap(32, 32))
        
        root.addWidget(msg)

        checkbox_row_w = QWidget()
        checkbox_row = QHBoxLayout(checkbox_row_w)
        
        self.checkbox = QCheckBox("Do not show this message again")
        self.checkbox.setChecked(False)
        checkbox_row.addWidget(self.checkbox)
        if self._warning_type:
            root.addWidget(checkbox_row_w)
        
        button_row_w = QWidget()
        button_row = QHBoxLayout(button_row_w)
        button_row.addStretch()

        match self._button_config:
            case ButtonConfig.OK:
                self.main_button = QPushButton("OK")
                self.no_button = None
            case ButtonConfig.YES_NO:
                self.main_button = QPushButton("Yes")
                self.no_button = QPushButton("No")
                self.no_button.clicked.connect(self._no)
                button_row.addWidget(self.no_button)
            case _: # shouldn't happen, just making the type checker happy
                raise

        self.main_button.clicked.connect(self._ok_yes)
        button_row.addWidget(self.main_button)

        root.addWidget(button_row_w)

    def _handle_dismissal(self):
        if self.checkbox.isChecked():
            if not isinstance(self._warning_type, WarningType):
                log.warning(
                    "Checkbox was checked without a warning type! Ignoring.")
                return
            log.info("User ignored warning type '%s'"
                     % WarningType(self._warning_type).name)
            config.ignored_messages.append(self._warning_type)
            if self._button_config == ButtonConfig.YES_NO:
                match self.status:
                    case UserReturn.OK_YES:
                        config.dialog_answers[self._warning_type] = True
                    case _:
                        config.dialog_answers[self._warning_type] = False

    def _ok_yes(self):
        self.status = UserReturn.OK_YES

    def _no(self):
        self.status = UserReturn.NO

    def exec(self) -> int:
        if self._warning_type in config.ignored_messages:
            log.debug("Not showing ignored warning '%s'"
                      % self._warning_type.value)
            if self._warning_type in config.dialog_answers:
                if config.dialog_answers[self._warning_type]:
                    self.status = UserReturn.OK_YES
                else:
                    self.status = UserReturn.NO
            return 0
        self._build_ui()
        return super().exec()
    
    def show(self) -> None:
        if self._warning_type in config.ignored_messages:
            log.debug("Not showing ignored warning '%s'"
                      % self._warning_type.value)
            if self._warning_type in config.dialog_answers:
                if config.dialog_answers[self._warning_type]:
                    self.status = UserReturn.OK_YES
                else:
                    self.status = UserReturn.NO
            return
        self._build_ui()
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
    def warn(cls, parent=None, text: str = "<oops>",
             type_: WarningType | None = None,
             title: str | None = None,
             button_config: ButtonConfig = ButtonConfig.OK,
             ico: QIcon | None = None):
        dialog = cls(text, type_, title, ico, button_config, parent)
        dialog.exec()
        match dialog.status:
            case UserReturn.OK_YES:
                return True
            case UserReturn.NO:
                return False
            case _:
                return False