"""
minecraftlauncher.front.qt.widgets.profile_editor

Profile management page rewritten to use CustomMapper instead of Qt's mapper

Editor pane
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
from launcher.front.window import (
    ButtonConfig,
    WarningDialog,
    WarningType,
)
from launcher.functions import copy_to_clipboard, is_path_valid
from launcher.ostools import set_jump_list

from . import Header1, Header2, IconPickerButton

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
    profile: LaunchProfile

    def __init__(self, profile: LaunchProfile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setBackgroundRole(styles.CRole.Base)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
