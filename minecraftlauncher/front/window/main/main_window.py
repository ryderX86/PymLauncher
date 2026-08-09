"""
minecraftlauncher.front.window.main.main_window

Main application window.
"""

__lazy_imports__ = ["minecraftlauncher.front.ees.KonamiCode"]  # py3.15

import logging
import sys

from PySide6.QtCore import Signal, QSize
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QLabel,
    QStatusBar,
    QFrame,
    QListWidget,
    QListWidgetItem,
)

from minecraftlauncher import set_exiting, launchargs
from minecraftlauncher.config import config, PostLaunchBehavior
from minecraftlauncher.front import styles
from minecraftlauncher.back import profile_manager
from minecraftlauncher.constants import LAUNCHER_VERSION
from minecraftlauncher.functions.error_box import error_box
from minecraftlauncher.front.qt.widgets import AccountSelect
from .home_page import HomePage
from .profiles_page import ProfilesPage
from .settings_page import SettingsPage
from .account_page import AccountPage
from .utilities_page import UtilitiesPage

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Primary application window"""

    login_requested = Signal()
    status_update = Signal(str)

    NAV_ITEMS = [
        ("Home", "home"),
        ("Profiles", "profiles"),
        ("Account", "account"),
        ("Utilities", "utilities"),
        ("Settings", "settings"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Minecraft Launcher")
        self.setMinimumSize(960, 620)
        width = config.window_size[0]
        height = config.window_size[1]
        self.resize(*config.window_size)
        geo = self.screen().geometry()
        sw = geo.width()
        sh = geo.height()
        if sw <= 1280:  # fix for small/scaled displays
            x = sw // 2 - width // 2
            y = sh // 2 - height // 2
            self.setGeometry(x, y, *config.window_size)

        self._nav_buttons: dict[str, QListWidgetItem] = {}
        self._build_ui()

    def check_for_launch_arg(self):
        if launchargs.launch_profile:
            log.info("We're launching from the jump-list!")
            if launchargs.launch_profile in profile_manager.profiles:
                profile_manager.set_current_profile_uuid(
                    launchargs.launch_profile
                )
                log.debug("Clicking play button")
                # is this even a good idea? lol
                self.home_page.play_button.click()
            else:
                error_box(
                    "Couldn't find any profile with ID "
                    f'"{launchargs.launch_profile}"!'
                )

    def _on_window_closed(self):
        geo = self.geometry()
        if self.isMaximized():
            config.maximized = True
        else:
            config.window_size = [geo.width(), geo.height()]
            config.maximized = False

    def closeEvent(self, a0):
        set_exiting()
        self._on_window_closed()
        super().closeEvent(a0)

    def hide(self):
        self._on_window_closed()
        return super().hide()

    def _process_game_open(self):
        match config.post_launch_option:
            case PostLaunchBehavior.HIDE | PostLaunchBehavior.CLOSE_WHEN_DONE:
                self.hide()
            case PostLaunchBehavior.CLOSE:
                self.close()

    def _process_game_closed(self, exit_code: str):
        match config.post_launch_option:
            case PostLaunchBehavior.KEEP_OPEN:
                return
            case PostLaunchBehavior.HIDE:
                self.show()
            case PostLaunchBehavior.CLOSE_WHEN_DONE:
                if int(exit_code) == 0:
                    self.close()
                    sys.exit()
                else:
                    self.show()

    def _build_ui(self):
        log.debug("Building MainWindow UI")
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # top bar (account dropdown)
        top_bar = QWidget()
        # top_bar.setFixedHeight(48)
        # top_bar.setStyleSheet(f"background-color: {styles.BG_DARK};")
        top_bar.setBackgroundRole(styles.CRole.Base)
        top_bar.setAutoFillBackground(True)
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(2, 2, 2, 2)
        top_bar_layout.addStretch(2)

        self.account_dropdown = AccountSelect()
        self.account_dropdown.add_account_requested.connect(
            self.login_requested.emit
        )
        top_bar_layout.addWidget(self.account_dropdown)

        root_layout.addWidget(top_bar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {styles.BORDER};")
        root_layout.addWidget(sep)

        # body
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # sidebar
        self.sidebar = QListWidget()
        self.sidebar.setBackgroundRole(styles.CRole.Mid)
        self.sidebar.setDragEnabled(False)
        self.sidebar.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.sidebar.setFixedWidth(180)
        # self.sidebar.setProperty("sidebar", True)
        # self.sidebar.setIconSize(QSize(32, 32))
        self.sidebar.setUniformItemSizes(True)
        self.sidebar.setFrameShape(QFrame.Shape.NoFrame)

        self.sidebar.currentRowChanged.connect(self._nav_button_group)

        for label, key in self.NAV_ITEMS:
            button = QListWidgetItem("".join([" " * 2, label]))
            button.setSizeHint(QSize(0, 48))
            self.sidebar.addItem(button)
            self._nav_buttons[key] = button

        body_layout.addWidget(self.sidebar)

        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setFixedWidth(1)
        vsep.setStyleSheet(f"background-color: {styles.BORDER};")
        body_layout.addWidget(vsep)

        self.pages = QStackedWidget()
        self.home_page = HomePage()
        self.profiles_page = ProfilesPage()
        self.settings_page = SettingsPage()
        self.account_page = AccountPage()
        self.utilities_page = UtilitiesPage()

        self.page_list = [
            self.home_page,
            self.profiles_page,
            self.account_page,
            self.utilities_page,
            self.settings_page,
        ]

        self.utilities_page.modloader_installed.connect(
            self.profiles_page.refresh_version_combo
        )

        self.home_page.game_open.connect(self._process_game_open)
        self.home_page.game_closed.connect(self._process_game_closed)
        self.home_page.status_update.connect(self.set_status_tmp)
        self.account_page.skin_upload.connect(self.account_dropdown.refresh)
        self.settings_page.settings_changed.connect(
            self.home_page.config_changed
        )

        for page in self.page_list:
            self.pages.addWidget(page)

        body_layout.addWidget(self.pages, 1)

        root_layout.addWidget(body)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready to go")
        self.status.setSizeGripEnabled(False)
        ver_label = QLabel(LAUNCHER_VERSION)
        ver_label.setContentsMargins(0, 0, 6, 0)
        ver_label.setProperty("secondary", True)
        self.status.addPermanentWidget(ver_label, 0)

        self.sidebar.setCurrentRow(0)

    def _nav_button_group(self, idx: int):
        self.pages.setCurrentIndex(idx)

    def set_status(self, message: str):
        self.status.showMessage(message)

    def set_status_tmp(self, message: str):
        self.status.showMessage(message, 10)
