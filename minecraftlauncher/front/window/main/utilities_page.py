"""
minecraftlauncher.front.window.main.utilities_page

Game management utilities
"""

import logging
import uuid

from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QPushButton

from minecraftlauncher.front.window.modloaders import (
    FabricInstallWindow,
    NeoForgeInstallWindow,
)
from minecraftlauncher.back import account_manager
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
        f_button = QPushButton("Open")
        f_button.clicked.connect(self.fab_install_window.exec)
        fabric_row.addWidget(f_button)

        layout.addWidget(fabric_row)

        if constants.DEV:
            debug_row = HRow(self)
            debug_row.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            d_label = QLabel("Debug utilities:")
            dump_accs_btn = QPushButton("See accounts.bin")
            dump_accs_btn.clicked.connect(self._dump_accs)
            debug_row.addWidget(d_label)
            debug_row.addWidget(dump_accs_btn)
            layout.addWidget(debug_row)

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
        pass

    # literally zero reason for this to even take up memory in prod
    if constants.DEV:
        # TODO: just spawn a qdialog for it or something, save an SSD lol
        def _dump_accs(self):
            accounts_list = account_manager.save_accounts(
                return_unencrypted=True
            )
            assert accounts_list
            b = accounts_list.encode("utf-8")
            dump_path = (
                constants.LAUNCHER_DATA_DIR / f"temp-{uuid.uuid4()}.json"
            )
            log.debug("Writing to %s", dump_path)
            dump_path.write_bytes(b)
            log.debug("Opening with QDesktopServices")
            uri = QUrl.fromLocalFile(dump_path)
            QDesktopServices.openUrl(uri)
            log.debug("Waiting a second then deleting the file...")

            def delete_temp_file():
                log.debug("deleting file")
                dump_path.unlink()

            QTimer.singleShot(1000, delete_temp_file)
