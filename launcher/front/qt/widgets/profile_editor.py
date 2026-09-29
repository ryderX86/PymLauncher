# pylint:disable=unused-import,unused-variable
from collections.abc import Callable
from dataclasses import dataclass, field
from types import MethodType
from typing import Any, ClassVar, Final, Iterable, Literal
import logging
import os
import time

from PySide6.QtCore import (
    QCoreApplication,
    QRegularExpression,
    QSignalBlocker,
    QSize,
    Qt,
    QTimer,
    Signal,
    SignalInstance,
    Slot,
)
from PySide6.QtGui import QRegularExpressionValidator, QShowEvent, QValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher import constants, paths
from launcher.back import profile_manager, version_manager
from launcher.datatypes import LaunchProfile
from launcher.front import resources
from launcher.front.qt import BindingMixin
from launcher.front.qt.validator import (
    ProfileRAMValidator,
    ProfileResolutionTextValidator,
    VersionTextValidator,
)
from launcher.front.qt.widgets import Header2, IconPickerButton, TooltipHint
from launcher.functions import Suppressable, is_path_valid

from .config_checkbox import ConfigCheckbox

log = logging.getLogger(__name__)

SPACING = 8


def _def_normalize(a: Any):
    return a


def _def_valid():
    return True


@dataclass(slots=True, kw_only=True, eq=False)
class WidgetMappingAdapter:
    # dataclass values
    read: Callable[[], str | int | bool]
    """Function that we use to read what's inside the widget"""
    write: (
        Callable[[str | None], None]
        | Callable[[int | None], None]
        | Callable[[bool | None], None]
        | Callable[[str], None]
        | Callable[[int], None]
        | Callable[[bool], None]
    )
    """Function we call to write to the widget's value"""
    normalize: Callable[[Any], Any] = field(default=_def_normalize)
    """Normalize the value for saving/comparison"""
    attr_name: str
    """The profile's attribute name"""
    signal: SignalInstance
    """The "value edited" signal"""
    widget: QWidget | None = field(default=None)

    # private/instance attributes
    _startup_val: str | int | bool = field(init=False, hash=True, compare=True)

    def __post_init__(self):
        self._startup_val = self.normalize(self.read())

    def reset_known(self, prof: LaunchProfile):
        self._startup_val = self.normalize(getattr(prof, self.attr_name))

    def reset(self):
        self.write(self._startup_val)  # type: ignore

    def changed(self) -> bool:
        return self.normalize(self.read()) != self._startup_val

    @property
    def data_valid(self) -> bool:
        match self.widget:
            case QLineEdit():
                return self.widget.hasAcceptableInput()
            case QComboBox() if self.widget.lineEdit():
                return (
                    self.widget.lineEdit().hasAcceptableInput()  # type: ignore
                )
            case _:
                return True

    def set_invalid_display(self, invalid: bool):
        if not self.widget:
            log.warning(
                "%s: No widget to set invalid property for",
                type(self).__name__,
            )
            return
        self.widget.setProperty("invalid", invalid)
        self.widget.style().unpolish(self.widget)
        self.widget.style().polish(self.widget)


def _get_browse_window(
    win_title: str,
    default_dir: str,
    w: QLineEdit,
    ext_filter: str | None = None,
    get_file: bool = False,
):
    if not QCoreApplication.instanceExists():
        log.warning(
            "Ignoring browse window request, no QCoreApplication exists."
        )
        return
    if w.text() and is_path_valid(w.text()):
        default_dir = os.path.split(w.text())[0]
    if get_file:
        assert ext_filter is not None
        path, _ = QFileDialog.getOpenFileName(
            w.window(), win_title, default_dir, filter=ext_filter
        )
    else:
        path = QFileDialog.getExistingDirectory(
            w.window(), win_title, default_dir
        )
    if not path:
        return
    if not is_path_valid(path):
        if get_file:
            raise ValueError(f"Invalid file path: {path!r}")
        else:
            raise ValueError(f"Invalid directory: {path!r}")
    w.setText(path)


