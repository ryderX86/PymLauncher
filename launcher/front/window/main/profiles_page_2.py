"""
minecraftlauncher.front.window.main.profiles_page_2

Profile management page rewritten to use CustomMapper instead of Qt's mapper
"""

import logging
import os
import time

from PySide6.QtCore import QEvent, QSize, Qt, QThread, Signal
from PySide6.QtGui import (
    QAction,
    QContextMenuEvent,
    QKeySequence,
    QMouseEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDataWidgetMapper,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher import config, constants
from launcher.back import profile_manager, version_manager
from launcher.datatypes import LaunchProfile
from launcher.datatypes.game_version import GameVersionStub
from launcher.front import resources, styles
from launcher.front.qt import CustomMapper
from launcher.front.qt.models import (
    ProfileModel,
    ProfileSelectionModel,
)
from launcher.front.qt.validator import (
    FilePathValidator,
    ProfileRAMValidator,
    ProfileResolutionTextValidator,
    QValidatorWithStoredResults,
    VersionTextValidator,
)
from launcher.front.qt.widgets import (
    Header1,
    Header2,
    IconPickerButton,
)
from launcher.front.window import (
    ButtonConfig,
    WarningDialog,
    WarningType,
)
from launcher.functions import copy_to_clipboard, is_path_valid
from launcher.ostools import set_jump_list

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
