"""
minecraftlauncher.front.window.main.settings_page

Stub settings page
"""

import logging

from PySide6.QtCore import QFile, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher.config import config
from launcher.front.qt import CustomMapper
from launcher.front.qt.widgets import Section, TooltipHint
from launcher.front.window import TextPopup
from launcher.paths import paths

log = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """Settings page (STUB)"""

    settings_changed = Signal()
    status_update = Signal(str)

    def __init__(self, parent=None, *, is_modal: bool = False):
        self._is_modal = is_modal
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        self.mapper = CustomMapper(self)
        self.mapper.saved.connect(self.settings_changed.emit)

        title = QLabel("Settings")
        title.setProperty("heading", True)
        layout.addWidget(title)

        # Behavior
        behavior = Section("Behavior")
        behavior.setProperty("section", True)
        layout.addWidget(behavior)

        post_launch_w = QWidget()
        post_launch_lo = QHBoxLayout(post_launch_w)
        post_launch_lo.setContentsMargins(0, 0, 4, 0)
        tooltip = TooltipHint(
            "How you want the launcher to behave after the game opens.\n\n"
            '"Close launcher completely" may increase system resources '
            "available to Minecraft on low-end systems, however the launcher "
            "will be completely unable to detect crashes and automatically "
            "show you logs."
        )
        post_launch_l = QLabel("After Minecraft opens:")
        post_launch_lo.addWidget(post_launch_l)
        self.post_launch_options = QComboBox()
        self.post_launch_options.setProperty("compact", True)
        self.mapper.add_mapping(
            self.post_launch_options,
            saver=lambda _: setattr(
                config,
                "post_launch_option",
                self.post_launch_options.currentData(),
            ),
        )
        post_launch_lo.addWidget(self.post_launch_options)
        post_launch_lo.addWidget(tooltip)
        post_launch_lo.addStretch()

        behavior.addWidget(post_launch_w)

        login_device_code = QCheckBox("Use device code for logins")
        self.mapper.add_mapping(
            login_device_code,
            saver=lambda c: setattr(config, "use_device_code_for_logins", c),
        )
        login_device_code.setChecked(config.use_device_code_for_logins)
        behavior.addWidget(login_device_code)

        copy_code_for_login = QCheckBox("Copy sign-in code to clipboard")
        self.mapper.add_mapping(
            copy_code_for_login,
            saver=lambda c: setattr(config, "copy_code_for_login", c),
        )
        copy_code_for_login.setChecked(config.copy_code_for_login)
        behavior.addWidget(copy_code_for_login)

        allow_audio = QCheckBox("Allow warning/error sounds")
        self.mapper.add_mapping(
            allow_audio,
            saver=lambda c: setattr(config, "allow_audio", c),
        )
        allow_audio.setChecked(config.allow_audio)
        behavior.addWidget(allow_audio)

        # Downloads
        downloads = Section("Downloads")
        downloads.setProperty("section", True)
        layout.addWidget(downloads)

        redownload_w = QWidget()
        redownload_lo = QHBoxLayout(redownload_w)
        redownload_lo.setContentsMargins(0, 0, 0, 0)
        rd_tooltip = TooltipHint(
            "How you want the launcher to behave with a lack of hash\n\n"
            "If you don't know what a file hash is, leave this at the default "
            'option ("Always redownload"), unless you have a very bad '
            "or unstable internet connection.\n\n"
            '"Redownload once" will redownload the libraries/client JAR, '
            'then set it back to "Never redownload" if the game closes with '
            "a return code of 0."
        )
        rd_label = QLabel("When a file doesn't have a hash:")
        redownload_lo.addWidget(rd_label)
        self.redownload_option = QComboBox()
        self.mapper.add_mapping(
            self.redownload_option,
            saver=self._on_redownload_option_change,
        )
        self.redownload_option.setProperty("compact", True)
        redownload_lo.addWidget(rd_label)
        redownload_lo.addWidget(self.redownload_option)
        redownload_lo.addWidget(rd_tooltip)
        redownload_lo.addStretch()

        downloads.addWidget(redownload_w)

        # Visual
        visual = Section("Visual")
        visual.setProperty("section", True)
        layout.addWidget(visual)

        tooltips_enabled = QCheckBox("Show Tooltip Icons")
        self.mapper.add_mapping(
            tooltips_enabled,
            saver=lambda c: setattr(config, "tooltip_icons_enabled", c),
        )
        tooltips_enabled.setChecked(config.tooltip_icons_enabled)
        self.mapper.saved.connect(TooltipHint.refresh_visibility)
        visual.addWidget(tooltips_enabled)

        show_logs_w = QWidget()
        show_logs_w.setContentsMargins(0, 0, 0, 0)
        show_logs_lo = QHBoxLayout(show_logs_w)
        show_logs_lo.setContentsMargins(0, 0, 0, 0)
        show_logs_lo.setAlignment(Qt.AlignmentFlag.AlignLeft)
        show_logs_tt = TooltipHint(
            "Show the game's console logs on the home page.\n"
            "(Might slow your PC!)"
        )
        show_logs_check = QCheckBox("Show game logs on home page")
        self.mapper.add_mapping(
            show_logs_check,
            saver=lambda c: setattr(config, "show_logs_on_home", c),
        )
        show_logs_check.setChecked(config.show_logs_on_home)
        show_logs_lo.addWidget(show_logs_check)
        show_logs_lo.addWidget(show_logs_tt)

        visual.addWidget(show_logs_w)

        compat = Section("Compatibility")

        json_row_w = QWidget()
        json_row = QHBoxLayout(json_row_w)
        json_row.setContentsMargins(0, 0, 0, 0)
        json_option = QCheckBox("Enforce JSON spec")
        json_option.setChecked(config.enforce_json_spec)
        self.mapper.add_mapping(
            json_option,
            saver=lambda b: setattr(config, "enforce_json_spec", b),
        )
        json_row.addWidget(json_option)
        json_option_tt = TooltipHint(
            "Whether or not to enforce JSON spec in JSON files.\n\n"
            "Mojang's launcher saves JSON files with a format outside "
            "of JSON spec. Checking this box will enforce the JSON spec onto "
            "the various JSON files shared by both launchers, which may "
            "result in both launchers changing the file's format slightly "
            "every time one or the other is launched/closed.\n\n"
            "It's recommended to keep this off if you plan on using Mojang's "
            "launcher simultaneously in the current working directory."
        )
        json_row.addWidget(json_option_tt)
        compat.addWidget(json_row_w)

        layout.addWidget(compat)

        layout.addStretch()

        buttons_w = QWidget()
        buttons_lo = QHBoxLayout(buttons_w)
        buttons_lo.setContentsMargins(0, 0, 0, 0)

        acknowledgements = QPushButton("Acknowledgements")
        acknowledgements.clicked.connect(self._open_acknowledgements)
        buttons_lo.addWidget(acknowledgements)

        buttons_lo.addStretch()

        open_dir_btn = QPushButton("Open Data Folder")
        open_dir_btn.clicked.connect(self._open_data_folder)
        buttons_lo.addWidget(open_dir_btn)

        open_config_btn = QPushButton("Edit Config File")
        open_config_btn.clicked.connect(self._open_settings_file)
        open_config_btn.setToolTip("<i>Requires restart</i>")
        buttons_lo.addWidget(open_config_btn)

        layout.addWidget(buttons_w)

        manage_w = QWidget()
        manage_lo = QHBoxLayout(manage_w)
        manage_lo.setContentsMargins(0, 0, 0, 0)

        cancel_btn = QPushButton("Cancel")

        apply_btn = QPushButton("Apply")
        apply_btn.setEnabled(False)

        if self._is_modal:
            manage_lo.addStretch()
            ok_btn = QPushButton("OK")
            manage_lo.addWidget(ok_btn)

            p = self.parent()
            if isinstance(p, QDialog):
                cancel_btn.clicked.connect(p.reject)
            manage_lo.addWidget(cancel_btn)

            manage_lo.addWidget(apply_btn)
        else:
            manage_lo.addWidget(apply_btn)
            manage_lo.addWidget(cancel_btn)
            cancel_btn.setEnabled(False)
            cancel_btn.clicked.connect(self.mapper.revert_changes)
            cancel_btn.setText("Reset")
            self.mapper.changes_made.connect(cancel_btn.setEnabled)
            manage_lo.addStretch()

        layout.addWidget(manage_w)

        self.mapper.changes_made.connect(apply_btn.setEnabled)
        apply_btn.clicked.connect(self.mapper.save)

    def _open_settings_file(self):
        log.debug("Opened launcher settings file with default app")
        QDesktopServices.openUrl(QUrl.fromLocalFile(paths.config_file))

    def _open_data_folder(self):
        log.debug("Opened data folder with file explorer")
        QDesktopServices.openUrl(QUrl.fromLocalFile(paths.data))

    def build(self):
        self.post_launch_options.addItem(
            "Keep launcher open", config.PostLaunchBehavior.KEEP_OPEN
        )
        self.post_launch_options.addItem(
            "Hide launcher until game closes", config.PostLaunchBehavior.HIDE
        )
        self.post_launch_options.addItem(
            "Close launcher if game doesn't crash",
            config.PostLaunchBehavior.CLOSE_WHEN_DONE,
        )
        self.post_launch_options.addItem(
            "Close launcher completely", config.PostLaunchBehavior.CLOSE
        )
        self.post_launch_options.setCurrentIndex(config.post_launch_option)
        self.post_launch_options.currentIndexChanged.connect(
            self._on_post_launch_options_change
        )
        self.redownload_option.addItem(
            "Always redownload (default)",
            config.JarRedownloadBehavior.REDOWNLOAD,
        )
        self.redownload_option.addItem(
            "Redownload once (not recommended)",
            config.JarRedownloadBehavior.REDOWNLOAD_ONCE,
        )
        self.redownload_option.addItem(
            "Never redownload (not recommended)",
            config.JarRedownloadBehavior.NEVER,
        )
        match config.redownload_option:
            case config.JarRedownloadBehavior.NEVER:
                self.redownload_option.setCurrentIndex(2)
            case config.JarRedownloadBehavior.REDOWNLOAD:
                self.redownload_option.setCurrentIndex(0)
            case config.JarRedownloadBehavior.REDOWNLOAD_ONCE:
                self.redownload_option.setCurrentIndex(1)
        self.mapper.start()

    def _on_post_launch_options_change(self, i: int):
        config.post_launch_option = config.PostLaunchBehavior(i)

    def _on_redownload_option_change(self, i: int):
        data: int = self.redownload_option.itemData(i)
        config.redownload_option = config.JarRedownloadBehavior(data)

    def _reset_redownload_option_change(self, *args):
        match config.redownload_option:
            case config.JarRedownloadBehavior.NEVER:
                self.redownload_option.setCurrentIndex(2)
            case config.JarRedownloadBehavior.REDOWNLOAD:
                self.redownload_option.setCurrentIndex(0)
            case config.JarRedownloadBehavior.REDOWNLOAD_ONCE:
                self.redownload_option.setCurrentIndex(1)

    def _open_acknowledgements(self):
        file = QFile(":/acknowledgements.txt")
        if not file.open(QFile.OpenModeFlag.ReadOnly):
            log.warning("Device not open!")
        ba = file.readAll().data()
        if isinstance(ba, memoryview):
            ba = ba.tobytes()
        txt = ba.decode("utf-8")

        TextPopup(txt, "Acknowledgements", "Acknowledgements", self)