def get_browse_row(
    w: QLineEdit,
    win_title: str,
    open_default_dir: str,
    gets_file: bool = False,
    file_extensions: Iterable[tuple[str, str]] | None = None,
):
    if file_extensions:
        exts: list[str] = []
        for label, ext in file_extensions:
            actual_ext = ext.strip("*").strip(".")
            exts.append(f"{label} (*.{actual_ext})")
        exts.append("")
        exts.append("All Files (*)")
        exts_str = ";".join(exts)
        del exts
    else:
        exts_str = None
    # results in something like "Image Files (*.png);;All Files (*)"

    row = QHBoxLayout()
    row.addWidget(w)
    row.setSpacing(SPACING)

    browse_button = QPushButton(resources.symbol("folder-symlink"), "Browse")
    browse_button.clicked.connect(
        lambda: _get_browse_window(
            win_title, open_default_dir, w, exts_str, gets_file
        )
    )
    browse_button.setProperty("large", True)
    row.addWidget(browse_button)
    return row


class ProfileEditor(BindingMixin, QWidget):
    # widget, current data for widget, attr for current data in profile
    _widget_checks: set[WidgetMappingAdapter]

    _current_profile: LaunchProfile
    _dirty: bool
    _can_save: bool
    _version_last_changed: float
    """
    Used to cancel the background thread for argument retrieval.

    Update on profile changed as well.
    """
    _force_refresh_versions_list: bool
    """Used in `_versions_refresh_button()`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widget_checks = set()
        self._dirty = False
        self._can_save: bool = False
        self._force_refresh_versions_list = False

        self.path_validator = QRegularExpressionValidator(
            constants.FP_REGEX, self
        )

        # required to be last
        self._build_ui()

    def bind(self):
        """
        Load necessary info/current profile after bootstrap is complete.

        Final-stage UI loading function for all main widgets, right before it's
        showtime.
        """

        # connect signals:
        for adapter in self._widget_checks:
            adapter.signal.connect(self.data_changed)

        _ = QSignalBlocker(self)  # block signals until GC'd

        with self.data_changed.suppressed():
            profile_manager.add_profile_switch_handler(self._load_profile)
            profile_manager.add_profile_refresh_handler(self._load_profile)

            # set the comboboxes
            self.resolution_selector.addItems(
                self.resolution_validator.set_resolutions(self.screen())
            )
            self.resolution_selector.setCurrentText("Automatic")
            self._latest_release_text = (
                constants.LATEST_VERSION_TEXT_UI.format(
                    version_manager.get_latest_release()
                )
            )
            self._latest_snapshot_text = (
                constants.LATEST_SNAPSHOT_TEXT_UI.format(
                    version_manager.get_latest_snapshot()
                )
            )
            self.game_dir_input.setPlaceholderText(paths.game)
            self._version_validator.load()
            self.refresh_version_combo()

        self._load_profile()
        return

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)

        heading = Header2("Edit Profile")
        root.addWidget(heading, 0)

        # icon picker
        self.icon_picker = IconPickerButton()
        self._widget_checks.add(
            WidgetMappingAdapter(
                read=self.icon_picker.text,
                write=self.icon_picker.setText,
                attr_name="icon",
                signal=self.icon_picker.icon_changed,
                normalize=lambda d: d or None,
            )
        )
        root.addWidget(
            self.icon_picker,
            stretch=0,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        self.form_layout = QFormLayout(
            labelAlignment=Qt.AlignmentFlag.AlignVCenter
            | Qt.AlignmentFlag.AlignRight,
            verticalSpacing=12,
            horizontalSpacing=SPACING,
        )
        root.addLayout(self.form_layout, 0)

        # name input
        self.name_input_area = QLineEdit()
        self._widget_checks.add(
            WidgetMappingAdapter(
                read=self.name_input_area.text,
                write=self.name_input_area.setText,
                signal=self.name_input_area.textChanged,
                attr_name="name",
            )
        )
        self.form_layout.addRow("Name:", self.name_input_area)

        # version selector
        version_select_row = QHBoxLayout()
        version_select_row.setSpacing(SPACING)
        self.version_combo_box = QComboBox(editable=True)
        self._version_validator = VersionTextValidator()
        self.version_combo_box.setValidator(self._version_validator)
        self._widget_checks.add(
            WidgetMappingAdapter(
                read=self.version_combo_box.currentData,
                write=self.set_version_text,
                signal=self.version_combo_box.currentIndexChanged,
                attr_name="version_id",
            )
        )
        version_select_row.addWidget(self.version_combo_box, 1)
        self.version_refresh = QPushButton()
        self.version_refresh.setProperty("large", True)
        self.version_refresh.setIcon(resources.symbol("refresh"))
        self.version_refresh.clicked.connect(self._versions_refresh_button)
        self.version_refresh.setMaximumWidth(32)
        version_select_row.addWidget(self.version_refresh, 0)
        self.form_layout.addRow("Version:", version_select_row)

        # show version-types
        show_versions_row = QHBoxLayout()
        show_versions_row.setSpacing(SPACING)
        self.show_snapshots_toggle = ConfigCheckbox(
            "Show snapshots", "show_snapshots"
        )
        self.show_snapshots_toggle.clicked.connect(self.refresh_version_combo)
        show_versions_row.addWidget(self.show_snapshots_toggle)
        self.show_old_toggle = ConfigCheckbox(
            "Show old releases", "show_old_releases"
        )
        self.show_old_toggle.clicked.connect(self.refresh_version_combo)
        show_versions_row.addWidget(self.show_old_toggle)
        self.form_layout.addRow("", show_versions_row)

        # game dir
        self.game_dir_input = QLineEdit()
        self.game_dir_input.setValidator(self.path_validator)
        self._widget_checks.add(
            WidgetMappingAdapter(
                attr_name="game_dir",
                read=self.game_dir_input.text,
                write=self.game_dir_input.setText,
                normalize=lambda t: t or None,
                signal=self.game_dir_input.textChanged,
            )
        )
        self.form_layout.addRow(
            "Game Directory:",
            get_browse_row(
                self.game_dir_input,
                "Select Game Directory",
                os.path.expanduser("~"),
            ),
        )

        # jvm binary
        self.jvm_binary_input = QLineEdit(
            placeholderText="Use default Java installation"
        )
        self.jvm_binary_input.setValidator(self.path_validator)
        self._widget_checks.add(
            WidgetMappingAdapter(
                attr_name="java_path",
                read=self.jvm_binary_input.text,
                write=self.jvm_binary_input.setText,
                normalize=lambda t: t or None,
                signal=self.jvm_binary_input.textChanged,
            )
        )
        self.form_layout.addRow(
            "Java Executable:",
            get_browse_row(
                self.jvm_binary_input,
                "Select Java Executable",
                os.path.realpath(constants.OS_PATH_DELIM),
                True,
                [("Executable File", "exe")],
            ),
        )

        # jvm args
        self.jvm_args_input = QLineEdit(
            placeholderText="Use default arguments", clearButtonEnabled=True
        )
        self._widget_checks.add(
            WidgetMappingAdapter(
                attr_name="_jvm_args",
                read=self.jvm_args_input.text,
                write=self.jvm_args_input.setText,
                normalize=lambda t: t or None,
                signal=self.jvm_args_input.textChanged,
            )
        )
        self.form_layout.addRow("JVM Arguments:", self.jvm_args_input)

        # memory min/max
        mem_row = QHBoxLayout()
        mem_row.setSpacing(SPACING)
        mem_row.setContentsMargins(2, 0, 2, 0)
        memory_validator = ProfileRAMValidator(parent=self)

        #   min
        memory_min_label = QLabel("Minimum:")
        self.memory_min = QLineEdit("512M", maxLength=6)
        self.memory_min.setMaximumWidth(72)
        self.memory_min.setValidator(memory_validator)
        self._widget_checks.add(
            WidgetMappingAdapter(
                attr_name="memory_min",
                read=self.memory_min.text,
                write=self.memory_min.setText,
                normalize=lambda t: t.upper() or None,
                signal=self.memory_min.textChanged,
                widget=self.memory_min,
            )
        )
        mem_row.addWidget(memory_min_label)
        mem_row.addWidget(self.memory_min)

        #   max
        memory_max_label = QLabel("Maximum")
        self.memory_max = QLineEdit("4G", maxLength=6)
        self.memory_max.setMaximumWidth(72)
        self.memory_max.setValidator(memory_validator)
        self._widget_checks.add(
            WidgetMappingAdapter(
                attr_name="memory_max",
                read=self.memory_max.text,
                write=self.memory_max.setText,
                normalize=lambda t: t.upper() or None,
                signal=self.memory_max.textChanged,
                widget=self.memory_max,
            )
        )
        mem_row.addWidget(memory_max_label)
        mem_row.addWidget(self.memory_max)

        mem_row.addStretch(1)

        self.form_layout.addRow("Memory:", mem_row)

        self.resolution_validator = ProfileResolutionTextValidator()
        self.resolution_selector = QComboBox(editable=True)
        self.resolution_selector.setValidator(self.resolution_validator)
        self.resolution_selector.setMask("Nnnn0A900000")
        self.resolution_selector.setPlaceholderText("Automatic")
        self.resolution_selector.currentTextChanged.connect(
            self._resolution_selector_update
        )
        self._widget_checks.add(
            WidgetMappingAdapter(
                attr_name="resolution",
                read=self.resolution_selector.currentText,
                write=self.resolution_selector.setEditText,
                normalize=lambda t: (
                    t.lower()
                    if bool(t) is not False and t != "Automatic"
                    else None
                ),
                signal=self.resolution_selector.currentTextChanged,
            )
        )
        self.form_layout.addRow("Window Size:", self.resolution_selector)

        # mods folder
        self.mods_folder_row = QHBoxLayout()
        self.mods_folder_row.setSpacing(SPACING)
        self.use_mods_folder_input = QCheckBox("Custom folder")
        self.use_mods_folder_input.setToolTip(
            "[Experimental] Fabric >=0.12.0 supports custom mods folders"
        )
        self.use_mods_folder_input.setChecked(False)
        self.use_mods_folder_input.setEnabled(False)
        self.mods_folder_row.addWidget(self.use_mods_folder_input)

        self.mods_folder_input = QLineEdit(
            placeholderText=os.path.join(paths.game, "mods")
        )
        self.mods_folder_input.setDisabled(True)
        self.mods_folder_input.setValidator(self.path_validator)
        self._widget_checks.add(
            WidgetMappingAdapter(
                attr_name="mods_folder",
                read=self.mods_folder_input.text,
                write=self.mods_folder_input.setText,
                normalize=lambda t: (
                    t.rstrip(constants.OS_PATH_DELIM) if t else None
                ),
                signal=self.mods_folder_input.textChanged,
            )
        )
        self.mods_folder_row.addLayout(
            get_browse_row(
                self.mods_folder_input, "Select Mods Folder", paths.game
            )
        )
        self.use_mods_folder_input.checkStateChanged.connect(
            self._use_mods_folder_changed
        )

        self.form_layout.addRow("Mods folder:", self.mods_folder_row)

        # save/reset/delete buttons
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(SPACING)
        self.save_button = QPushButton("Save")
        self.save_button.setDisabled(True)
        self.save_button.clicked.connect(self.save)
        buttons_row.addWidget(self.save_button)
        self.reset_button = QPushButton("Reset")
        self.reset_button.setDisabled(True)
        self.reset_button.clicked.connect(self.reset)
        buttons_row.addWidget(self.reset_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.setDisabled(True)
        self.delete_button.clicked.connect(self.delete)
        buttons_row.addWidget(self.delete_button)

        root.addStretch(1)
        root.addLayout(buttons_row)

        return

    def set_version_text(self, actual_data: str):
        idx = self.version_combo_box.findData(
            actual_data, flags=Qt.MatchFlag.MatchExactly
        )
        if idx >= 0:
            self.version_combo_box.setCurrentIndex(idx)
        elif actual_data == "latest-snapshot":
            self.version_combo_box.setCurrentText(
                self._version_validator.latest_snapshot_ui
            )
        else:
            self.version_combo_box.setCurrentText(actual_data)

    def _load_profile(self, *args):
        _ = QSignalBlocker(self)  # block signals until GC'd
        with self.data_changed.suppressed():
            self._current_profile = profile_manager.get_current_profile()
            # QoL UI stuff
            if self._current_profile.game_dir:
                self.mods_folder_input.setPlaceholderText(
                    os.path.join(self._current_profile.game_dir, "mods")
                )
            else:
                self.mods_folder_input.setPlaceholderText(
                    os.path.join(paths.game, "mods")
                )

            # show/hide/set the checkbox for the mods folder
            mods_row_enabled = version_manager.check_fabric_mod_arg_support(
                self._current_profile.version_id
            )
            self.form_layout.setRowVisible(
                self.mods_folder_row,
                mods_row_enabled,
            )
            self.mods_folder_input.setEnabled(mods_row_enabled)
            self.use_mods_folder_input.setChecked(
                bool(self._current_profile.mods_folder)
            )
            self.use_mods_folder_input.setEnabled(mods_row_enabled)

            for adapter in self._widget_checks:
                adapter.reset_known(self._current_profile)
                adapter.reset()

            match self._current_profile.type:
                case "latest-release" | "latest-snapshot":
                    self.version_combo_box.setDisabled(True)
                case _:
                    self.version_combo_box.setDisabled(False)
        self._dirty = False
        self._can_save = True
        self._set_save_buttons()

    @Slot()
    def save(self):
        for adapter in self._widget_checks:
            if getattr(
                self._current_profile, adapter.attr_name, None
            ) != adapter.normalize(adapter.read()):
                setattr(
                    self._current_profile,
                    adapter.attr_name,
                    adapter.normalize(adapter.read()),
                )
        profile_manager.save_single_profile(self._current_profile)

    @Slot()
    def reset(self):
        with self.data_changed.suppressed():
            for adapter in self._widget_checks:
                adapter.reset()
        if self._current_profile.mods_folder:
            self.use_mods_folder_input.setChecked(True)
        else:
            self.use_mods_folder_input.setChecked(False)
        self.data_changed()
        if self._dirty:
            log.warning("Reset, but editor is still dirty!")

    @Slot()
    def delete(self):
        result = QMessageBox.warning(
            self,
            "Delete Profile",
            f'Are you sure you want to delete "{self._current_profile.name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        match result:
            case QMessageBox.StandardButton.Yes:
                profile_manager.delete_single_profile(self._current_profile)
            case _:
                return

    @Slot(object)
    @Slot()
    @Suppressable
    def data_changed(self, *_):
        self._dirty = False
        self._can_save = True
        for adapter in self._widget_checks:
            if adapter.changed():
                self._dirty = True
            if not adapter.data_valid:
                self._can_save = False
            if adapter.widget:
                adapter.set_invalid_display(not adapter.data_valid)
        self._set_save_buttons()
        return

    def _set_save_buttons(self):
        self.save_button.setEnabled(self._can_save and self._dirty)
        self.reset_button.setEnabled(self._dirty)
        self.delete_button.setEnabled(
            self._current_profile.type
            not in {"latest-release", "latest-snapshot"}
        )

    @Slot(str)
    @Slot()
    def _get_jvm_args(self, new_text: str = ""): ...

    @Slot()
    def __vrb_timeout(self):
        self._force_refresh_versions_list = False

    @Slot()
    def _versions_refresh_button(self):
        log.debug("User requested versions list refresh")
        if self._force_refresh_versions_list:
            log.debug("Force downloading new versions manifest")
            version_manager.fetch_version_manifest(True)
            version_manager.get_version_list(True)
        self.refresh_version_combo()
        self._force_refresh_versions_list = True
        QTimer.singleShot(200, self.__vrb_timeout)

    @Slot(Qt.CheckState)
    @Slot()
    def refresh_version_combo(self, *_):
        current = self.version_combo_box.currentText()
        found_text = False
        with self.data_changed.suppressed():
            self.version_combo_box.clear()
            for text, data in self._version_validator.iter_versions_combobox():
                self.version_combo_box.addItem(text, data)
                if text == current:
                    self.version_combo_box.setCurrentIndex(
                        self.version_combo_box.findText(
                            current, Qt.MatchFlag.MatchExactly
                        )
                    )
                    found_text = True
            if not found_text:
                self.version_combo_box.setCurrentIndex(-1)
                self.version_combo_box.setCurrentText(current)

    @Slot(str)
    def _resolution_selector_update(self, new_text: str):
        self.resolution_selector.setProperty(
            "default", new_text == "Automatic"
        )

    @Slot(Qt.CheckState)
    def _use_mods_folder_changed(self, state: Qt.CheckState):
        if state == Qt.CheckState.Checked:
            self.mods_folder_input.setDisabled(False)
            if self._current_profile.mods_folder:
                self.mods_folder_input.setText(
                    self._current_profile.mods_folder
                )
        elif state == Qt.CheckState.Unchecked:
            self.mods_folder_input.clear()
            self.mods_folder_input.setDisabled(True)

    @property
    def dirty(self):
        return self._dirty
