"""
minecraftlauncher.front.window.main.main_window

Main application window.
"""
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout,
    QWidget, QLabel, QStatusBar, QFrame)

from minecraftlauncher import config
from minecraftlauncher.front import styles
from minecraftlauncher.back import account_manager
from minecraftlauncher.constants import LAUNCHER_VERSION
from .home_page import HomePage
from .profiles_page import ProfilesPage
from .settings_page import SettingsPage
from .account_page import AccountPage
from .account_select import AccountSelect
from .utilities_page import UtilitiesPage

class MainWindow(QMainWindow):
    """Primary application window"""

    login_requested = Signal()
    status_update = Signal(str)

    NAV_ITEMS = [
        ("Home", "home"),
        ("Profiles", "profiles"),
        ("Account", "account"),
        ("Utilities", "utilities"),
        ("Settings", "settings")
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Minecraft Launcher")
        self.setMinimumSize(960, 600)
        width = config.window_size[0]
        height = config.window_size[1]
        self.resize(*config.window_size)
        geo = self.screen().geometry()
        if geo.width() <= 1280: # fix for small/scaled displays
            x = geo.width() // 2 - width // 2
            y = geo.height() // 2 - height // 2
            self.setGeometry(x, y, *config.window_size)

        self._nav_buttons:dict[str, QPushButton] = {}
        self._build_ui()

    def _save_config(self):
        geo = self.geometry()
        if self.isMaximized():
            config.maximized = True
        else:
            config.window_size = [geo.width(), geo.height()]
            config.maximized = False
        config.save()
        account_manager.save_accounts()

    def closeEvent(self, a0):
        self._save_config()
        super().closeEvent(a0)

    def hide(self):
        self._save_config()
        config.save()
        return super().hide()
    
    def _process_game_open(self):
        match config.post_launch_option:
            case (config.PostLaunchBehavior.HIDE |
                  config.PostLaunchBehavior.CLOSE_WHEN_DONE):
                self.hide()
            case config.PostLaunchBehavior.CLOSE:
                self.close()

    def _process_game_closed(self, exit_code:str):
        match config.post_launch_option:
            case config.PostLaunchBehavior.KEEP_OPEN:
                return
            case config.PostLaunchBehavior.HIDE:
                self.show()
            case config.PostLaunchBehavior.CLOSE_WHEN_DONE:
                if int(exit_code) == 0:
                    self.close()
                    exit()
                else:
                    self.show()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # top bar (account dropdown)
        top_bar = QWidget()
        top_bar.setFixedHeight(48)
        top_bar.setStyleSheet(f"background-color: {styles.BG_DARK};")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(16, 0, 16, 0)
        
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
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setProperty("sidebar", True)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 8, 0, 8)
        sidebar_layout.setSpacing(0)

        for label, key in self.NAV_ITEMS:
            button = QPushButton(label)
            button.setProperty("nav", True)
            button.clicked.connect(lambda checked, k=key: self._navigate(k))
            sidebar_layout.addWidget(button)
            self._nav_buttons[key] = button

        sidebar_layout.addStretch()

        body_layout.addWidget(sidebar)

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
            self.settings_page
        ]

        self.utilities_page.modloader_installed.connect(
            self.profiles_page.refresh_version_combo
        )

        self.home_page.game_open.connect(self._process_game_open)
        self.home_page.game_closed.connect(self._process_game_closed)
        self.account_page.skin_upload.connect(self.account_dropdown.refresh)

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

        self._navigate("home")

    def _navigate(self, key:str):
        pages = [*self._nav_buttons.keys()]
        index = pages.index(key)
        self.pages.setCurrentIndex(index)

        for k, button in self._nav_buttons.items():
            button.setProperty("active", k == key)
            button.setDisabled(k == key)
            b_style = button.style()
            if b_style:
                b_style.unpolish(button)
                b_style.polish(button)
    
    def set_status(self, message:str):
        self.status.showMessage(message)