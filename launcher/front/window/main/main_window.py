"""
minecraftlauncher.front.window.main.main_window

Main application window.
"""

from time import sleep
import logging
import sys

from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from launcher import (
    PostLaunchBehavior,
    config,
    constants,
    debug_utils,
    launchargs,
    lifecycle,
    paths,
    set_exiting,
)
from launcher.back import profile_manager
from launcher.constants import LAUNCHER_VERSION
from launcher.front.icon_helpers import IconName, get_icon
from launcher.front.qt.widgets import AccountSelect
from launcher.front.qt.widgets.profile_list import ProfileList
from launcher.front.window.about import AboutWindow
from launcher.front.window.modloaders import FabricInstallWindow
from launcher.front.window.settings import SettingsWindow
from launcher.front.window.skin_change import SkinChange
from launcher.functions.error_box import error_box
from launcher.threads.lro_thread import run_lro

from .home_page import HomePage
from .profiles_page import ProfilesPage

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Primary application window"""

    login_requested = Signal()
    status_update = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PymLauncher")
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
        lifecycle.shutting_down.emit()
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
            case _:
                pass

    def _process_game_closed(self, exit_code: str):
        # pyrefly: ignore [non-exhaustive-match]
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

        self.menuBar().setNativeMenuBar(True)

        self.menuBar().addAction(
            "Add Profile",
            profile_manager.create_profile,
        )

        self.menuBar().addAction(
            "Settings",
            self._show_settings_window,
        )

        self.utils_menu = self.menuBar().addMenu("Utilities")
        self._setup_utilities_menu()

        help_menu = self.menuBar().addMenu("Help")

        help_menu.addAction(
            get_icon(IconName.HELP_ABOUT),
            f"About {constants.LAUNCHER_NAME}",
            AboutWindow.create_show,
        )

        self.account_dropdown = AccountSelect()
        self.account_dropdown.add_account_requested.connect(
            self.login_requested.emit
        )
        self.account_dropdown.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum
        )
        self.menuBar().setCornerWidget(
            self.account_dropdown, Qt.Corner.TopRightCorner
        )
        self.menuBar().setAutoFillBackground(True)

        # body
        body = QWidget()
        body_layout = QHBoxLayout(body)
        # body_layout.setContentsMargins(0, 0, 0, 0)
        # body_layout.setSpacing(0)

        # profile selector
        self.profile_list = ProfileList()
        self.profile_list.setContentsMargins(0, 0, 0, 0)
        self.profile_list.setMaximumWidth(200)
        self.profile_list.setMinimumWidth(200)
        body_layout.addWidget(self.profile_list)

        # main area
        main_area = QVBoxLayout()
        body_layout.addLayout(main_area)

        self.pages = QTabWidget()
        main_area.addWidget(self.pages, 1)

        # self.pages.setFrameShape(QFrame.Shape.StyledPanel)

        self.home_page = HomePage(self.pages)
        self.profiles_page = ProfilesPage(self.pages)

        self.tab_list = {
            "Home": self.home_page,
            "Edit Profile": self.profiles_page,
        }

        self.home_page.game_open.connect(self._process_game_open)
        self.home_page.game_closed.connect(self._process_game_closed)
        self.home_page.status_update.connect(self.set_status_tmp)

        for label, page in self.tab_list.items():
            self.pages.addTab(page, label)

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
        lifecycle.config_updated.connect(self._on_config_update)

    @Slot()
    def _on_tab_change(self, idx: int):
        self.pages.setCurrentIndex(idx)

    def set_status(self, message: str):
        self.status.showMessage(message)

    @Slot(int)
    def set_status_tmp(self, message: str, time: int = -1):
        if 0 < time < 1000:
            time = min(time * 1000, 1000)
        if time:
            self.status.showMessage(message, time)
        else:
            self.status.showMessage(message)

    @Slot()
    def _show_settings_window(self):
        win = SettingsWindow(self)
        win.accepted.connect(self.home_page.config_changed)
        win.exec()

    @Slot()
    def _show_fabric_window(self):
        FabricInstallWindow().exec()

    @Slot()
    def _open_data_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(paths.data))

    def _setup_utilities_menu(self):
        self.utils_menu.addAction(
            get_icon(IconName.INSTALLER),
            "Open Fabric Installer",
            self._show_fabric_window,
        )
        self.utils_menu.addAction(
            get_icon(IconName.DATA_FOLDER),
            "Open data folder",
            self._open_data_folder,
        )

        self.utils_menu.addAction("Change skin", SkinChange.change_skin)

        if constants.DEV:
            self.utils_menu.addAction(
                "See accounts.bin", debug_utils.preview_accounts_file
            )
            self.utils_menu.addAction(
                "Show debug info", debug_utils.system_info
            )
            self.utils_menu.addAction(
                "Force account refresh", debug_utils.force_account_refresh
            )
            self.utils_menu.addAction(
                "Test LROThread (3 sec)", self._test_lro_thread
            )

    def _test_lro_thread(self):
        return run_lro("Testing LROs", sleep, 3)

    def showEvent(self, event: QShowEvent) -> None:
        self._on_config_update()
        return super().showEvent(event)

    @Slot()
    def _on_config_update(self):
        self.menuBar().setCornerWidget(QWidget(), Qt.Corner.TopRightCorner)
        lifecycle.qapp.processEvents()
        h = self.menuBar().height()
        self.account_dropdown.setFixedHeight(
            max(h, self.account_dropdown.sizeHint().height())
        )
        self.menuBar().setCornerWidget(
            self.account_dropdown, Qt.Corner.TopRightCorner
        )
