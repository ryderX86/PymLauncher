"""
minecraftlauncher.front.window.main.profiles_page

Profile management page.

TODOs:
- Rework the editor state check (clean/dirty)
- Possibly replace the default Qt mapper with the custom one used by
  settings_page
- Find a way to make "latest-release" and "latest-snapshot" use friendlier names
- Are colored save/delete buttons really necessary here?
"""

from pathlib import Path
import logging
import time
import os

from PySide6.QtCore import Qt, Signal, QThread, QSize, QEvent
from PySide6.QtGui import (
    QAction,
    QContextMenuEvent,
    QMouseEvent,
    QShortcut,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QDataWidgetMapper,
    QListView,
    QCheckBox,
    QMenu,
)

from minecraftlauncher import DEV
from minecraftlauncher.datatypes.game_version import GameVersionStub
from minecraftlauncher.back.profile_manager import (
    GameProfile,
    load_launcher_profiles,
    save_single_profile,
)
from minecraftlauncher.back import version_manager, profile_manager
from minecraftlauncher.front import styles, resources
from minecraftlauncher.front.qt.models import (
    ProfileSelectionModel,
    ProfileModel,
)
from minecraftlauncher.front.qt.widgets import (
    IconPickerButton,
    Header1,
    Header2,
)
from minecraftlauncher.front.qt.validator import (
    ProfileRAMValidator,
    VersionTextValidator,
    ProfileResolutionTextValidator,
    FilePathValidator,
    QValidatorWithStoredResults,
)
from minecraftlauncher.front.window.profile_exporting.export_profile import (
    ExportProfileDialog,
)
from minecraftlauncher.front.window import (
    WarningDialog,
    WarningType,
    ButtonConfig,
)
from minecraftlauncher.functions import copy_to_clipboard
from minecraftlauncher.ostools import set_jump_list
from minecraftlauncher import constants, config

log = logging.getLogger(__name__)

# TODO: calculate resolutions instead of statically setting them
COMMON_RESOLUTIONS = [
    (854, 480),
    (1280, 720),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
    (3840, 2160),
]

MapIndex = ProfileModel.MapIndex

_running_threads = []


def _right_click_decorator(func):
    _func = func

    def decorated_func(e: QEvent | QMouseEvent | None):
        if not e or not isinstance(e, QMouseEvent):
            return _func(e)
        if e.buttons() & Qt.MouseButton.RightButton:
            return None
        return _func(e)

    return decorated_func


class VersionJsonBackgroundDownloader(QThread):
    done = Signal(str)

    log = log.getChild("VersionJsonBackgroundDownloader()")

    def __init__(self, version_id: str, profile: GameProfile, parent=None):
        super().__init__(parent)
        self._version_id = version_id
        self._profile = profile

    def run(self):
        if self._profile.has_custom_args:
            self.done.emit("")
            return
        match self._version_id.lower():
            case "latest-release" | "latest release":
                self._version_id = version_manager.get_latest_release()
            case "latest-snapshot" | "latest snapshot":
                self._version_id = version_manager.get_latest_release()
        version_list = version_manager.get_version_list()
        version: GameVersionStub | None = None
        for v in version_list:
            if v.id == self._version_id:
                version = v
                break
        if not version:
            self.log.warning(
                "Failed to get version info for '%s'", self._version_id
            )
            self.done.emit("INVALID")
            return
        version_json = version_manager.resolve_inheritence(version.get_json())
        args = version_manager.default_user_jvm_args_factory(version_json)
        self.done.emit(args)
        self.destroyed.connect(lambda: _running_threads.remove(self))


