"""
minecraftlauncher.front.window.main.home_page

Home page, play button, profile info, progress bar, all that stuff.
"""
from pathlib import Path
from time import sleep
import logging
import subprocess

import requests

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QItemSelection, QSize
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QVBoxLayout, QWidget, QComboBox)

from minecraftlauncher.functions.error_box import error_box
from minecraftlauncher.back.profile_manager import GameProfile
from minecraftlauncher.back import (version_manager, asset_manager,
                                    java_manager, library_manager,
                                    game_launcher, profile_manager,
                                    account_manager)
from minecraftlauncher.exceptions.datatypes import InvalidVersionIdError
from minecraftlauncher.constants import MINECRAFT_DIR, offline_mode
from minecraftlauncher.datatypes.LauncherProfile import LauncherProfile
from minecraftlauncher.front import styles, resources
from minecraftlauncher.front.qt.models import ProfileSelectionModel

log = logging.getLogger(__name__)

class LaunchWorker(QThread):
    """Background worker for downloading game files and launching."""

    progress = Signal(str, int, int) # step label, current, total
    finished = Signal(bool, str) # successful, message
    status = Signal(str) # status text
    game_closed = Signal(str, str)
    """
    `[0]` (`int`) - Exit code<br>
    `[1]` (`str`) - stdout<br>
    `[2]` (`str`) - stderr
    """

    log = log.getChild("LaunchWorker")

    def __init__(self, version_id:str, profile_data:GameProfile,
                 auth_info:LauncherProfile, parent=None):
        super().__init__(parent)
        self.version_id = version_id
        self.profile_data = profile_data
        self.auth_info = auth_info

    def run(self):
        match self.version_id:
            case "latest-release":
                self.version_id = version_manager.get_latest_release()
            case "latest-snapshot":
                self.version_id = version_manager.get_latest_snapshot()
        
        self.status.emit("Fetching version info...")
        version_json = version_manager.fetch_version_json(self.version_id)
        version_json = version_manager.resolve_inheritence(version_json)
        
        self.status.emit("Downloading client JAR...")
        jar_path = version_manager.download_client_jar(
            version_json,
            progress_callback=lambda c, t: self.progress.emit(
                f"{self.version_id}.jar", c, t
            )
        )

        self.status.emit("Checking for assets...")
        asset_index = asset_manager.filter_assets_downloads(
            asset_manager.fetch_asset_index(version_json),
            progress_callback=lambda c, t: self.progress.emit(
                "Checking assets", c, t
            )
        )
        if len(asset_index.get("objects", {}).keys()) > 0:
            self.status.emit("Downloading assets...")
            asset_manager.download_assets_threaded(
                asset_index,
                progress_callback=lambda c, t: self.progress.emit(
                    "Downloading assets", c, t
                )
            )
        
        self.status.emit("Checking log4j config file...")
        log4j_config = asset_manager.check_or_download_logging_config(
            version_json
        )

        self.status.emit("Downloading libraries...")
        libs = library_manager.filter_libraries(version_json)
        library_manager.download_libraries(
            libs,
            progress_callback=lambda c, t: self.progress.emit(
                "Downloading libraries", c, t
            )
        )
        library_manager.download_natives(libs)
        natives_dir = MINECRAFT_DIR / "bin" / self.version_id
        natives_dir = library_manager.extract_natives(libs, natives_dir)

        self.status.emit("Checking for Java install...")
        profile_jre = self.profile_data.java_path
        if profile_jre:
            try:
                success = subprocess.run(
                    [profile_jre.replace("javaw", "java"), "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            except subprocess.CalledProcessError as err:
                self.log.error("Java exited with code %d:\n%s"
                               % (err.returncode, str(err.output)))
                self.log.info("Aborting launch, and notifying user of invalid "
                              "JRE location.")
                self.finished.emit(False, str(err.output))
                return
            else:
                java_exc = Path(profile_jre)
        else:
            jre_name = version_json.get("javaVersion", {}).get("component", "")
            jre_manifest = java_manager.get_jvm_version_manifest(jre_name)
            if not offline_mode:
                java_exc = java_manager.install_java_version(jre_name,
                                                            jre_manifest)
            else:
                self.log.warning("Offline mode active, JRE executable may be "
                                 "broken!")
                try:
                    java_exc = java_manager.find_java_exc(jre_name)
                except RuntimeError as err:
                    self.log.error("Failed to find JRE installation!",
                                   exc_info=err)
                    self.finished.emit(False, str(err))
                    return

        classpath = library_manager.build_classpath(libs, jar_path)

        if not self.auth_info.token_valid:
            self.log.warning("User account doesn't have a valid token, "
                             "trying to refresh...")
            self.status.emit("Reauthenticating...")
            try:
                self.auth_info.minecraft_auth()
            except RuntimeError as err:
                self.log.error("Failed to authenticate account, aborting "
                               "launch.", exc_info=err)
                self.finished.emit(False, str(err.__notes__))
                return
            except requests.RequestException as err:
                self.log.error("Failed to authenticate account (are we "
                               "offline?):", exc_info=err)
                self.finished.emit(False, str(err))
                return
        assert self.auth_info.token
        if not self.auth_info.profile:
            try:
                self.auth_info.get_profile_info()
            except Exception as err:
                self.log.error("Failed to fetch profile info (are we "
                               "offline?)", exc_info=err)
                self.finished.emit(False, str(err))
                return
            else:
                assert self.auth_info.profile
        
        account_manager.save_or_replace_account(self.auth_info)
                
        self.status.emit("Launching Minecraft...")
        cmd = game_launcher.build_launch_command(
            version_json, self.auth_info.profile.name,
            self.auth_info.profile.uuid, self.auth_info.token.access_token,
            self.auth_info.player_type, self.auth_info.demo_mode,
            None, str(java_exc), log4j_config, classpath,
            self.profile_data.game_dir, self.profile_data.jvm_args,
            self.profile_data.memory_min,
            self.profile_data.memory_max,
            self.profile_data.resolution_width,
            self.profile_data.resolution_height,
            self.profile_data.mods_folder,
            self.profile_data.mods_folder_mode
        )
        logged_cmd = " ".join(cmd).replace(self.auth_info.token.access_token,
                                           "TOKEN")
        self.log.info("Launch command: '%s'" % logged_cmd)

        sub_logger = logging.getLogger(Path(cmd[0]).name)
        self._p = game_launcher.launch_game(cmd,
                                            cwd=self.profile_data.game_dir)
        self.finished.emit(True, "Minecraft launched successfully.")

        # reverse this when reading:
        stdout_cache:list[str] = []

        if self._p.stdout:
            for line in iter(self._p.stdout.readline, ""):
                sub_logger.debug(
                    line[:-1] # skip newline
                )
                stdout_cache.insert(0, line[:-1])

                # memory usage
                self._p.stdout.flush()
                stdout_cache = stdout_cache[:255] # 256 lines
        self._p.wait()

        stdout_cache.reverse()
        stdout = "\n".join(stdout_cache)

        self.log.debug("Returned with code %d" % self._p.returncode)
        self.game_closed.emit(
            str(self._p.returncode),
            stdout
        )

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection_model = ProfileSelectionModel.instance()
        self._worker:LaunchWorker|None = None
        self._no_icon = QIcon().pixmap(QSize(32, 32))
        self._build_ui()
        self.profile_needs_install:bool = True

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

        title = QLabel("Home")
        title.setProperty("heading", True)
        layout.addWidget(title)

        # profile info stuff
        info_frame = QFrame()
        info_frame.setProperty("surface", True)
        # info_frame.setStyleSheet(
        #     f"background-color: {styles.BG_SURFACE}; "
        #     f"border: 1px solid {styles.BORDER}; "
        #     "border-radius: 10px; padding 20px;"
        # )
        info_layout = QVBoxLayout(info_frame)
        info_frame.setContentsMargins(0, 0, 0, 2)

        info_sub_frame = QFrame()
        info_sub_layout = QHBoxLayout(info_sub_frame)

        info_sub_layout.addWidget(
            QLabel("Profile: "), 0
        )

        info_sub_layout.setContentsMargins(10,4,10,0)

        self.profile_dropdown = QComboBox()
        self.profile_dropdown.activated.connect(self._on_dropdown_select)
        self.selection_model.currentChanged.connect(self._on_global_profile)
        profile_manager.add_profile_refresh_handler(
            self._refresh_profiles
        )
        self.profile_dropdown.setIconSize(QSize(32, 32))
        self.profile_dropdown.setProperty("bigIcons", True)
        self.profile_dropdown.setMaxVisibleItems(6)
        info_sub_layout.addWidget(self.profile_dropdown, 1)

        info_layout.addWidget(info_sub_frame)

        layout.addWidget(info_frame)

        layout.addStretch()

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
        open_mods_button.clicked.connect(
            lambda: self._open_prof_folder("mods")
        )
        open_mods_button.setProperty("mini", True)
        profile_action_row.addWidget(open_mods_button, 0)

        open_screenshots_button = QPushButton("Screenshots")
        open_screenshots_button.clicked.connect(
            lambda: self._open_prof_folder("screenshots")
        )
        open_screenshots_button.setProperty("mini", True)
        profile_action_row.addWidget(open_screenshots_button, 0)

        profile_action_row.addStretch()

        self.version_label = QLabel("Version: [unknown]")
        self.version_label.setStyleSheet(
            f"font-size: 13px; color: {styles.TEXT_SECONDARY};"
        )
        self.version_label.setContentsMargins(10,0,10,0)
        info_layout.addWidget(self.version_label)

        # Progress bar
        self.progress_frame = QFrame()
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {styles.TEXT_SECONDARY};")
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
        play_layout.setProperty("surface", True)
        play_layout.addWidget(self.play_button, 0,
                              Qt.AlignmentFlag.AlignCenter)
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
                self.profile_dropdown.addItem(
                    ico,
                    prof.name or prof.uuid,
                    prof
                )
            else:
                self.profile_dropdown.addItem(
                    self._no_icon,
                    prof.name or prof.uuid,
                    prof
                )
            if prof == current:
                self.profile_dropdown.setCurrentIndex(
                    profs.index(current)
                )
    
    def _on_dropdown_select(self, index:int):
        prof:GameProfile = self.profile_dropdown.itemData(index)
        current_prof = profile_manager.get_current_profile()
        if prof != current_prof:
            self.selection_model.setCurrentIndex(
                self.selection_model.model().index(index, 0),
                self.selection_model.SelectionFlag.ClearAndSelect
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

    def _on_global_profile(self, current:QItemSelection,
                           previous:QItemSelection):
        if current.isValid(): # type: ignore
            self.profile_dropdown.blockSignals(True)
            self.profile_dropdown.setCurrentIndex(
                current.row() # type: ignore
            )
            self.profile_dropdown.blockSignals(False)
        row:int = current.row() # type: ignore
        profile = profile_manager.get_profile(row)
        self._profile_change(profile)

    def _profile_change(self, profile:GameProfile):
        try:
            prof_exists = profile.check_install()
        except InvalidVersionIdError:
            self.progress_label.setText(
                "Unknown game version: %s" % profile.version_id
            )
            self.play_button.setText("Invalid version")
            self.play_button.setDisabled(True)
            return
        if prof_exists:
            self.progress_label.setText("Ready to launch.")
            self.play_button.setText("Launch Game")
            self.play_button.setDisabled(False)
        else:
            self.progress_label.setText("Ready to install.")
            self.play_button.setText("Install %s" % profile.real_version_id)
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

    def install_launch_game(self, version_id:str,
                            profile_data:GameProfile,
                            auth_info:LauncherProfile):
        """Start download/launch process in a background thread"""
        log.debug("Preparing to install/launch game...")
        self.progress_bar.setValue(0)
        self.progress_frame.setVisible(True)

        self._worker = LaunchWorker(version_id, profile_data, auth_info)
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self._on_status)
        self._worker.finished.connect(self._on_finished)
        self._worker.game_closed.connect(self._on_game_closed)
        log.debug("Starting background worker for install...")
        self._worker.start()

    def _on_progress(self, label:str, current:int, total:int):
        if total > 0:
            progress = int(current/total*100)
            self.progress_bar.setValue(progress)
            self.progress_label.setText(f"{label}: {current}/{total}")
    
    def _on_status(self, text:str):
        self.progress_label.setText(text)

    def _on_game_closed(self, exit_code:str, stdout:str):
        if int(exit_code) == 0:
            self.game_closed.emit("0")
        else:
            self.game_closed.emit(exit_code)
        self.play_button.setEnabled(True)
        # we WILL have profiles by this point or i deserve the crash this will
        # allow
        prof = profile_manager.get_current_profile()
        assert prof
        self._profile_change(prof)
        if int(exit_code) != 0:
            self.game_crash.emit(exit_code, stdout)
        self.kill_worker()

    def _open_prof_folder(self, folder:str|None=None):
        prof = profile_manager.get_current_profile()
        if prof.game_dir:
            p = Path(prof.game_dir)
        else:
            p = MINECRAFT_DIR

        if not p.exists():
            error_box("Profile directory doesn't exist yet!")
            return

        match folder:
            case "rp":
                p = p / "resourcepacks" # TODO: texturepacks dir for old ver
            case "mods":
                if (prof.mods_folder
                    and prof.mods_folder_mode != "addMods"):
                    p = Path(prof.mods_folder)
                else:
                    p = p / "mods"
            case "world":
                p = p / "saves"
            case "screenshots":
                p = p / "screenshots"

        # check again for subfolders
        if not p.exists():
            if p.parent.exists():
                log.warning("Folder at '%s' doesn't exist, trying to create it."
                            % str(p))
                try:
                    p.mkdir(parents=False, exist_ok=True)
                except Exception as err:
                    log.error("Failed to make directory. Notifying user and "
                              "returning.", exc_info=err)
                    error_box("Failed to open folder. Does it exist?")
                    return
        qurl = QUrl.fromLocalFile(str(p))
        QDesktopServices.openUrl(qurl)
    
    def _on_finished(self, success:bool, message:str):
        if success:
            self.play_button.setText("Playing...")
            self.play_button.setEnabled(False)
            self.progress_frame.setVisible(False)
            self.progress_label.setText("")
            self.progress_bar.setValue(0)
            self.game_open.emit()
        else:
            error_box("Launch failed: %s" % message)
            prof = profile_manager.get_current_profile()
            assert prof
            self._profile_change(prof)