import logging

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QHBoxLayout,
    QCheckBox,
    QMessageBox,
)


from minecraftlauncher.back import fabric

log = logging.getLogger(__name__)


class FabricInstallWindow(QDialog):
    installed_fabric = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        flags = Qt.WindowType.Window
        flags |= Qt.WindowType.CustomizeWindowHint
        flags |= Qt.WindowType.WindowTitleHint
        flags |= Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.game_ver_selected = False
        self.loader_ver_selected = False
        self._build_ui()
        size = QSize(400, 250)
        self.setMaximumSize(size)
        self.setMinimumSize(size)
        self.setSizeGripEnabled(False)
        self.setWindowTitle("Fabric Installer")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(16)

        label = QLabel("Install Fabric Loader")
        label.setProperty("heading", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(label)

        self.game_ver_dd = QComboBox()
        self.game_ver_dd.setPlaceholderText("Loading versions...")
        self.show_snapshots_box = QCheckBox()
        self.show_snapshots_box.setChecked(False)
        self.loader_ver_dd = QComboBox()
        self.loader_ver_dd.setPlaceholderText("Loading versions...")

        game_ver_w = QWidget()
        game_ver_lo = QHBoxLayout(game_ver_w)
        game_ver_lo.addWidget(QLabel("Minecraft version:"))
        game_ver_lo.addWidget(self.game_ver_dd, 1)

        loader_ver_w = QWidget()
        loader_ver_lo = QHBoxLayout(loader_ver_w)
        loader_ver_lo.addWidget(QLabel("Fabric version:"))
        loader_ver_lo.addWidget(self.loader_ver_dd, 1)

        layout.addWidget(game_ver_w)
        layout.addWidget(loader_ver_w)

        self.install_button = QPushButton("Install Fabric")
        self.install_button.setDisabled(True)
        self.install_button.clicked.connect(self._install)

        layout.addWidget(self.install_button)

    def load(self):
        self.game_ver_dd.addItem("")
        game_vers = fabric.get_game_versions_list()
        for v in game_vers:
            self.game_ver_dd.addItem(v[0], v[1])
        self.game_ver_dd.setCurrentIndex(0)
        self.game_ver_dd.currentTextChanged.connect(
            self._game_ver_dd_txt_change
        )
        self.game_ver_dd.currentTextChanged.connect(self._set_button_disabled)
        self.loader_ver_dd.addItem("")
        self.loader_ver_dd.addItems(fabric.get_loader_versions_list())
        self.loader_ver_dd.setCurrentIndex(0)
        self.loader_ver_dd.currentTextChanged.connect(
            self._loader_ver_dd_txt_change
        )
        self.loader_ver_dd.currentTextChanged.connect(self._set_button_disabled)
        return

    def exec(self):
        self.show()
        self.load()
        return super().exec()

    def _game_ver_dd_txt_change(self, text: str):
        if text:
            self.game_ver_selected = True
        else:
            self.game_ver_selected = False

    def _loader_ver_dd_txt_change(self, text: str):
        if text:
            self.loader_ver_selected = True
        else:
            self.loader_ver_selected = False

    def _set_button_disabled(self, text: str):
        if self.game_ver_selected and self.loader_ver_selected:
            self.install_button.setDisabled(False)
        else:
            self.install_button.setDisabled(True)

    def _install(self):
        game_ver = self.game_ver_dd.currentText()
        loader_ver = self.loader_ver_dd.currentText()
        if not game_ver:
            raise ValueError("Game version selection is empty")
        if not loader_ver:
            raise ValueError("Loader version selection is empty")
        fab_v = f"fabric-loader-{loader_ver}-{game_ver}"
        try:
            success = fabric.install(game_ver, loader_ver)
        except FileExistsError:
            msg_box = QMessageBox.question(
                self,
                "Fabric already installed",
                f"fabric-loader-{fab_v} is already installed, re-install it?"
                % (loader_ver, game_ver),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if msg_box == QMessageBox.StandardButton.Yes:
                success = fabric.install(game_ver, loader_ver, True)
            else:
                return
        if success:
            QMessageBox.information(
                self, "Success", f"Successfully installed {fab_v}"
            )
            self.installed_fabric.emit()
            self.done(QDialog.DialogCode.Accepted)
