"""
minecraftlauncher.front.window.main.profiles_page

Profile management page.

TODOs:
- Rework the editor state check (clean/dirty)
- Possibly replace the default Qt mapper with the custom one used by
  settings_page
- Find a way to make "latest-release" and "latest-snapshot" use friendlier names
- Are colored save/delete buttons really necessary here?
"""

from pathlib import Path
import logging

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from launcher import constants
from launcher.back import profile_manager
from launcher.back.profile_manager import (
    LaunchProfile,
)
from launcher.front import resources, styles
from launcher.front.qt.widgets.profile_editor import ProfileEditor
from launcher.front.qt.widgets.profile_list import ProfileList
from launcher.front.window import (
    ButtonConfig,
    WarningDialog,
    WarningType,
)

log = logging.getLogger(__name__)

# TODO: calculate resolutions instead of statically setting them
COMMON_RESOLUTIONS = [
    (854, 480),
    (1280, 720),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
    (3840, 2160),
]


class ProfilesPage(QWidget):
    """Profile page"""

    status_update = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.log = log.getChild("ProfilesPage")
        self._dirty = False
        self._loaded = False
        self._validity_state = True
        self._build_ui()
        if constants.OS != "osx":
            key_seq = QKeySequence(
                Qt.Modifier.CTRL | Qt.Key.Key_S  # type: ignore
            )
        else:
            key_seq = QKeySequence(
                Qt.Modifier.META | Qt.Key.Key_S  # type: ignore
            )
        shortcut = QShortcut(key_seq, self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)

    def build(self):
        self._loaded = True

    def load(self): ...

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        #
        # Left-side layout
        #
        left = QWidget()
        left.setFixedWidth(250)
        left_layout = QVBoxLayout(left)
        # TODO: find out why 19 specifically, what's adding 1 px of margin??
        left_layout.setContentsMargins(19, 19, 19, 19)
        left.setBackgroundRole(styles.CRole.Mid)
        left.setAutoFillBackground(True)

        self._profile_list = ProfileList()
        left_layout.addWidget(self._profile_list)
        layout.addWidget(left)

        # separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        layout.addWidget(sep)

        #
        # Right-side/editor
        #
        self.editor = ProfileEditor(self)

        layout.addWidget(self.editor, 1)

    def _new_profile(self):
        prof = profile_manager.create_profile()
        profile_manager.set_current_profile(prof)

    def _delete_profile(self, profile: LaunchProfile | None = None):
        if not profile:
            profile = profile_manager.get_current_profile()
        confirmation = WarningDialog.warn(
            self,
            "Delete Profile?",
            f'Are you sure you want to delete the profile "{profile.name}"?',
            WarningType.DELETE_PROFILE,
            button_config=ButtonConfig.YES_NO,
        )
        if confirmation:
            log.info(
                "Deleting profile '%s' (ID: %s)", profile.name, profile.uuid
            )
            profile_manager.delete_single_profile(profile)
            del profile

    def _export_prof_icon(self, prof: LaunchProfile | None = None):
        if not prof:
            prof = profile_manager.get_current_profile()
        if not prof.icon:
            return
        str_path, _ = QFileDialog.getSaveFileName(
            self, "Save file", "", "PNG Image (*.png);;All Files (*)"
        )
        if not str_path:
            return
        path = Path(str_path)
        if not path.parent.exists():
            return
        log.debug("Saving profile icon to '%s'", str_path)
        ico = resources.profile_icon(prof.icon)
        img = ico.pixmap(ico.actualSize(QSize(99999, 99999))).toImage()
        img.save(str_path)

    def _clone_profile(self, prof: LaunchProfile | None = None):
        if not prof:
            prof = profile_manager.get_current_profile()
        new = prof.copy()
        profile_manager.save_single_profile(new)
