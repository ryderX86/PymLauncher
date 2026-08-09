"""
minecraftlauncher.front.qt.widgets.profile_editor

Profile management page rewritten to use CustomMapper instead of Qt's mapper

Editor pane
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

from . import IconPickerButton, Header1, Header2

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


class ProfileEditor(QWidget):

    # instance attributes
    profile: GameProfile

    def __init__(self, profile: GameProfile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setBackgroundRole(styles.CRole.Base)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
