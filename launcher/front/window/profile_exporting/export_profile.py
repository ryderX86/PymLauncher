from pathlib import Path
import logging
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher.back.profile_exporting import PortableProfile
from launcher.datatypes.launch_profile import LaunchProfile
from launcher.front import resources

from . import Status

log = logging.getLogger(__name__)


class ProfileExporter(QThread):
    done = Signal(int)
    progress = Signal(int, int)
    step = Signal(str, int)

    def __init__(
        self,
        parent,
        destination,
        prof: PortableProfile,
        includes: dict | None = None,
    ):
        super().__init__(parent)
        self._destination_zip = destination
        self._include = includes or {}
        self.profile = prof
        self._current_step_label = ""
        self._max = 0
        self._done = 0

    def _step(self, msg: str, max_: int):
        self._current_step_label = msg
        self._max = max_
        self._done = 0
        self.step.emit(self._current_step_label, self._max)

    def _progress(self):
        self._done += 1

    def run(self):
        status = Status.INTERRUPTED
        try:
            self.profile.export(self._destination_zip, **self._include)
        except ValueError as err:
            log.error("ValueError in export function:", exc_info=err)
            status = Status.ERROR_ARGS
        else:
            status = Status.SUCCESS
        self.done.emit(status)
        return


class ExportProfileDialog(QDialog):
    def __init__(self, prof: LaunchProfile, parent=None):
        super().__init__(parent)
        self.profile = PortableProfile(prof)
        self._destination = str(Path("~/Documents").resolve())
        self._includes = {
            "mods": True,
            "resource_packs": True,
            "options_txt": False,
            "saves": False,
            "screenshots": False,
            "versions": False,
            "config": True,
            "coremods": True,
            "menuworlds": False,
            "debug_profile": False,
        }
        self._build_ui()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)

        self.fmt_sel = QComboBox()
        self.fmt_sel.addItem("Vanilla", "default")
        self._layout.addWidget(self.fmt_sel)

        output_w = QWidget()
        output_w.setContentsMargins(0, 0, 0, 0)
        output_row = QHBoxLayout(output_w)

        self.dest_path_text = QLineEdit()
        output_row.addWidget(self.dest_path_text, 1)

        self.dest_path_browse = QPushButton("Browse")
        self.dest_path_browse.setIcon(resources.symbol("folder-symlink"))
        self.dest_path_browse.clicked.connect(self._browse_dest)
        output_row.addWidget(self.dest_path_browse)

        self._layout.addWidget(output_w)

        include_mods = QCheckBox("Include mods")
        include_mods.setEnabled(self.profile.mods)
        include_mods.setChecked(self.profile.mods and self._includes["mods"])
        include_mods.checkStateChanged.connect(
            lambda c: self._includes.__setitem__(
                "mods", c == Qt.CheckState.Checked
            )
        )
        self._layout.addWidget(include_mods)

        include_options = QCheckBox("Include options.txt")
        include_options.setEnabled(self.profile.options_txt)
        include_options.setChecked(
            self.profile.options_txt and self._includes["options_txt"]
        )
        include_options.checkStateChanged.connect(
            lambda c: self._includes.__setitem__(
                "options_txt", c == Qt.CheckState.Checked
            )
        )
        self._layout.addWidget(include_options)

        include_rps = QCheckBox("Include Resource Packs")
        include_rps.setEnabled(self.profile.resource_packs)
        include_rps.setChecked(
            self.profile.resource_packs and self._includes["resource_packs"]
        )
        include_rps.checkStateChanged.connect(
            lambda c: self._includes.__setitem__(
                "resource_packs", c == Qt.CheckState.Checked
            )
        )
        self._layout.addWidget(include_rps)

        include_ss = QCheckBox("Include Screenshots")
        include_ss.setEnabled(self.profile.screenshots)
        include_ss.setChecked(
            self.profile.screenshots and self._includes["screenshots"]
        )
        include_ss.checkStateChanged.connect(
            lambda c: self._includes.__setitem__(
                "screenshots", c == Qt.CheckState.Checked
            )
        )
        self._layout.addWidget(include_ss)

        include_vers = QCheckBox("Include Versions")
        include_vers.setEnabled(self.profile.versions)
        include_vers.setChecked(
            self.profile.versions and self._includes["versions"]
        )
        include_vers.checkStateChanged.connect(
            lambda c: self._includes.__setitem__(
                "versions", c == Qt.CheckState.Checked
            )
        )
        self._layout.addWidget(include_vers)

        include_config = QCheckBox("Include Mod Configs")
        include_config.setEnabled(self.profile.config)
        include_config.setChecked(
            self.profile.config and self._includes["config"]
        )
        include_config.checkStateChanged.connect(
            lambda c: self._includes.__setitem__(
                "config", c == Qt.CheckState.Checked
            )
        )
        self._layout.addWidget(include_config)

        include_saves = QCheckBox("Include Saves")
        include_saves.setEnabled(self.profile.saves)
        include_saves.setChecked(
            self.profile.saves and self._includes["saves"]
        )
        include_saves.checkStateChanged.connect(
            lambda c: self._includes.__setitem__(
                "saves", c == Qt.CheckState.Checked
            )
        )
        self._layout.addWidget(include_saves)

        actions = QWidget()
        actions.setContentsMargins(0, 0, 0, 0)
        action_row = QHBoxLayout(actions)
        action_row.addStretch()

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        action_row.addWidget(cancel)

        export = QPushButton("Export")
        export.setProperty("accent", True)
        export.clicked.connect(self.export)
        action_row.addWidget(export)

        self._layout.addWidget(actions)

    @classmethod
    def deploy(cls, profile: LaunchProfile, parent=None):
        self = cls(profile, parent)
        return self.exec()

    def export(self):
        if not self._destination:
            return
        if not max(self._includes.values()):
            return
        if os.path.isfile(self._destination):
            overwrite = QMessageBox.question(
                self,
                "Overwrite file?",
                f'A file exists at "{self._destination}"\n'
                "Would you like to replace it?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.Cancel,
            )
            if overwrite != QMessageBox.StandardButton.Yes:
                return
        self.profile.export(
            self.fmt_sel.currentData(), self._destination, **self._includes
        )
        self.accept()

    def _browse_dest(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Save file as...")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setOptions(QFileDialog.Option.DontConfirmOverwrite)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        if not dialog.exec():
            return

        fp = dialog.selectedFiles()[0]
        self._destination = fp
        self.dest_path_text.setText(fp)
