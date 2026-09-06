import logging

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher.back import fabric
from launcher.front.window import (
    ButtonConfig,
    WarningDialog,
    WarningType,
)
from launcher.functions import error_box
from launcher.offline import offline_man

log = logging.getLogger(__name__)


class FabricLoadThread(QThread):
    loaded = Signal()
    error = Signal(Exception)
    log = log.getChild(__name__)

    def run(self):
        try:
            self.game_versions = fabric.get_game_versions_list()
        except Exception as err:
            self.log.error(
                "Error occured getting fabric game versions list:",
                exc_info=err,
            )
            offline_man.check_requests_error(err)
            self.error.emit(err)
            return
        try:
            self.loader_versions = fabric.get_loader_versions_list()
        except Exception as err:
            self.log.error(
                "Error occured getting fabric loader list:", exc_info=err
            )
            offline_man.check_requests_error(err)
            self.error.emit(err)
            return
        self.loaded.emit()
        return


class FabricInstallWindow(QDialog):
    installed_fabric = Signal()

    # instance attributes
    is_loaded: bool
    loader_thread: FabricLoadThread | None
    game_vers: list[tuple[str, bool]]
    loader_vers: list[str]

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
        self.loader_thread = None
        self.is_loaded = False
        self.game_vers = []
        self.loader_vers = []

    def close(self) -> bool:
        if self.loader_thread and self.loader_thread.isRunning():
            log.warning(
                "User closed Fabric installer window while it's loading! "
                "Things may behave weirdly. Stalling until it's done."
            )
            while self.loader_thread.isRunning():
                pass
        return super().close()

    def closeEvent(self, arg__1: QCloseEvent) -> None:
        if self.loader_thread and self.loader_thread.isRunning():
            log.warning(
                "User closed Fabric installer window while it's loading! "
                "Things may behave weirdly. Stalling until it's done."
            )
            while self.loader_thread.isRunning():
                pass
        return super().closeEvent(arg__1)

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

        self.install_button = QPushButton("Loading...")
        self.install_button.setDisabled(True)
        self.install_button.clicked.connect(self._install)

        layout.addWidget(self.install_button)

    def loader_finished(self):
        assert self.loader_thread
        self.game_vers = self.loader_thread.game_versions
        self.loader_vers = self.loader_thread.loader_versions
        log.debug("Cleaning up thread")
        self.loader_thread.deleteLater()
        self.loader_thread = None
        self.load()

    def loader_error(self, err: Exception):
        assert self.loader_thread
        log.warning(
            "Failed to load Fabric manifests, notifying user and exiting."
        )
        error_box(
            f"Unexpected {type(err).__name__!r} error occured while trying to "
            "get Fabric info."
        )
        self.loader_thread.deleteLater()
        self.loader_thread = None
        self.close()

    def load(self):
        log.debug("Adding game and fabric items to combo boxes...")
        self.game_ver_dd.addItem("")
        game_vers = self.game_vers
        for v in game_vers:
            self.game_ver_dd.addItem(v[0], v[1])
        self.game_ver_dd.setCurrentIndex(0)
        self.game_ver_dd.currentTextChanged.connect(
            self._game_ver_dd_txt_change
        )
        self.game_ver_dd.currentTextChanged.connect(self._set_button_disabled)
        self.loader_ver_dd.addItem("")
        self.loader_ver_dd.addItems(self.loader_vers)
        self.loader_ver_dd.setCurrentIndex(0)
        self.loader_ver_dd.currentTextChanged.connect(
            self._loader_ver_dd_txt_change
        )
        self.loader_ver_dd.currentTextChanged.connect(
            self._set_button_disabled
        )
        self.install_button.setText("Install Fabric")
        self.is_loaded = True
        return

    def exec(self):
        self.show()
        if not self.loader_thread:
            if not self.is_loaded:
                log.debug("Starting new FabricLoadThread()")
                self.loader_thread = FabricLoadThread(self)
                self.loader_thread.loaded.connect(self.loader_finished)
                self.loader_thread.error.connect(self.loader_error)
                self.loader_thread.start()
        elif not self.is_loaded and not self.loader_thread.isRunning():
            self.loader_thread.start()
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
            dialog_input = WarningDialog.warn(
                self,
                "Fabric already installed",
                f"fabric-loader-{fab_v} is already installed, re-install it?",
                WarningType.MODLOADER_VERSION_CONFLICT,
                button_config=ButtonConfig.YES_NO,
            )
            if dialog_input:
                success = fabric.install(game_ver, loader_ver, True)
            else:
                return
        if success:
            QMessageBox.about(  # TODO: subclass QMessageBox for this
                self, "Success", f"Successfully installed {fab_v}"
            )
            self.installed_fabric.emit()
            self.done(QDialog.DialogCode.Accepted)