class ProfilesPage(QWidget):
    """Profile page"""

    status_update = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.log = log.getChild("ProfilesPage")
        self.select = ProfileSelectionModel.instance()
        self.model = self.select.model()
        self.mapper = QDataWidgetMapper(self)
        self.mapper.setModel(self.model)
        self.select.currentChanged.connect(
            lambda a, b: self.mapper.setCurrentIndex(a.row())
        )
        self.mapper.currentIndexChanged.connect(self._dirty_check)
        self._dirty = False
        self._loaded = False
        self._validity_state = True
        self._fp_validator = FilePathValidator(self)
        self._build_ui()
        if constants.OS != "osx":
            key_seq = QKeySequence(
                Qt.Modifier.CTRL | Qt.Key.Key_S  # type: ignore
            )
        else:
            key_seq = QKeySequence(
                Qt.Modifier.META | Qt.Key.Key_S  # type: ignore
            )
        shortcut = QShortcut(key_seq, self)
        shortcut.activated.connect(self._ctrl_s)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._bg_worker: VersionJsonBackgroundDownloader | None = None
        self._ver_refresh_last_click: float = 0.0

    def _ctrl_s(self):
        if self.save_button.isEnabled():
            self._save()

    def build(self):
        self._load()
        self._loaded = True

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        #
        # Left-side layout
        #
        left = QWidget()
        left.setFixedWidth(250)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 16, 12, 16)
        left.setBackgroundRole(styles.CRole.Mid)
        left.setAutoFillBackground(True)

        label = Header1("Profiles")
        left_layout.addWidget(label)

        button_row_w = QWidget()
        button_row = QHBoxLayout(button_row_w)
        button_row.setContentsMargins(0, 0, 0, 0)
        new_icon = resources.symbol("journal-plus")
        button_new = QPushButton(new_icon, "New Profile")
        button_new.setProperty("large", True)
        button_new.clicked.connect(self._new_profile)
        button_row.addWidget(button_new, 1)
        button_export = QPushButton()
        button_export.setProperty("large", True)
        button_export.setIcon(resources.symbol("share"))
        button_export.setMaximumWidth(36)
        button_export.setToolTip("Export Current Profile")
        # button_row.addWidget(button_export)
        button_import = QPushButton()
        button_import.setProperty("large", True)
        button_import.setIcon(resources.symbol("import"))
        button_import.setMaximumWidth(36)
        button_import.setToolTip("Import Profile")
        # button_row.addWidget(button_import)
        # may have to relocate
        left_layout.addWidget(button_row_w)

        #
        # Profile list
        #
        self.profile_list = QListView()
        self.profile_list.setVerticalScrollMode(
            QListView.ScrollMode.ScrollPerPixel
        )
        # stinky funky workaround
        self.profile_list.mousePressEvent = _right_click_decorator(
            self.profile_list.mousePressEvent
        )

        def _l_ctx_menu(a0):
            return self._profile_list_context_menu(a0)

        self.profile_list.contextMenuEvent = _l_ctx_menu
        # for the context menu, I could have used the customContextMenuRequested
        # event, however that only gives a single `pos` argument that is local
        # to the widget's coordinates, and the `contextMenuEvent` function gives
        # to event with `globalPos()` as an argument allowing me to be much,
        # much lazier with implementation
        self.profile_list.setModel(self.model)
        self.profile_list.setSelectionModel(self.select)
        self.profile_list.setUniformItemSizes(True)
        self.profile_list.setProperty("profiles", True)
        self.profile_list.setIconSize(QSize(32, 32))
        self.profile_list.setSelectionMode(
            self.profile_list.SelectionMode.SingleSelection
        )
        self.profile_list.setSelectionBehavior(
            self.profile_list.SelectionBehavior.SelectRows
        )
        self.profile_list.setDragEnabled(True)
        self.profile_list.setDragDropMode(QListView.DragDropMode.DragDrop)
        left_layout.addWidget(self.profile_list, 1)

        layout.addWidget(left)

        # separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        layout.addWidget(sep)

        #
        # Right-side/editor
        #
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 16, 12, 16)
        right.setBackgroundRole(styles.CRole.Base)
        right.setAutoFillBackground(True)

        edit_label = Header2("Edit Profile")
        right_layout.addWidget(edit_label)

        self.form = QFormLayout()
        self.form.setSpacing(12)
        self.form.setLabelAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )

        # Icon picker
        icon_row_w = QWidget()
        icon_row = QHBoxLayout(icon_row_w)
        icon_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_row.setContentsMargins(0, 0, 0, 0)
        self.icon_picker = IconPickerButton()
        self.icon_picker.icon_changed.connect(self._dirty_check)
        icon_row.addWidget(self.icon_picker)
        right_layout.addWidget(icon_row_w)

        # Name input
        self.name_input = QLineEdit()
        self.mapper.addMapping(self.name_input, MapIndex.NAME)
        self.name_input.textChanged.connect(self._dirty_check)

        self.form.addRow("Name:", self.name_input)

        # Version drop-down/combobox
        version_combo_area = QVBoxLayout()
        version_combo_area.setSpacing(8)

        self.version_combo = QComboBox(
            insertPolicy=QComboBox.InsertPolicy.NoInsert, editable=True
        )
        self.version_combo_view = QListView(self.version_combo)
        self.version_combo.setView(self.version_combo_view)
        self.version_combo.addItems(
            [constants.LATEST_VERSION_TEXT, constants.LATEST_SNAPSHOT_TEXT]
        )
        self._version_id_validator = VersionTextValidator()
        self.version_combo.editTextChanged.connect(self._dirty_check)
        self.version_combo.editTextChanged.connect(self._args_changer)
        self.version_combo.setValidator(self._version_id_validator)
        self.mapper.addMapping(
            self.version_combo, MapIndex.VERSION, b"currentText"
        )
        refresh_versions_button = QPushButton()
        refresh_versions_button.setProperty("large", True)
        refresh_versions_button.setIcon(resources.symbol("refresh"))
        refresh_versions_button.clicked.connect(self.refresh_version_combo)
        refresh_versions_button.setFixedWidth(32)
        version_row = QHBoxLayout()
        version_row.addWidget(self.version_combo, 1)
        version_row.addWidget(refresh_versions_button)
        version_row.setSpacing(12)
        version_combo_area.addItem(version_row)
        version_combo_checkboxes = QHBoxLayout()
        self.show_snapshots_chk = QCheckBox("Show snapshots")
        self.show_snapshots_chk.setChecked(config.show_snapshots)
        self.show_snapshots_chk.checkStateChanged.connect(
            self.version_visibility_changed
        )
        self.show_old_chk = QCheckBox("Show old releases")
        self.show_old_chk.setChecked(config.show_snapshots)
        self.show_old_chk.checkStateChanged.connect(
            self.version_visibility_changed
        )
        version_combo_checkboxes.addWidget(self.show_snapshots_chk)
        version_combo_checkboxes.addWidget(self.show_old_chk)
        version_combo_checkboxes.setAlignment(Qt.AlignmentFlag.AlignLeft)
        version_combo_area.addItem(version_combo_checkboxes)
        self.form.addRow("Version:", version_combo_area)

        # Game directory
        game_dir_row = QHBoxLayout()
        self.game_dir_input = QLineEdit(
            placeholderText=f"...{constants.OS_PATH_DELIM}.minecraft"
        )
        self.game_dir_input.textChanged.connect(self._dirty_check)
        self.game_dir_input.setValidator(self._fp_validator)
        self.mapper.addMapping(self.game_dir_input, MapIndex.GAME_DIR)
        game_dir_row.addWidget(self.game_dir_input, 1)
        self.game_dir_browse_button = QPushButton(
            resources.symbol("folder-symlink"), "Browse"
        )
        self.game_dir_browse_button.setProperty("large", True)
        self.game_dir_browse_button.setFixedWidth(100)
        self.game_dir_browse_button.clicked.connect(self._browse_game_dir)
        game_dir_row.addWidget(self.game_dir_browse_button)
        self.form.addRow("Game Directory:", game_dir_row)

        # Java directory
        java_row = QHBoxLayout()
        self.java_input = QLineEdit(placeholderText="Built-in Java")
        self.java_input.textChanged.connect(self._dirty_check)
        self.java_input.setValidator(self._fp_validator)
        self.mapper.addMapping(self.java_input, MapIndex.JAVA_PATH)
        java_row.addWidget(self.java_input, 1)
        java_browse_button = QPushButton(
            resources.symbol("folder-symlink"), "Browse"
        )
        java_browse_button.setProperty("large", True)
        java_browse_button.setFixedWidth(100)
        java_browse_button.clicked.connect(self._browse_java)
        java_row.addWidget(java_browse_button)
        self.form.addRow("Java Executable:", java_row)

        self.jvm_args_input = QLineEdit(
            placeholderText="(Use default arguments)"
        )
        self.jvm_args_input.textChanged.connect(self._dirty_check)
        self.mapper.addMapping(self.jvm_args_input, MapIndex.JAVA_ARGS)
        self.form.addRow("JVM Arguments:", self.jvm_args_input)

        # Min/max RAM
        memory_row = QHBoxLayout()

        min_label = QLabel("Minimum:")

        self._ram_validator = ProfileRAMValidator()
        # workaround for the dumb stupid label alignment
        min_label.setContentsMargins(0, 0, 0, 4)
        memory_row.addWidget(min_label, 0)
        self.mem_min_input = QLineEdit("512M", maxLength=6)
        self.mem_min_input.setMaximumWidth(72)
        self.mem_min_input.textChanged.connect(self._dirty_check)
        self.mem_min_input.setValidator(self._ram_validator)
        memory_row.addWidget(self.mem_min_input, 0)
        self.mapper.addMapping(self.mem_min_input, MapIndex.MIN_RAM)

        max_label = QLabel("Maximum:")
        max_label.setContentsMargins(0, 0, 0, 4)
        memory_row.addWidget(max_label, 0)
        self.mem_max_input = QLineEdit("4G", maxLength=6)
        self.mem_max_input.setMaximumWidth(72)
        self.mem_max_input.textChanged.connect(self._dirty_check)
        self.mem_max_input.setValidator(self._ram_validator)
        memory_row.addWidget(self.mem_max_input, 0)
        memory_row.addStretch(2)
        self.mapper.addMapping(self.mem_max_input, MapIndex.MAX_RAM)

        self.form.addRow("RAM", memory_row)

        # Game window size
        self.res_combo_box = QComboBox(editable=True)
        self.res_combo_box.setValidator(ProfileResolutionTextValidator())
        self.res_combo_box.setMask("Nnnn0A900000")
        self.res_combo_box.editTextChanged.connect(self._dirty_check)
        self.mapper.addMapping(
            self.res_combo_box, MapIndex.RESOLUTION, b"currentText"
        )
        self._populate_resolution_combo()
        self.form.addRow("Window size:", self.res_combo_box)

        # Mods folder (visible w/ Fabric versions)
        self.mods_folder_row = QHBoxLayout()
        self.use_mods_folder_input = QCheckBox("Custom folder")
        self.use_mods_folder_input.setToolTip(
            "[Experimental] Fabric >=0.12.0 supports custom mods folders"
        )
        self.use_mods_folder_input.setChecked(False)
        self.use_mods_folder_input.setDisabled(True)
        self.use_mods_folder_input.checkStateChanged.connect(
            self._process_mods_folder_checkbox
        )
        self.mods_folder_row.addWidget(self.use_mods_folder_input)
        self.mods_folder_input = QLineEdit(
            placeholderText=f"...{constants.OS_PATH_DELIM}mods",
        )
        self.mods_folder_input.setDisabled(True)
        self.mods_folder_input.setValidator(self._fp_validator)
        self.mods_folder_input.textChanged.connect(self._dirty_check)
        self.mapper.addMapping(self.mods_folder_input, 9)
        self.mods_folder_row.addWidget(self.mods_folder_input)
        self.mods_folder_browse = QPushButton(
            resources.symbol("folder-symlink"), "Browse"
        )
        self.mods_folder_browse.setProperty("large", True)
        self.mods_folder_browse.clicked.connect(self._browse_mods_folder)
        self.mods_folder_browse.setDisabled(True)
        self.mods_folder_row.addWidget(self.mods_folder_browse)
        self.form.addRow("Mods folder:", self.mods_folder_row)

        right_layout.addLayout(self.form)
        right_layout.addStretch()

        # Save/set current/delete buttons
        buttons_row = QWidget()
        buttons_row_layout = QHBoxLayout(buttons_row)

        self.save_button = QPushButton("Save")
        self.save_button.setProperty("accent", True)
        self.save_button.setDisabled(True)
        self.save_button.clicked.connect(self._save)
        self.save_button.setProperty("large", True)
        buttons_row_layout.addWidget(self.save_button)

        self.reset_button = QPushButton("Reset")
        self.reset_button.setDisabled(True)
        self.reset_button.clicked.connect(self._reset)
        self.reset_button.setProperty("large", True)
        buttons_row_layout.addWidget(self.reset_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setProperty("danger", True)
        self.delete_button.setProperty("large", True)
        self.delete_button.clicked.connect(self._delete_profile)
        buttons_row_layout.addWidget(self.delete_button)

        buttons_row_layout.addStretch()

        right_layout.addWidget(buttons_row)

        self.mapper.setSubmitPolicy(QDataWidgetMapper.SubmitPolicy.ManualSubmit)

        layout.addWidget(right, 1)
        self.select.begin_change.connect(self._hook)
        self.form.setRowVisible(self.mods_folder_row, False)

    def _populate_resolution_combo(self):
        self.res_combo_box.clear()
        resolution_list = [str(w) + "x" + str(h) for w, h in COMMON_RESOLUTIONS]
        screen = self.screen()
        geo = screen.geometry()
        if screen:
            sw, sh = geo.width(), geo.height()
            for frac in [1.0, 0.8, 0.75, 0.6]:
                w = int(sw * frac)
                h = int(sh * frac)
                res = f"{w}x{h}"
                if res not in resolution_list:
                    self.log.debug("Adding resolution %s to list", res)
                    resolution_list.append(res)
            new_res_list = []
            for x, y in COMMON_RESOLUTIONS:
                if x > sw or y > sh:
                    continue
                new_res_list.append(f"{x}x{y}")
            resolution_list = new_res_list

        def sort(resolution: str):
            xy = resolution.split("x")
            if len(xy) < 2:
                return 0
            return int(xy[0])

        resolution_list.sort(key=sort)
        resolution_list.insert(0, "Auto")
        self.res_combo_box.addItems(resolution_list)
        self.res_combo_box.validator().set_resolutions(  # type: ignore
            resolution_list
        )
        return

    def _abandon_changes_dialog(self):
        confirm = QMessageBox.question(
            self,
            "Abandon Changes?",
            "Are you sure you want to abandon your profile changes?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard,
        )
        if confirm == QMessageBox.StandardButton.Save:
            self._set_undirty()
            self._save()

    def _hook(self, prof: GameProfile):
        self.version_combo.setDisabled(prof.is_default_profile)
        self.icon_picker.profile_selected(prof)
        if self._dirty:
            self._abandon_changes_dialog()
        self._set_mods_folder_row_visibility(prof.real_version_id, prof)

    def _process_mods_folder_checkbox(self, checked: bool | None = None):
        if not isinstance(checked, bool):
            checked = self.use_mods_folder_input.isChecked()
        if checked:
            prof = profile_manager.get_current_profile()
            self.mods_folder_input.setDisabled(False)
            if prof.mods_folder:
                self.mods_folder_input.setText(prof.mods_folder)
            else:
                self.mods_folder_input.clear()
            self.mods_folder_browse.setDisabled(False)
        else:
            self.mods_folder_input.clear()
            self.mods_folder_input.setDisabled(True)
            self.mods_folder_browse.setDisabled(True)

    def _set_mods_folder_row_visibility(
        self,
        ver_id: str | None = None,
        prof: GameProfile | None = None,
        set_checkbox: bool = True,
    ):
        if not prof:
            prof = profile_manager.get_current_profile()
        if not ver_id:
            ver_id = prof.real_version_id
            if not ver_id:
                log.warning("Couldn't get version ID from profile")
                ver_id = ""
        if version_manager.check_fabric_mod_arg_support(ver_id):
            self.use_mods_folder_input.setEnabled(True)
            if prof.mods_folder and set_checkbox:
                self.use_mods_folder_input.setChecked(True)
                self.mods_folder_input.setText(prof.mods_folder)
            elif set_checkbox:
                self.use_mods_folder_input.setChecked(False)
            self._process_mods_folder_checkbox()
            self.form.setRowVisible(self.mods_folder_row, True)
        else:
            self.use_mods_folder_input.setDisabled(True)
            self.mods_folder_input.clear()
            self.form.setRowVisible(self.mods_folder_row, False)

    def _set_dirty(self):
        self._dirty = True
        self.save_button.setEnabled(True)
        self.reset_button.setEnabled(True)

    def _set_undirty(self):
        self._dirty = False
        self.save_button.setDisabled(True)
        self.reset_button.setDisabled(True)

    def _dirty_check(self, *args):  # TODO: rework/remove
        if not self._loaded:
            return False
        profile = profile_manager.get_current_profile()

        # we assume clean/valid until proven otherwise
        is_dirty = False
        self._validity_state = True
        for i in range(10):
            if i == 8:
                continue
            widget = self.mapper.mappedWidgetAt(i)
            if widget is None:
                log.warning("No widget at form idx %d", i)
                continue
            if getattr(widget, "currentText", None):
                val = widget.currentText()  # type: ignore
                if not val:
                    if profile[i] is None:
                        val = None
                    else:
                        val = ""
            elif getattr(widget, "text", None):
                val = widget.text()  # type: ignore
                if not val:
                    if profile[i] is None:
                        val = None
                    else:
                        val = ""
            else:
                continue
            if val != profile[i]:
                is_dirty = True
                # check validity/warn user of nonvalidity
                if getattr(widget, "validator", None):
                    validator = widget.validator()  # type: ignore
                    if isinstance(validator, QValidatorWithStoredResults):
                        widget_is_valid: bool = validator.isValid()
                    else:
                        widget_is_valid = True
                else:
                    widget_is_valid: bool = True
                if self._validity_state is True and not widget_is_valid:
                    self._validity_state = False
                    widget.setProperty("invalid", True)
                    widget.setToolTip("Invalid value")
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                elif widget_is_valid:
                    widget.setProperty("invalid", None)
                    widget.setToolTip("")
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                continue
            else:
                widget.setProperty("invalid", None)
                widget.setToolTip("")
                widget.style().unpolish(widget)
                widget.style().polish(widget)
        # This entire section here for the icon check is stupid and I'm not proud
        # of it, but it damn works at least.
        if self.icon_picker.text() == "<CUSTOM>" and profile.has_custom_icon():
            # <CUSTOM> is always a loaded icon, means there's no change
            pass
        elif not profile.icon and not self.icon_picker.text():
            pass
        elif (
            self.icon_picker.text().startswith("data:image/")
            or self.icon_picker.text() != profile.icon
        ):
            # which also means that base64 in the data indicates a change
            is_dirty = True
        if is_dirty:
            self._set_dirty()
        else:
            self._set_undirty()
        self._handle_validity()
        return is_dirty

    def _handle_validity(self):
        if self._dirty and not self._validity_state:
            self.save_button.setDisabled(True)
            self.save_button.setToolTip("Invalid input present; cannot save")
        else:
            self.save_button.setToolTip("")

    def _save(self):
        self._set_undirty()
        row = self.select.currentIndex().row()
        idx = self.model.index(row, 8)
        # hacky workaround for mapper not supporting itemData :(
        self.model.setData(
            idx, self.icon_picker.text(), Qt.ItemDataRole.UserRole
        )
        self.mapper.submit()
        if constants.FLAG_ENABLE_JUMP_LISTS and config.jump_list_items:
            profile = profile_manager.get_current_profile()
            if (self.icon_picker.text() or None) not in {
                "<CUSTOM>",
                profile.icon,
            }:
                set_jump_list()

    def _reset(self):
        self._set_mods_folder_row_visibility()
        # TODO: see if i can remove this check during build
        self.icon_picker.revert()
        self.mapper.revert()
        prof = profile_manager.get_current_profile()
        self.jvm_args_input.setText(prof.jvm_args)
        if DEV:
            self._dirty_check()
        else:
            self._set_undirty()

    def _parse_resolution(
        self, text: str
    ) -> tuple[None, None] | tuple[int, int]:
        """Parse `nxn` into `(n, n)`"""
        if text.lower() == "auto":
            return None, None
        try:
            w, h = text.split("x")
            w, h = int(w), int(h)
        except Exception as err:
            self.log.error("Failed to split resolution text!", exc_info=err)
            return 720, 480
        else:
            return w, h

    def _resolution_to_text(self, width: int | None, height: int | None):
        if (not width) and (not height):
            return "Auto"
        return f"{width}x{height}"

    def _browse_game_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Game Directory")
        if path:
            self.game_dir_input.setText(path)

    def _browse_java(self):
        # TODO: other OSes
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Java Executable",
            "",
            "Executables (*.exe);;All Files (*)",
        )
        if path:
            self.java_input.setText(path)

    def _browse_mods_folder(self):
        prof = profile_manager.get_current_profile()
        dialog = QFileDialog(self)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setOptions(QFileDialog.Option.ShowDirsOnly)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        if prof.game_dir and os.path.isdir(prof.game_dir):
            dir_ = prof.game_dir
        else:
            dir_ = str(constants.MINECRAFT_DIR)
        dialog.setDirectory(dir_)
        dialog.exec()
        sel_files = dialog.selectedFiles()
        if not sel_files:
            return
        if len(sel_files) > 1:
            log.warning("Mods folder dialog shouldn't have had >1 selected")
        folder = sel_files[0]
        if os.path.isdir(folder):
            self.mods_folder_input.setText(folder)
        else:
            log.warning("User selected non-existant folder? Trying to make it")
            p = Path(folder)
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception as err:
                log.error(
                    "Folder creation failed. "
                    "Returning without doing anything.",
                    exc_info=err,
                )
                return
            else:
                self.mods_folder_input.setText(folder)

    def _load(self):
        self._version_id_validator.load()
        self.populate_version_combo()
        load_launcher_profiles()
        # for name, icon in resources.get_all_default_icons().items():
        #     self.icon_menu.addItem(icon, name, name)

    def version_visibility_changed(self, *args):
        config.show_snapshots = self.show_snapshots_chk.isChecked()
        config.show_old_releases = self.show_old_chk.isChecked()
        self.handle_version_visibility()

    def handle_version_visibility(self):
        for i in range(self.version_combo.count()):
            if i < 2:
                continue
            version: GameVersionStub = self.version_combo.itemData(i)
            match version.type:
                case "release":
                    continue
                case "snapshot":
                    self.version_combo_view.setRowHidden(
                        i, not config.show_snapshots
                    )
                case "old_alpha" | "old_beta":
                    self.version_combo_view.setRowHidden(
                        i, not config.show_old_releases
                    )
        return

    def refresh_version_combo(self):
        click_time = time.time()
        if self._ver_refresh_last_click >= click_time - 1.0:
            log.debug("Refreshing version list (web request)")
            version_manager.fetch_version_manifest(True)
        self._ver_refresh_last_click = click_time
        log.debug("Refreshing version list")
        current_selected_ver = self.version_combo.currentText()
        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        self.version_combo.addItems(
            [constants.LATEST_VERSION_TEXT, constants.LATEST_SNAPSHOT_TEXT]
        )
        game_versions = version_manager.get_version_list(override=True)
        self._version_id_validator.load()
        for ver in game_versions:
            id_ = ver.id
            ver_type = ver.type
            if config.show_snapshots and config.show_old_releases:
                self.version_combo.addItem(id_, ver)
                continue
            r = self.version_combo.count()
            match ver_type:
                case "release":
                    self.version_combo.addItem(id_, ver)
                    continue
                case "snapshot":
                    self.version_combo.addItem(id_, ver)
                    if not config.show_snapshots:
                        self.version_combo_view.setRowHidden(r, True)
                case "old_beta" | "old_alpha":
                    self.version_combo.addItem(id_, ver)
                    if not config.show_old_releases:
                        self.version_combo_view.setRowHidden(r, True)
                case _:
                    self.version_combo.addItem(id_, ver)
        prof = profile_manager.get_current_profile()
        if current_selected_ver in constants.LATEST_VERSIONS_SET:
            self.version_combo.setCurrentText(current_selected_ver)
        elif version_manager.version_exists(current_selected_ver):
            self.version_combo.setCurrentText(current_selected_ver)
        else:
            log.warning(
                "Version '%s' either never existed or doesn't anymore!",
                current_selected_ver,
            )
            if (
                prof.version_id != current_selected_ver
                and version_manager.version_exists(prof.version_id)
            ):
                self.version_combo.setCurrentText(prof.version_id)
            self.version_combo.setCurrentText(constants.LATEST_VERSION_TEXT)
        self.version_combo.blockSignals(False)
        self._dirty_check()

    def populate_version_combo(self):
        # refresh game versions (just in case)
        # TODO: is this necessary?
        game_versions = version_manager.get_version_list()
        self._version_id_validator.load()
        for ver in game_versions:
            id_ = ver.id
            ver_type = ver.type
            if config.show_snapshots and config.show_old_releases:
                self.version_combo.addItem(id_, ver)
                continue
            r = self.version_combo.count()
            match ver_type:
                case "release":
                    self.version_combo.addItem(id_, ver)
                    continue
                case "snapshot":
                    self.version_combo.addItem(id_, ver)
                    if not config.show_snapshots:
                        self.version_combo_view.setRowHidden(r, True)
                case "old_beta" | "old_alpha":
                    self.version_combo.addItem(id_, ver)
                    if not config.show_old_releases:
                        self.version_combo_view.setRowHidden(r, True)
                case _:
                    self.version_combo.addItem(id_, ver)

    def _check_changed_vals(self) -> list[tuple[str, str, str]]:
        profile = profile_manager.get_current_profile()
        # (key, old, new)
        changed_values: list[tuple[str, str, str]] = []

        prof_name = self.name_input.text()
        if profile.name != prof_name:
            changed_values.append(("name", profile.name, prof_name))
        prof_ver_id = self.version_combo.currentText()
        if profile.version_id != prof_ver_id:
            changed_values.append(
                ("version_id", profile.version_id, prof_ver_id)
            )
        prof_game_dir = self.game_dir_input.text() or None
        if profile.game_dir != prof_game_dir:
            changed_values.append(
                (
                    "game_dir",
                    profile.game_dir or "None",
                    prof_game_dir or "None",
                )
            )
        prof_java_path = self.java_input.text() or None
        if profile.java_path != prof_java_path:
            changed_values.append(
                (
                    "java_path",
                    profile.java_path or "None",
                    prof_java_path or "None",
                )
            )
        jvm_args = self.jvm_args_input.text() or None
        if profile.jvm_args != jvm_args:
            changed_values.append(
                ("jvm_args", profile.jvm_args or "None", jvm_args or "None")
            )
        mem_min = self.mem_min_input.text() or "512M"
        if profile.memory_min != mem_min:
            changed_values.append(("memory_min", profile.memory_min, mem_min))
        mem_max = self.mem_max_input.text() or "4G"
        if profile.memory_max != mem_max:
            changed_values.append(("memory_max", profile.memory_max, mem_max))
        width, height = self._parse_resolution(self.res_combo_box.currentText())
        if profile.resolution_width != width:
            changed_values.append(
                (
                    "resolution_width",
                    str(profile.resolution_width) or "None",
                    str(width) or "None",
                )
            )
        if profile.resolution_height != height:
            changed_values.append(
                (
                    "resolution_height",
                    str(profile.resolution_height) or "None",
                    str(height) or "None",
                )
            )

        return changed_values

    def _save_current(self):
        profile = profile_manager.get_current_profile()
        changed_values = self._check_changed_vals()
        log.info("Saving profile '%s' (ID: %s)", profile.name, profile.uuid)
        string = []
        for name, old, new in changed_values:
            string.append(f"{name}: '{old}'->'{new}'")
        if string:
            log.debug("\n".join(string))

        self.mapper.submit()
        save_single_profile(profile)

    def _new_profile(self):
        prof = profile_manager.create_profile()
        profile_manager.set_current_profile(prof)

    def _delete_profile(self, profile: GameProfile | None = None):
        if not profile:
            profile = profile_manager.get_current_profile()
        confirmation = WarningDialog.warn(
            self,
            "Delete Profile?",
            f'Are you sure you want to delete the profile "{profile.name}"?',
            WarningType.DELETE_PROFILE,
            button_config=ButtonConfig.YES_NO,
        )
        if confirmation:
            log.info(
                "Deleting profile '%s' (ID: %s)", profile.name, profile.uuid
            )
            profile_manager.delete_single_profile(profile)
            del profile

    @property
    def current_jvm_args(self):
        return self.jvm_args_input.text()

    def _args_changer(self, version_id: str | int):
        if not self._loaded:
            return
        prof = profile_manager.get_current_profile()
        if isinstance(version_id, int):
            version_id = self.version_combo.itemText(version_id)
        _bg_worker = VersionJsonBackgroundDownloader(version_id, prof)
        _running_threads.append(_bg_worker)

        def set_args_final(args: str):
            nonlocal prof
            if args:
                prof.jvm_args = args
                self.jvm_args_input.setText(args)

        _bg_worker.done.connect(set_args_final)
        _bg_worker.finished.connect(_bg_worker.deleteLater)
        _bg_worker.start()

        self._set_mods_folder_row_visibility(version_id, set_checkbox=False)

    def _export_prof_icon(self, prof: GameProfile | None = None):
        if not prof:
            prof = profile_manager.get_current_profile()
        if not prof.icon:
            return
        str_path, _ = QFileDialog.getSaveFileName(
            self, "Save file", "", "PNG Image (*.png);;All Files (*)"
        )
        if not str_path:
            return
        path = Path(str_path)
        if not path.parent.exists():
            return
        log.debug("Saving profile icon to '%s'", str_path)
        ico = resources.profile_icon(prof.icon)
        img = ico.pixmap(ico.actualSize(QSize(99999, 99999))).toImage()
        img.save(str_path)

    def _clone_profile(self, prof: GameProfile | None = None):
        if not prof:
            prof = profile_manager.get_current_profile()
        new = prof.copy()
        profile_manager.save_single_profile(new)

    def _profile_list_context_menu(self, e: QContextMenuEvent):
        e.ignore()
        if not e:
            return
        mods = e.modifiers()
        show_debug_options = mods & Qt.KeyboardModifier.ShiftModifier

        menu = QMenu(self.profile_list)
        idx = self.profile_list.indexAt(e.pos())
        prof = self.model.data(idx, 256)
        if not prof:
            new_prof = QAction(menu)
            new_prof.setIcon(resources.symbol("journal-plus"))
            new_prof.setText("New profile")
            new_prof.triggered.connect(self._new_profile)
            menu.addAction(new_prof)
            menu.exec(e.globalPos())
            return
        elif not isinstance(prof, GameProfile):
            raise TypeError("Unexpected type when getting profile from index")

        save_icon = QAction(menu)
        save_icon.setIcon(resources.symbol("save"))
        save_icon.setText("Save Icon as...")
        save_icon.triggered.connect(lambda c: self._export_prof_icon(prof))
        if not prof.icon:
            save_icon.setDisabled(True)
        menu.addAction(save_icon)

        if constants.FLAG_ENABLE_JUMP_LISTS:
            add_jump_list = QAction(
                menu,
                checkable=True,
                checked=prof.uuid in config.jump_list_items,
                text="Show in jump-list",
                icon=(
                    resources.symbol("checkbox-checked")
                    if prof.uuid in config.jump_list_items
                    else resources.symbol("square")
                ),
            )
            add_jump_list.toggled.connect(
                lambda c: self._add_jump_list_item(c, prof)
            )
            menu.addAction(add_jump_list)

        clone_prof = QAction(menu)
        clone_prof.setIcon(resources.symbol("copy"))
        clone_prof.setText(f'Create copy of "{prof.name}"')
        clone_prof.triggered.connect(lambda c: self._clone_profile(prof))
        menu.addAction(clone_prof)

        if constants.FLAG_ENABLE_EXPORTING:
            export_prof = QAction(menu)
            export_prof.setIcon(resources.symbol("share"))
            export_prof.setText(f'Export "{prof.name}"')
            if prof.is_default_profile:
                export_prof.setDisabled(True)
            else:
                export_prof.triggered.connect(
                    lambda c: ExportProfileDialog.deploy(prof, self)
                )
            menu.addAction(export_prof)

        if show_debug_options:
            copy_id = QAction(menu)
            copy_id.setIcon(resources.symbol("clipboard"))
            copy_id.setText("Copy ID")
            copy_id.triggered.connect(lambda c: copy_to_clipboard(prof.uuid))
            menu.addAction(copy_id)

        delete_profile = QAction(menu)
        delete_profile.setObjectName("delete")
        delete_profile.setData("delete")
        delete_profile.setIcon(resources.symbol("trash"))
        delete_profile.setText("Delete profile")
        delete_profile.setProperty("danger", True)
        if prof.is_default_profile:
            delete_profile.setDisabled(True)
        else:
            delete_profile.triggered.connect(
                lambda c: self._delete_profile(prof)
            )
        menu.addAction(delete_profile)

        menu.popup(e.globalPos())

    @classmethod
    def _add_jump_list_item(cls, checked: bool, profile: GameProfile):
        if not checked:
            return cls._rm_jump_list_item(profile)
        if profile not in config.jump_list_items:
            config.jump_list_items.append(profile.uuid)
        set_jump_list()

    @staticmethod
    def _rm_jump_list_item(profile: GameProfile):
        try:
            config.jump_list_items.remove(profile.uuid)
        except ValueError:
            log.warning(
                "User shouldn't have been able to trigger this function!"
            )
            return
        set_jump_list()
