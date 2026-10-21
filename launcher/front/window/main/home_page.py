"""
minecraftlauncher.front.window.main.home_page

Home page, play button, profile info, progress bar, all that stuff.
"""

from types import NoneType
import logging
import os
import time

from PySide6.QtCore import QSize, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher import config, constants, lifecycle, paths
from launcher.auth import LauncherAccount
from launcher.back import profile_manager
from launcher.back.account_manager import account_man
from launcher.back.game_installer import installer
from launcher.back.profile_manager import LaunchProfile
from launcher.exceptions.datatypes import InvalidVersionIdError
from launcher.front.qt.binding_mixin import BindingMixin
from launcher.front.qt.widgets import Header1, SecondaryLabel
from launcher.front.styles import get_fonts
from launcher.front.theming import theme_manager
from launcher.front.window.text_popup import TextPopup
from launcher.functions import error_box, is_path_valid
from launcher.offline import offline_man

log = logging.getLogger(__name__)
log_tmp = config.logging_template or constants.DEFAULT_LOG_TEMPLATE
log_tmp_type = config.determine_log_template_format(log_tmp)[0]


class HomePage(BindingMixin, QWidget):
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
        self.fonts = get_fonts()
        self._no_icon = QIcon().pixmap(QSize(32, 32))
        self._build_ui()
        self.profile_needs_install: bool = True

    def build(self):
        pass

    def bind(self):
        self._reset_progress_bar_sizes()
        lifecycle.config_updated.connect(self._reset_progress_bar_sizes)
        lifecycle.config_updated.connect(self.config_changed)

        installer.starting.connect(self._on_installer_starting)
        installer.finished.connect(self.on_install_finished)
        installer.step.connect(self._on_installer_step)
        installer.downloaded_file.connect(self._on_downloaded_file)
        installer.update_bytes.connect(self._step_progress_bar)
        self.config_changed()

    @Slot(int)
    def _step_progress_bar(self, amount: int):
        self.progress_bar.setValue(self.progress_bar.value() + amount)

    @Slot()
    def _on_installer_starting(self):
        # use globals to avoid some(?) attribute lookup, since formatting is
        # going to be slow enough as-is.
        global log_tmp, log_tmp_type
        log_tmp_type = config.determine_log_template_format(log_tmp)[0]
        if log_tmp_type != config.GameLogTemplateType.UNKNOWN:
            log_tmp = config.logging_template or constants.DEFAULT_LOG_TEMPLATE
        else:
            log_tmp = constants.DEFAULT_LOG_TEMPLATE
            log_tmp_type = config.GameLogTemplateType.DEFAULT
        self.progress_bar.setValue(0)
        self.progress_label.setText("")
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        if config.show_logs_on_home:
            self.game_logs.clear()

    @Slot(str, str, int)
    def _on_installer_step(self, progress_bar_msg: str, _: str, total: int):
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(total)
        self.progress_label.setText(progress_bar_msg)

    @Slot(str, int)
    def _on_downloaded_file(self, _: str, size: int):
        self.progress_bar.setValue(self.progress_bar.value() + size)

    @Slot()
    def _reset_progress_bar_sizes(self):
        self.progress_label.setVisible(True)
        plh = self.progress_label.sizeHint().height()
        self.progress_label.setVisible(False)
        self.progress_bar.setVisible(True)
        pbh = self.progress_bar.sizeHint().height()
        self.progress_bar.setVisible(False)

        margins = self.progress_frame.contentsMargins()
        min_height = plh + pbh + margins.top() + margins.bottom()
        self.progress_frame.setFixedHeight(min_height)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = Header1("Home")
        # title.setProperty("heading", True)
        layout.addWidget(title)

        # profile info stuff
        info_frame = QWidget()
        info_frame.setContentsMargins(0, 0, 0, 0)
        # info_frame.setStyleSheet(
        #     f"background-color: {styles.BG_SURFACE}; "
        #     f"border: 1px solid {styles.BORDER}; "
        #     "border-radius: 10px; padding 20px;"
        # )
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(0, 0, 0, 0)

        info_sub_frame = QFrame()

        # pyrefly: ignore [bad-argument-type]
        profile_manager.add_profile_switch_handler(self._on_profile_change)
        profile_manager.add_profile_refresh_handler(self._refresh_profiles)

        info_layout.addWidget(info_sub_frame)

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
        open_rp_button.clicked.connect(
            Slot()(lambda: self._open_prof_folder("rp"))
        )
        profile_action_row.addWidget(open_rp_button, 0)

        open_save_button = QPushButton("Worlds")
        open_save_button.clicked.connect(
            Slot()(lambda: self._open_prof_folder("world"))
        )
        open_save_button.setProperty("mini", True)
        profile_action_row.addWidget(open_save_button, 0)

        open_mods_button = QPushButton("Mods")
        open_mods_button.clicked.connect(
            Slot()(lambda: self._open_prof_folder("mods"))
        )
        open_mods_button.setProperty("mini", True)
        profile_action_row.addWidget(open_mods_button, 0)

        open_screenshots_button = QPushButton("Screenshots")
        open_screenshots_button.clicked.connect(
            Slot()(lambda: self._open_prof_folder("screenshots"))
        )
        open_screenshots_button.setProperty("mini", True)
        profile_action_row.addWidget(open_screenshots_button, 0)

        open_versions_button = QPushButton("Versions")
        open_versions_button.clicked.connect(
            Slot()(lambda: self._open_prof_folder("versions"))
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
            placeholderText="*taps mic*",
            centerOnScroll=False,
        )
        self.game_logs.setBackgroundRole(QPalette.ColorRole.Dark)
        self.game_logs.setFont(self.fonts.terminal)
        self.game_logs.setMaximumBlockCount(5000)  # change if needed

        layout.addWidget(info_frame, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.game_logs, 1)

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

        layout.addWidget(self.progress_frame)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

        # Play button
        self.play_button = QPushButton("Loading...")
        self.play_button.setProperty("play", True)
        self.play_button.setMinimumHeight(50)
        self.play_button.setMinimumWidth(280)
        self.play_button.clicked.connect(self._on_play)
        self.play_button.setDisabled(True)

        play_layout = QHBoxLayout()
        play_layout.addWidget(
            self.play_button, 0, Qt.AlignmentFlag.AlignCenter
        )
        layout.addLayout(play_layout)
        account_man.signals.account_changed.connect(
            self._check_set_demo_mode_text
        )

    @Slot()
    def _refresh_profiles(self):
        current = profile_manager.get_current_profile()
        self._on_profile_change(current)

    @Slot(LaunchProfile)
    def _on_profile_change(self, profile: LaunchProfile):
        self._reset_play_button()
        try:
            version_installed = profile.check_install()
        except InvalidVersionIdError:
            self.progress_label.setText(
                f"Unknown game version: {profile.version_id}"
            )
            return
        if version_installed:
            self.progress_label.setText("Ready to launch.")
            self.status_update.emit(
                f"Ready to launch {profile.real_version_id}"
            )
        elif not offline_man.offline:
            self.status_update.emit(
                f"Ready to install {profile.real_version_id}"
            )
            self.progress_label.setText("Ready to install.")
        else:
            self.status_update.emit("No internet connection")
            if profile.version_id in {"latest-snapshot", "latest-release"}:
                self.progress_label.setText(
                    f"Version {profile.real_version_id} isn't installed!"
                )
            else:
                self.progress_label.setText(
                    f"Version {profile.version_id} isn't installed!"
                )
        match profile.version_id:
            case "latest-release":
                version_label = f"Latest Release ({profile.real_version_id})"
            case "latest-snapshot":
                version_label = f"Latest Snapshot ({profile.real_version_id})"
            case _:
                version_label = profile.version_id
        self.version_label.setText(f"Version: {version_label}")

    def _on_play(self):
        """Play button function"""
        log.info("Preparing to install/launch game...")
        self.play_button.setDisabled(True)
        prof = profile_manager.get_current_profile()
        if prof.check_install():
            self.play_button.setText("Preparing...")
        else:
            self.play_button.setText("Installing...")
        self.play_requested.emit()

    @Slot(str, float, float, bool)
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

    @Slot(str)
    def _on_status(self, text: str):
        self.progress_label.setText(text)

    @Slot()
    def on_game_closed(self):
        self.play_button.setEnabled(True)
        # we WILL have profiles by this point or i deserve the crash this will
        # allow
        prof = profile_manager.get_current_profile()
        prof.set_last_used()
        self._reset_play_button()

    @Slot()
    def _open_prof_folder(self, folder: str | None = None):
        p: str | os.PathLike
        prof = profile_manager.get_current_profile()
        if prof.game_dir:
            if not is_path_valid(prof.game_dir):
                error_box(f"Bad game directory: {prof.game_dir!r}")
            p = prof.game_dir
        else:
            p = paths.game

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
                        error_box(f"Bad mods directory: {prof.mods_folder!r}")
                        return
                    p = os.path.normpath(prof.mods_folder)
                else:
                    p = os.path.join(p, "mods")
            case "world":
                p = os.path.join(p, "saves")
            case "screenshots":
                p = os.path.join(p, "screenshots")
            case "versions":
                p = os.path.join(paths.game, "versions")

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

    @Slot(LauncherAccount)
    @Slot(NoneType)
    def _check_set_demo_mode_text(self, lp: LauncherAccount | None = None):
        if not self.play_button.isEnabled():
            return
        if not lp:
            lp = account_man.active
            if not lp:
                return
        if lp.token and lp.token.owns_game:
            self.play_button.setText("Launch Game")
        else:
            self.play_button.setText("Launch Demo")

    @Slot(bool, str)
    def on_launch_finished(self, success: bool, message: str):
        if success:
            self.play_button.setText("Playing...")
            self.play_button.setEnabled(False)
            self.progress_label.setVisible(False)
            self.progress_bar.setVisible(False)
            self.progress_label.setText("")
            self.progress_bar.setValue(0)
            self.game_open.emit()
        else:
            self.aborted_launch()
            TextPopup(
                message or "No content provided",
                "Failed to launch game",
                "Launch Error",
                self,
            )

    @Slot(bool)
    def on_install_finished(self, success: bool):
        if success:
            self.play_button.setText("Launching...")
            self.play_button.setEnabled(False)
            self.progress_label.setVisible(False)
            self.progress_bar.setVisible(False)
            self.progress_label.setText("")
            self.progress_bar.setValue(0)
        else:
            self.aborted_launch()

    def _reset_play_button(self):
        profile = profile_manager.get_current_profile()
        try:
            sel_version_installed = profile.check_install()
        except InvalidVersionIdError as err:
            self.play_button.setText("Invalid game version ID")
            self.play_button.setDisabled(True)
            sel_version_installed = False
            log.warning(
                "InvalidVersionIdError on profile %r (ID: %s)",
                profile.name,
                profile.uuid,
            )
            log.debug("Traceback:", exc_info=err)
            return
        if offline_man.offline:
            if sel_version_installed:
                self.play_button.setText("Launch Game (offline)")
            else:
                self.play_button.setText("Cannot install")
                self.play_button.setDisabled(True)
                return
        else:
            if sel_version_installed:
                self.play_button.setText("Launch Game")
            else:
                self.play_button.setText(
                    f"Install {profile.real_version_id or profile.version_id}"
                )
        self.play_button.setDisabled(False)
        return

    def aborted_launch(self):
        self._reset_play_button()
        self.progress_label.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("")
        self.progress_bar.setValue(0)

    @Slot()
    def config_changed(self):
        self.game_logs.setHidden(not config.show_logs_on_home)
        self.stretcher.setHidden(config.show_logs_on_home)
        if theme_manager.current.qss:
            self.play_button.setStyleSheet(
                f"{self.play_button.styleSheet()}"
                'QPushButton[play="true"] {'
                "height: 50;"
                "width: 280;"
                "}"
            )
        else:
            self.play_button.setStyleSheet("")
            self.play_button.setFixedHeight(50)
            self.play_button.setMinimumWidth(280)
        if not config.show_logs_on_home:
            if self.game_logs.blockCount() > 1:
                log.debug(
                    "Resetting home page game logs due to option being "
                    "unchecked"
                )
                self.game_logs.clear()

    @Slot(str, str, str, str, str)
    def handle_game_log(
        self,
        logger_name: str,
        timestamp: str,
        level: str,
        thread: str,
        msg: str,
    ):
        if config.show_logs_on_home:
            ts = time.strftime(
                "%H:%M:%S", time.localtime(int(timestamp) / 1000)
            )
            inf = {
                "logger": logger_name,
                "timestamp": ts,
                "level": level,
                "thread": thread,
                "message": msg,
            }
            match log_tmp_type:
                case config.GameLogTemplateType.PERCENT:
                    self.game_logs.appendPlainText(log_tmp % inf)
                case (
                    config.GameLogTemplateType.FORMAT
                    | config.GameLogTemplateType.DEFAULT
                ):
                    self.game_logs.appendPlainText(log_tmp.format_map(inf))
                case _:  # fallback for invalid/unknown
                    self.game_logs.appendPlainText(
                        constants.DEFAULT_LOG_TEMPLATE.format(inf)
                    )
