"""
minecraftlauncher.front.window.main.utilities_page

Game management utilities
"""

from textwrap import dedent
import platform
import logging
import uuid
import json
import sys
import os

from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QPushButton

from minecraftlauncher.front.window.modloaders import (
    FabricInstallWindow,
    NeoForgeInstallWindow,
)
from minecraftlauncher.front.qt.widgets import Section
from minecraftlauncher.back.account_manager import account_man
from minecraftlauncher.front.window import TextPopup
from minecraftlauncher.offline import offline_man
from minecraftlauncher.functions import beep
from minecraftlauncher.paths import paths
from minecraftlauncher import constants
from . import HRow

log = logging.getLogger(__name__)


class UtilitiesPage(QWidget):
    """Utilities page (STUB)"""

    status_update = Signal(str)
    modloader_installed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fab_install_window = FabricInstallWindow(self)
        self.fab_install_window.installed_fabric.connect(
            self.modloader_installed
        )
        self.neoforge_install_window = NeoForgeInstallWindow(self)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        title = QLabel("Utilities")
        title.setProperty("heading", True)
        layout.addWidget(title)

        fabric_row = HRow(self)
        fabric_row.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        f_label = QLabel("Fabric installer:")
        fabric_row.addWidget(f_label)
        self.f_win_button = QPushButton("Open")
        self.f_win_button.clicked.connect(self.fab_install_window.exec)
        fabric_row.addWidget(self.f_win_button)

        layout.addWidget(fabric_row)

        if constants.DEV:
            debug_section = Section("Debug")
            debug_section.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            dump_accs_btn = QPushButton("See accounts.bin")
            dump_accs_btn.clicked.connect(self._dump_accs)
            debug_section.addWidget(dump_accs_btn)

            test_beep = QPushButton("Test OS beep")
            test_beep.clicked.connect(beep)
            debug_section.addWidget(test_beep)

            misc_info = QPushButton("Debug Info")
            misc_info.clicked.connect(self.system_info)
            debug_section.addWidget(misc_info)

            layout.addWidget(debug_section)

        # nf_row = HRow(self)
        # nf_row.setAlignment(
        #     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        # )
        # nf_label = QLabel("NeoForge installer:")
        # nf_row.addWidget(nf_label)
        # nf_button = QPushButton("Open")
        # nf_button.clicked.connect(self.neoforge_install_window.exec)
        # nf_row.addWidget(nf_button)

        # layout.addWidget(nf_row)

        layout.addStretch()

    def build(self):
        offline_man.add_hook(self.offline_mode_hook)

    # literally zero reason for this to even take up memory in prod
    if constants.DEV:
        # TODO: just spawn a qdialog for it or something, save an SSD lol
        def _dump_accs(self):
            accounts_list = json.dumps(account_man.dump(), indent=4)
            assert accounts_list
            dump_path = os.path.join(paths.data, f"temp-{uuid.uuid4()}.json")
            log.debug("Writing to %s", dump_path)
            with open(dump_path, "w") as file:
                file.write(accounts_list)
            log.debug("Opening with QDesktopServices")
            uri = QUrl.fromLocalFile(dump_path)
            QDesktopServices.openUrl(uri)
            log.debug("Waiting a second then deleting the file...")

            def delete_temp_file():
                log.debug("deleting file")
                os.unlink(dump_path)

            QTimer.singleShot(1000, delete_temp_file)

    def offline_mode_hook(self, offline: bool):
        self.f_win_button.setDisabled(offline)

    def system_info(self):
        os_info = platform.uname()
        text = dedent(f"""
        System info:
            CPU type: {os_info.machine}
            CPU thread count: {os.cpu_count()}
            Usable CPU threads: {os.process_cpu_count()}
            OS: {os_info.system} {os_info.version}
            Computer name: {os_info.node}
        Process info:
            PID: {os.getpid()}
            CWD: {os.getcwd()}
            Executable: {sys.executable}
            Python flags: {", ".join(str(a) for a in sys.flags)}
        Launcher info:
            Offline: {"Yes" if offline_man.offline else "No"}
            .minecraft directory: {paths.game}
            Launcher data directory: {paths.data}
            Accounts cache filename: {paths.accounts_file}
        """).strip()

        TextPopup(text, "Debug Info", "Debug Info", parent=self)
