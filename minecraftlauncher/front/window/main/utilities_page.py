"""
minecraftlauncher.front.window.main.utilities_page

Game management utilities
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel, QVBoxLayout, QWidget, QPushButton
)

from . import HRow
from minecraftlauncher.front.window.modloaders import (
    FabricInstallWindow, NeoForgeInstallWindow)

class UtilitiesPage(QWidget):
    """Utilities page (STUB)"""

    status_update = Signal(str)
    modloader_installed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fab_install_window = FabricInstallWindow(self)
        self.fab_install_window.installed_fabric.connect(self.modloader_installed)
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