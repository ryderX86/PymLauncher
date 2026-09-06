from collections.abc import Callable
from enum import StrEnum
import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from launcher import constants
from launcher.front.resources import symbol
from launcher.functions import truncate

log = logging.getLogger(__name__)


class CopyToClipboardButton(QPushButton):
    class ContentType(StrEnum):
        TEXT = "text"
        IMAGE = "image"
        PIXMAP = "pixmap"

    def __init__(
        self,
        parent: QWidget | None,
        get_content_func: Callable,
        content_type: ContentType = ContentType.TEXT,
        is_icon_button: bool = True,
    ):
        super().__init__(parent)
        if is_icon_button:
            self._default_icon = symbol("clipboard")
            self.setIcon(self._default_icon)
            self.setFixedHeight(40)
            self.setFixedWidth(40)
            self._clicked_icon = symbol("clipboard-checked")
        else:
            self.setText("Copy to clipboard")

        self._clipboard = QApplication.clipboard()
        self._get_content_func = get_content_func
        self._type = content_type

        match self._type:
            case self.ContentType.TEXT:
                func = self.copy_text
            case self.ContentType.IMAGE:
                func = self.copy_img
            case self.ContentType.PIXMAP:
                func = self.copy_pixmap

        if self._clipboard:
            self.clicked.connect(func)
            if is_icon_button:
                self._animation = self._animate_icon
            else:
                self._animation = self._animate_text
        else:
            log.warning("Unable to get clipboard")
            self.setDisabled(True)

    def copy_text(self):
        try:
            content = self._get_content_func()
        except Exception as err:
            log.error(
                "Failed to get content from %r %r: %r",
                type(self._get_content_func).__name__,
                self._get_content_func.__name__,
                type(err).__name__,
                exc_info=err,
            )
            return
        try:
            self._clipboard.setText(content)
        except Exception as err:
            log.error(
                "Failed to set clipboard content: %r",
                type(err).__name__,
                exc_info=err,
            )
        else:
            log.debug("Copied %r to clipboard.", truncate(content, 80))
            self._animation()

    def copy_img(self):
        try:
            content = self._get_content_func()
        except Exception as err:
            log.error(
                "Failed to get content from %r %r: %r",
                type(self._get_content_func).__name__,
                self._get_content_func.__name__,
                type(err).__name__,
                exc_info=err,
            )
            return
        try:
            self._clipboard.setImage(content)
        except Exception as err:
            log.error(
                "Failed to set clipboard content: %r",
                type(err).__name__,
                exc_info=err,
            )
        else:
            log.debug("Copied image to clipboard.")
            self._animation()

    def copy_pixmap(self):
        try:
            content = self._get_content_func()
        except Exception as err:
            log.error(
                "Failed to get content from %r %r: %r",
                type(self._get_content_func).__name__,
                self._get_content_func.__name__,
                type(err).__name__,
                exc_info=err,
            )
            return
        try:
            self._clipboard.setPixmap(content)
        except Exception as err:
            log.error(
                "Failed to set clipboard content: %r",
                type(err).__name__,
                exc_info=err,
            )
        else:
            log.debug("Copied pixmap to clipboard.")
            self._animation()

    def _animate_icon_finish(self):
        self.setIcon(self._default_icon)
        self.setDisabled(False)

    def _animate_icon(self):
        self.setIcon(self._clicked_icon)
        self.setDisabled(True)
        QTimer.singleShot(
            constants.DONE_VISUAL_DELAY, self._animate_icon_finish
        )

    def _animate_text_finish(self):
        self.setText("Copy to clipboard")
        self.setDisabled(False)

    def _animate_text(self):
        self.setText("Copied!")
        self.setDisabled(True)
        QTimer.singleShot(
            constants.DONE_VISUAL_DELAY, self._animate_text_finish
        )
