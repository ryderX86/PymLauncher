"""
minecraftlauncher.front.window.main.profiles_page_2

Profile management page rewritten to use CustomMapper instead of Qt's mapper
"""

import logging
import time
import os

from PySide6.QtCore import Qt, Signal, QThread, QSize, QEvent
from PySide6.QtGui import (
    QAction,
    QContextMenuEvent,
    QMouseEvent,
    QShortcut,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
    QDataWidgetMapper,
    QListView,
    QCheckBox,
    QMenu,
)

from minecraftlauncher import config, constants
from minecraftlauncher.datatypes import GameProfile
from minecraftlauncher.datatypes.game_version import GameVersionStub
from minecraftlauncher.back import version_manager, profile_manager
from minecraftlauncher.front import styles, resources
from minecraftlauncher.front.qt import CustomMapper
from minecraftlauncher.front.qt.models import (
    ProfileModel,
    ProfileSelectionModel,
)
from minecraftlauncher.front.qt.widgets import (
    IconPickerButton,
    Header1,
    Header2,
)
from minecraftlauncher.front.qt.validator import (
    ProfileRAMValidator,
    ProfileResolutionTextValidator,
    VersionTextValidator,
    FilePathValidator,
    QValidatorWithStoredResults,
)
from minecraftlauncher.front.window import (
    WarningDialog,
    WarningType,
    ButtonConfig,
)
from minecraftlauncher.functions import copy_to_clipboard, is_path_valid
from minecraftlauncher.ostools import set_jump_list

LOGGER = logging.getLogger(__name__)

COMMON_RESOLUTIONS = [
    (854, 480),
    (1280, 720),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
    (3840, 2160),
]

MapIndex = ProfileModel.MapIndex


def _right_click_decorator(func):
    _func = func

    def decorated_func(e: QEvent | QMouseEvent | None):
        if not isinstance(e, QMouseEvent):
            return _func(e)
        if e.buttons() & Qt.MouseButton.RightButton:
            return None
        return _func(e)

    return decorated_func


class ProfilesPage(QWidget):
    """Profiles page"""

    status_update = Signal(str)

    # Instance attributes
    _dirty: bool
    save_shortcut: QShortcut

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dirty = False
        self.mapper = CustomMapper(self)
        self.mapper.changes_made.connect(self._set_dirty)
        _seq = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_S)  # type: ignore
        self.save_shortcut = QShortcut(_seq, self)
        self.save_shortcut.activated.connect(self.mapper.save)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        left = QWidget()
        left.setFixedWidth(250)

    def refresh(self):
        self.mapper.reset()

    def _set_dirty(self, dirty: bool):
        self._dirty = dirty
