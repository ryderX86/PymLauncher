"""
minecraftlauncher.front.window.main.utilities_page

Game management utilities
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel, QVBoxLayout, QWidget, QPushButton
)

from . import HRow
from minecraftlauncher.front.window.fabric_installer import FabricInstallWindow

class UtilitiesPage(QWidget):
    """Utilities page (STUB)"""
    fabric_installed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fab_install_window = FabricInstallWindow(self)
        self.fab_install_window.load()
        self.fab_install_window.installed_fabric.connect(self.fabric_installed)
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

        layout.addStretch()

    def build(self):
        pass