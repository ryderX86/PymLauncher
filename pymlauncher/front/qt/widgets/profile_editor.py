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

from pymlauncher import config, constants
from pymlauncher.back import profile_manager, version_manager
from pymlauncher.datatypes import LaunchProfile
from pymlauncher.datatypes.game_version import GameVersionStub
from pymlauncher.front import resources, styles
from pymlauncher.front.qt import CustomMapper
from pymlauncher.front.qt.models import (
    ProfileModel,
    ProfileSelectionModel,
)
from pymlauncher.front.qt.validator import (
    FilePathValidator,
    ProfileRAMValidator,
    ProfileResolutionTextValidator,
    QValidatorWithStoredResults,
    VersionTextValidator,
)
from pymlauncher.front.window import (
    ButtonConfig,
    WarningDialog,
    WarningType,
)
from pymlauncher.functions import copy_to_clipboard, is_path_valid
from pymlauncher.ostools import set_jump_list

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
