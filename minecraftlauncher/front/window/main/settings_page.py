"""
minecraftlauncher.front.window.main.settings_page

Stub settings page
"""
from enum import StrEnum
import logging

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QLabel, QVBoxLayout, QWidget, QHBoxLayout, QComboBox, QPushButton,
    QCheckBox
)

from minecraftlauncher import config, constants
from minecraftlauncher.front import resources
from minecraftlauncher.front.qt.widgets import TooltipHint

log = logging.getLogger(__name__)

class SettingsPage(QWidget):
    """Settings page (STUB)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        title = QLabel("Settings")
        title.setProperty("heading", True)
        layout.addWidget(title)

        # Behavior
        behavior_label = QLabel("Behavior")
        behavior_label.setProperty("section", True)
        layout.addWidget(behavior_label)

        post_launch_w = QWidget()
        post_launch_lo = QHBoxLayout(post_launch_w)
        post_launch_lo.setContentsMargins(0, 0, 0, 0)
        tooltip = TooltipHint(
            "How you want the launcher to behave after the game opens.\n\n"
            "\"Close launcher completely\" may increase system resources "
            "available to Minecraft on low-end systems, however the launcher "
            "will be completely unable to detect crashes and automatically "
            "show you logs."
        )
        post_launch_lo.addWidget(tooltip)
        post_launch_l = QLabel("After Minecraft opens:")
        post_launch_lo.addWidget(post_launch_l)
        self.post_launch_options = QComboBox()
        post_launch_lo.addWidget(self.post_launch_options)
        post_launch_lo.addStretch()
        
        layout.addWidget(post_launch_w)

        # Visual
        visual_label = QLabel("Visual")
        visual_label.setProperty("section", True)
        layout.addWidget(visual_label)

        tooltips_enabled = QCheckBox("Show Tooltip Icons")
        tooltips_enabled.setChecked(config.tooltip_icons_enabled)
        tooltips_enabled.checkStateChanged.connect(
            lambda c: config.set("tooltip_icons_enabled",
                                 c == Qt.CheckState.Checked)
        )
        tooltips_enabled.checkStateChanged.connect(
            lambda c: TooltipHint.refresh_visibility()
        )
        layout.addWidget(tooltips_enabled)

        layout.addStretch()

        buttons_w = QWidget()
        buttons_lo = QHBoxLayout(buttons_w)
        buttons_lo.addStretch()

        open_config_btn = QPushButton("Edit Config File")
        open_config_btn.clicked.connect(self._open_settings_file)
        open_config_btn.setToolTip("<i>Requires restart</i>")
        buttons_lo.addWidget(open_config_btn)

        layout.addWidget(buttons_w)

    def _open_settings_file(self):
        log.debug("Opened launcher settings file with default app")
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(constants.LAUNCHER_CONFIG_FILE)
        )

    def build(self):
        self.post_launch_options.addItem(
            "Keep launcher open", config.PostLaunchBehavior.KEEP_OPEN
        )
        self.post_launch_options.addItem(
            "Hide launcher until game closes", config.PostLaunchBehavior.HIDE
        )
        self.post_launch_options.addItem(
            "Close launcher if game doesn't crash",
            config.PostLaunchBehavior.CLOSE_WHEN_DONE
        )
        self.post_launch_options.addItem(
            "Close launcher completely",
            config.PostLaunchBehavior.CLOSE
        )
        self.post_launch_options.setCurrentIndex(
            config.post_launch_option
        )
        self.post_launch_options.currentIndexChanged.connect(
            self._on_post_launch_options_change
        )

    def _on_post_launch_options_change(self, i:int):
        config.post_launch_option = config.PostLaunchBehavior(i)