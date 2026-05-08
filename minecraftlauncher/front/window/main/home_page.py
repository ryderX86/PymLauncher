"""
minecraftlauncher.front.window.main.home_page

Home page, play button, profile info, progress bar, all that stuff.
"""

import logging
import os

from PySide6.QtCore import Qt, Signal, QUrl, QItemSelection, QSize
from PySide6.QtGui import QDesktopServices, QIcon, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QPlainTextEdit,
    QListView,
)

from minecraftlauncher.functions import error_box, is_path_valid
from minecraftlauncher.back.profile_manager import GameProfile
from minecraftlauncher.back.game_launcher import LaunchWorker
from minecraftlauncher.back import profile_manager
from minecraftlauncher.exceptions.datatypes import InvalidVersionIdError
from minecraftlauncher.constants import MINECRAFT_DIR
from minecraftlauncher.auth import LauncherAccount
from minecraftlauncher.front import resources
from minecraftlauncher.front.qt.models import ProfileSelectionModel
from minecraftlauncher.front.qt.widgets import Header1, SecondaryLabel
from minecraftlauncher.front.styles import TERMINAL_FONT
from minecraftlauncher import config, offline_mode

log = logging.getLogger(__name__)


class HomePage(QWidget):
    """Home/Play button page"""

    play_requested = Signal()
    game_crash = Signal(str, str)
    """
    `[0]` (`str`) - Exit code<br>
    `[1]` (`str`) - stderr
    """
    game_open = Signal()
    game_closed = Signal(str)
    status_update = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection_model = ProfileSelectionModel.instance()
        self._worker: LaunchWorker | None = None
        self._no_icon = QIcon().pixmap(QSize(32, 32))
        self._build_ui()
        self.profile_needs_install: bool = True

    def build(self):
        pass

    def kill_worker(self):
        if self._worker:
            log.debug("self._worker.deleteLater()")
            self._worker.deleteLater()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        title = Header1("Home")
        # title.setProperty("heading", True)
        layout.addWidget(title)

        # profile info stuff
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        info_frame.setFrameShadow(QFrame.Shadow.Plain)
        info_frame.setLineWidth(1)
        # info_frame.setStyleSheet(
        #     f"background-color: {styles.BG_SURFACE}; "
        #     f"border: 1px solid {styles.BORDER}; "
        #     "border-radius: 10px; padding 20px;"
        # )
        info_layout = QVBoxLayout(info_frame)

        info_sub_frame = QFrame()
        info_sub_layout = QHBoxLayout(info_sub_frame)

        info_sub_layout.addWidget(QLabel("Profile: "), 0)

        info_sub_layout.setContentsMargins(10, 4, 10, 0)

        self.profile_dropdown = QComboBox()
        self.profile_dropdown.setStyleSheet(
            " ".join(
                [
                    self.profile_dropdown.styleSheet(),
                    "::item {min-height: 48px;}",
                ]
            )
        )
        self.profile_dropdown.view().setVerticalScrollMode(
            QListView.ScrollMode.ScrollPerPixel
        )
        self.profile_dropdown.activated.connect(self._on_dropdown_select)
        self.selection_model.currentChanged.connect(self._on_global_profile)
        profile_manager.add_profile_refresh_handler(self._refresh_profiles)
        self.profile_dropdown.setIconSize(QSize(32, 32))
        self.profile_dropdown.setProperty("bigIcons", True)
        self.profile_dropdown.setMaxVisibleItems(6)
        info_sub_layout.addWidget(self.profile_dropdown, 1)

        info_layout.addWidget(info_sub_frame)

        layout.addWidget(info_frame)

        # profile options
        profile_action_frame = QFrame()
        profile_action_row = QHBoxLayout(profile_action_frame)
        info_layout.addWidget(profile_action_frame)

        action_label = QLabel("Profile Folders:")
        action_label.setMargin(1)
        profile_action_row.addWidget(action_label)

        open_folder_button = QPushButton("Game")
        open_folder_button.setProperty("mini", True)
        open_folder_button.clicked.connect(self._open_prof_folder)
        profile_action_row.addWidget(open_folder_button, 0)

        open_rp_button = QPushButton("Resource Packs")
        open_rp_button.setProperty("mini", True)
        open_rp_button.clicked.connect(lambda: self._open_prof_folder("rp"))
        profile_action_row.addWidget(open_rp_button, 0)

        open_save_button = QPushButton("Worlds")
        open_save_button.clicked.connect(
            lambda: self._open_prof_folder("world")
        )
        open_save_button.setProperty("mini", True)
        profile_action_row.addWidget(open_save_button, 0)

        open_mods_button = QPushButton("Mods")
        open_mods_button.clicked.connect(lambda: self._open_prof_folder("mods"))
        open_mods_button.setProperty("mini", True)
        profile_action_row.addWidget(open_mods_button, 0)

        open_screenshots_button = QPushButton("Screenshots")
        open_screenshots_button.clicked.connect(
            lambda: self._open_prof_folder("screenshots")
        )
        open_screenshots_button.setProperty("mini", True)
        profile_action_row.addWidget(open_screenshots_button, 0)

        open_versions_button = QPushButton("Versions")
        open_versions_button.clicked.connect(
            lambda: self._open_prof_folder("versions")
        )
        open_versions_button.setProperty("mini", True)
        profile_action_row.addWidget(open_versions_button, 0)

        profile_action_row.addStretch()

        self.version_label = SecondaryLabel("Version: [unknown]")
        self.version_label.setContentsMargins(10, 0, 10, 0)
        self.version_label.setOpenExternalLinks(True)
        info_layout.addWidget(self.version_label)

        self.game_logs = QPlainTextEdit(
            tabChangesFocus=False,
            undoRedoEnabled=False,
            lineWrapMode=QPlainTextEdit.LineWrapMode.WidgetWidth,
            readOnly=True,
            plainText="*taps mic* This thing on?",
            centerOnScroll=False,
        )
        self.game_logs.setBackgroundRole(QPalette.ColorRole.Dark)
        self.game_logs.setFont(TERMINAL_FONT)
        self.game_logs.setMaximumBlockCount(5000)  # change if needed

        info_layout.addWidget(self.game_logs)

        self.stretcher = QWidget()
        stretcher_lo = QVBoxLayout(self.stretcher)
        stretcher_lo.addStretch()
        layout.addWidget(self.stretcher)

        if config.show_logs_on_home:
            self.stretcher.setHidden(True)
        else:
            self.game_logs.setHidden(True)

        # Progress bar
        self.progress_frame = QFrame()
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_label = QLabel("")
        self.progress_label.setForegroundRole(
            QPalette.ColorRole.PlaceholderText
        )
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.progress_frame.setVisible(False)
        layout.addWidget(self.progress_frame)

        # Play button
        self.play_button = QPushButton("Loading...")
        self.play_button.setProperty("play", True)
        self.play_button.setFixedHeight(50)
        self.play_button.setMinimumWidth(280)
        self.play_button.clicked.connect(self._on_play)
        self.play_button.setDisabled(True)

        play_layout = QHBoxLayout()
        play_layout.addWidget(self.play_button, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(play_layout)

    def _refresh_profiles(self):
        profs = [*profile_manager.profiles.values()]
        current = profile_manager.get_current_profile()
        if not current:
            log.warning("Cannot get current profile! Aborting refresh.")
            return
        self.profile_dropdown.clear()
        for prof in profs:
            if prof.icon:
                ico = resources.profile_icon(prof.icon)
                self.profile_dropdown.addItem(ico, prof.name or prof.uuid, prof)
            else:
                self.profile_dropdown.addItem(
                    self._no_icon, prof.name or prof.uuid, prof
                )
            if prof == current:
                self.profile_dropdown.setCurrentIndex(profs.index(current))

    def _on_dropdown_select(self, index: int):
        prof: GameProfile = self.profile_dropdown.itemData(index)
        current_prof = profile_manager.get_current_profile()
        if prof != current_prof:
            self.selection_model.setCurrentIndex(
                self.selection_model.model().index(index, 0),
                self.selection_model.SelectionFlag.ClearAndSelect,
            )
            # handle what happens if the pop-up is cancelled/ignored
            if self.selection_model.currentIndex().row() != index:
                log.debug("Looks like user aborted the change?")
                self.profile_dropdown.blockSignals(True)
                self.profile_dropdown.setCurrentIndex(
                    self.selection_model.currentIndex().row()
                )
                self.profile_dropdown.blockSignals(False)
                return

    def _on_global_profile(
        self, current: QItemSelection, previous: QItemSelection
    ):
        if current.isValid():  # type: ignore
            self.profile_dropdown.blockSignals(True)
            self.profile_dropdown.setCurrentIndex(current.row())  # type: ignore
            self.profile_dropdown.blockSignals(False)
        row: int = current.row()  # type: ignore
        profile = profile_manager.get_profile(row)
        self._profile_change(profile)

    def _profile_change(self, profile: GameProfile):
        try:
            prof_exists = profile.check_install()
        except InvalidVersionIdError:
            self.progress_label.setText(
                f"Unknown game version: {profile.version_id}"
            )
            self.play_button.setText("Invalid version")
            self.play_button.setDisabled(True)
            return
        if prof_exists:
            if not offline_mode:
                self.play_button.setText("Launch Game")
            else:
                self.play_button.setText("Launch Game (offline)")
            self.progress_label.setText("Ready to launch.")
            self.play_button.setDisabled(False)
        else:
            self.progress_label.setText("Ready to install.")
            self.play_button.setText(f"Install {profile.real_version_id}")
            self.play_button.setDisabled(offline_mode)
        self.version_label.setText(f"Version: {profile.version_id}")

    def _on_play(self):
        """Play button function"""
        self.play_button.setDisabled(True)
        prof = profile_manager.get_current_profile()
        if prof.check_install():
            self.play_button.setText("Preparing...")
        else:
            self.play_button.setText("Installing...")
        self.play_requested.emit()

    def install_launch_game(
        self,
        version_id: str,
        profile_data: GameProfile,
        auth_info: LauncherAccount,
    ):
        """Start download/launch process in a background thread"""
        log.debug("Preparing to install/launch game...")
        self.progress_bar.setValue(0)
        self.progress_frame.setVisible(True)
        show_logs = config.show_logs_on_home

        self._worker = LaunchWorker(
            version_id, profile_data, auth_info, emit_logs=show_logs
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self._on_status)
        self._worker.finished.connect(self._on_finished)
        self._worker.game_closed.connect(self._on_game_closed)
        if show_logs:
            log.debug("Starting game with logs shown")
            self._worker.game_log.connect(self._handle_game_log)
        self.game_logs.clear()
        log.debug("Starting background worker for install...")
        self._worker.start()

    def _on_progress(
        self, label: str, current: float, total: float, use_mb: bool
    ):
        if total > 0:
            progress = int(current / total * 100)
            self.progress_bar.setValue(progress)
            if use_mb:
                self.progress_label.setText(f"{label}: {current}MB/{total}MB")
            else:
                self.progress_label.setText(
                    f"{label}: {int(current)}/{int(total)}"
                )

    def _on_status(self, text: str):
        self.progress_label.setText(text)

    def _on_game_closed(self, exit_code: str, stdout: str):
        if int(exit_code) == 0:
            self.game_closed.emit("0")
        else:
            self.game_closed.emit(exit_code)
        self.play_button.setEnabled(True)
        # we WILL have profiles by this point or i deserve the crash this will
        # allow
        prof = profile_manager.get_current_profile()
        prof.set_last_used()
        self._profile_change(prof)
        if int(exit_code) != 0:
            self.game_crash.emit(exit_code, stdout)
        self.kill_worker()

    def _open_prof_folder(self, folder: str | None = None):
        p: str | os.PathLike
        prof = profile_manager.get_current_profile()
        if prof.game_dir:
            if not is_path_valid(prof.game_dir):
                error_box(f"Bad game directory: {prof.game_dir!r}")
            p = prof.game_dir
        else:
            p = MINECRAFT_DIR

        if not os.path.isdir(p):
            error_box("Profile directory doesn't exist yet!")
            return

        match folder:
            case "rp":
                if not os.path.isdir(
                    os.path.join(p, "resourcepacks")
                ) and os.path.isdir(os.path.join(p, "texturepacks")):
                    p = os.path.join(p, "texturepacks")
                else:
                    p = os.path.join(p, "resourcepacks")
            case "mods":
                if prof.mods_folder and prof.mods_folder_mode != "addMods":
                    if not is_path_valid(prof.mods_folder):
                        error_box(f"Bad mods folder path: {prof.mods_folder!r}")
                        return
                    p = os.path.normpath(prof.mods_folder)
                else:
                    p = os.path.join(p, "mods")
            case "world":
                p = os.path.join(p, "saves")
            case "screenshots":
                p = os.path.join(p, "screenshots")
            case "versions":
                p = os.path.join(MINECRAFT_DIR, "versions")

        # check again for subfolders
        if not os.path.isdir(p):
            log.debug(
                "Folder at '%s' doesn't exist, trying to create it.", str(p)
            )
            try:
                os.makedirs(p, exist_ok=True)
            except Exception as err:
                log.error(
                    "Failed to make directory. Notifying user and returning.",
                    exc_info=err,
                )
                error_box(
                    f"Failed to make folder {p!r}. Do you have permissions?"
                )
                return
        qurl = QUrl.fromLocalFile(p)
        QDesktopServices.openUrl(qurl)

    def _on_finished(self, success: bool, message: str):
        if success:
            self.play_button.setText("Playing...")
            self.play_button.setEnabled(False)
            self.progress_frame.setVisible(False)
            self.progress_label.setText("")
            self.progress_bar.setValue(0)
            self.game_open.emit()
        else:
            error_box(f"Failed to launch the game: {message}")
            prof = profile_manager.get_current_profile()
            self._profile_change(prof)

    def config_changed(self):
        self.game_logs.setHidden(not config.show_logs_on_home)
        self.stretcher.setHidden(config.show_logs_on_home)
        if not config.show_logs_on_home:
            if self.game_logs.blockCount() > 1:
                log.debug(
                    "Resetting home page game logs due to option being "
                    "unchecked"
                )
                self.game_logs.setPlainText("*taps mic* This thing on?")

    def _handle_game_log(self, log_text: str):
        self.game_logs.appendPlainText(log_text)
