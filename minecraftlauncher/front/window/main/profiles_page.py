"""
minecraftlauncher.front.window.main.profiles_page

Profile management page.
"""
from datetime import datetime
from pathlib import Path
from fractions import Fraction
from io import BytesIO
import base64
import logging
import json
import os

from PySide6.QtCore import (
    Qt, Signal, QThread, QSize, QBuffer, QByteArray, QModelIndex, QPoint,
    QEvent, QObject
)
from PySide6.QtGui import (
    QGuiApplication, QValidator, QIcon, QPixmap, QAction, QContextMenuEvent,
    QMouseEvent, QSinglePointEvent, QPixelFormat
)
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QVBoxLayout, QWidget, QStyle, QDataWidgetMapper, QListView, QFileDialog,
    QCheckBox, QMenu, QWidgetAction
)

from minecraftlauncher import style, DEV, config
from minecraftlauncher.functions.text import indent
from minecraftlauncher.functions.error_box import error_box
from minecraftlauncher.datatypes.game_version import GameVersionStub
from minecraftlauncher.back.profile_manager import (
    GameProfile, load_launcher_profiles, save_launcher_profiles,
    get_last_used_profile, save_single_profile
)
from minecraftlauncher.back import (
    version_manager, profile_manager, game_launcher
)
from minecraftlauncher.front import styles, resources
from minecraftlauncher.front.qt.models import (
    ProfileSelectionModel, ProfileModel
)
from minecraftlauncher.front.qt.widgets import IconPickerButton
from minecraftlauncher import constants

log = logging.getLogger(__name__)

# TODO: calculate resolutions instead of statically setting them
COMMON_RESOLUTIONS = [
    (854, 480),
    (1280, 720),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
    (3840, 2160)
]

screen = QGuiApplication.primaryScreen()

MapIndex = ProfileModel.MapIndex

class ProfileVersionTextValidator(QValidator):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ver_list = version_manager.get_version_list()

    def _refresh_versions(self):
        self.ver_list = version_manager.get_version_list()
    
    def validate(self, a0:str|None,
                 a1:int) -> tuple[QValidator.State, str, int]:
        ver_ids = [v.id for v in self.ver_list]
        if not a0:
            return self.State.Intermediate, ver_ids[0], 0
        if a0 in ["latest-release", "latest-snapshot"]:
            return self.State.Acceptable, a0, a1
        for id in ver_ids:
            if id == a0:
                return self.State.Acceptable, a0, a1
            if id.startswith(a0):
                return self.State.Intermediate, a0, a1
        return self.State.Invalid, ver_ids[0], 0

def _right_click_decorator(func):
    _func = func
    def decorated_func(e:QEvent|QMouseEvent|None):
        if not e or not isinstance(e, QMouseEvent):
            return _func(e)
        if e.buttons() & Qt.MouseButton.RightButton:
            return
        return _func(e)
    return decorated_func
    
class ProfileResolutionTextValidator(QValidator):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resolutions = []

    def set_resolutions(self, resolution_list:list[str]):
        self.resolutions = resolution_list

    def validate(self, a0:str|None, a1:int):
        if not a0:
            return self.State.Intermediate, self.resolutions[0], 0
        if a0 == "Auto":
            return self.State.Acceptable, a0, a1
        a0 = a0.replace(" ", "")
        sel_res = a0.split("x")
        if ((len(sel_res) < 2 and sel_res[0].isdigit())
            or sel_res[0].isdigit() and not sel_res[1]):
            return self.State.Intermediate, a0, a1
        elif sel_res[0].isdigit() and sel_res[1].isdigit():
            w = int(sel_res[0])
            h = int(sel_res[1])
            if w > 10000 or h > 10000:
                return self.State.Invalid, a0, a1
            elif w < 100 or h < 100:
                return self.State.Intermediate, a0, a1
            return self.State.Acceptable, a0, a1
        return self.State.Invalid, self.resolutions[0], 0
    
class VersionJsonBackgroundDownloader(QThread):
    done = Signal(str)

    log = log.getChild("VersionJsonBackgroundDownloader()")
    
    def __init__(self, version_id:str, profile:GameProfile, parent=None):
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
        version:GameVersionStub|None=None
        for v in version_list:
            if v.id == self._version_id:
                version = v
                break
        if not version:
            self.log.warning("Failed to get version info for '%s'"
                             % self._version_id)
            self.done.emit("INVALID")
            return
        version_json = version_manager.resolve_inheritence(version.get_json())
        args = game_launcher.default_user_jvm_args_factory(version_json)
        self.done.emit(args)

class ProfilesPage(QWidget):
    """Profile page"""
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
        self._build_ui()
        self._bg_worker:VersionJsonBackgroundDownloader|None=None

    @property
    def _selected_uuid(self):
        prof = profile_manager.get_current_profile()
        if prof:
            return prof.uuid
        return None
    
    @_selected_uuid.setter
    def _selected_uuid(self, new_id:str):
        prof = profile_manager.profiles.get(new_id)
        if not prof:
            raise ValueError("UUID not found in profiles cache")
        profile_manager.set_current_profile(prof)
        
    def build(self):
        self._load()
        self._loaded = True

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Profile list
        left = QWidget()
        left.setFixedWidth(250)
        left.setStyleSheet(f"background-color: {styles.BG_DARK};")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 16, 12, 16)
        
        label = QLabel("Profiles")
        label.setProperty("heading", True)
        left_layout.addWidget(label)

        button_row_w = QWidget()
        button_row = QHBoxLayout(button_row_w)
        button_row.setContentsMargins(0, 0, 0, 0)
        new_icon = resources.symbol("journal-plus")
        button_new = QPushButton(new_icon, "New Profile")
        button_new.clicked.connect(self._new_profile)
        button_row.addWidget(button_new, 1)
        button_export = QPushButton()
        button_export.setIcon(resources.symbol("share"))
        button_export.setMaximumWidth(36)
        button_export.setToolTip("Export Current Profile")
        button_row.addWidget(button_export)
        button_import = QPushButton()
        button_import.setIcon(resources.symbol("import"))
        button_import.setMaximumWidth(36)
        button_import.setToolTip("Import Profile")
        button_row.addWidget(button_import)
        # may have to relocate
        left_layout.addWidget(button_row_w)

        self.profile_list = QListView()
        # stinky funky workaround
        self.profile_list.mousePressEvent = _right_click_decorator(
            self.profile_list.mousePressEvent
        )
        _l_ctx_menu = lambda a0: self._profile_list_context_menu(a0)
        self.profile_list.contextMenuEvent = _l_ctx_menu
        """
        for the context menu, I could have used the customContextMenuRequested
        event, however that only gives a single `pos` argument that is local to
        the widget's coordinates, and the `contextMenuEvent` function gives an
        event with `globalPos()` as an argument allowing me to be much, much
        lazier with implementation
        """
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
        self.profile_list.setAutoScroll(False)
        self.profile_list.setDragEnabled(True)
        self.profile_list.setDragDropMode(QListView.DragDropMode.DragDrop)
        # self._change_filter = ProfileSelectionModel(
        #     self.profile_list.model(),
        #     can_change_func=self._row_change_check,
        #     dialog_func=self._abandon_changes_dialog
        # )
        # self.profile_list.setSelectionModel(self._change_filter)
        # self.selection_model.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self.profile_list, 1)

        layout.addWidget(left)

        # separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background-color: {styles.BORDER};")
        layout.addWidget(sep)

        # editor
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 16, 12, 16)

        edit_label = QLabel("Edit Profile")
        edit_label.setProperty("heading", True)
        right_layout.addWidget(edit_label)

        self.form = QFormLayout()
        self.form.setSpacing(12)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        name_icon_area = QHBoxLayout()
        self.name_input = QLineEdit()
        self.mapper.addMapping(self.name_input, MapIndex.NAME)
        self.name_input.textChanged.connect(self._dirty_check)

        # self.icon_menu = QComboBox()
        # self.icon_menu.setMaximumWidth(72)
        # self.icon_menu.setMaxVisibleItems(5)
        # self.icon_menu.currentIndexChanged.connect(self._dirty_check)
        # self.icon_menu.currentIndexChanged.connect(self._icon_change)
        # self.icon_menu.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
        # self.icon_menu.setProperty("icons_only", True)
        # icon_view = self.icon_menu.view()
        # assert icon_view
        # icon_view.setIconSize(QSize(48, 48))
        # icon_view.setAutoScroll(False)
        # self.icon_menu.addItem("", userData="")
        # self.icon_menu.addItem(
        #     resources.symbol("file-image"), "Import", "IMPORT"
        # )
        # icon_view.setVerticalScrollMode(icon_view.ScrollMode.ScrollPerPixel)

        icon_label = QLabel("Icon:")

        self.icon_picker = IconPickerButton()
        self.icon_picker.icon_changed.connect(self._dirty_check)
        # self.icon_menu_2.icon_changed.connect(self._icon_change)

        name_icon_area.addWidget(self.name_input, 1)
        name_icon_area.addWidget(icon_label)
        name_icon_area.addWidget(self.icon_picker)

        self.form.addRow("Name:", name_icon_area)
        
        self.version_combo = QComboBox()
        self.version_combo.addItems(["latest-release", "latest-snapshot"])
        self.version_combo.setEditable(True)
        version_view = self.version_combo.view()
        assert version_view
        version_view.setAutoScroll(False)
        self._version_id_validator = ProfileVersionTextValidator()
        self.version_combo.setValidator(self._version_id_validator)
        self.version_combo.currentIndexChanged.connect(self._dirty_check)
        self.version_combo.currentIndexChanged.connect(self._args_changer)
        self.mapper.addMapping(
            self.version_combo, MapIndex.VERSION, b"currentText"
        )
        refresh_versions_button = QPushButton()
        refresh_versions_button.setIcon(resources.symbol("refresh"))
        refresh_versions_button.clicked.connect(self.refresh_version_combo)
        refresh_versions_button.setFixedWidth(40)
        version_row = QHBoxLayout()
        version_row.addWidget(self.version_combo, 1)
        version_row.addWidget(refresh_versions_button)
        self.form.addRow("Version:", version_row)
        self.populate_version_combo()
        
        game_dir_row = QHBoxLayout()
        self.game_dir_input = QLineEdit()
        self.game_dir_input.setPlaceholderText(".../.minecraft")
        self.game_dir_input.textChanged.connect(self._dirty_check)
        self.mapper.addMapping(self.game_dir_input, MapIndex.GAME_DIR)
        game_dir_row.addWidget(self.game_dir_input, 1)
        self.game_dir_browse_button = QPushButton(
            resources.symbol("folder-symlink"), "Browse"
        )
        self.game_dir_browse_button.setFixedWidth(100)
        self.game_dir_browse_button.clicked.connect(self._browse_game_dir)
        game_dir_row.addWidget(self.game_dir_browse_button)
        self.form.addRow("Game Directory:", game_dir_row)

        java_row = QHBoxLayout()
        self.java_input = QLineEdit()
        self.java_input.setPlaceholderText("Built-in Java")
        self.java_input.textChanged.connect(self._dirty_check)
        self.mapper.addMapping(self.java_input, MapIndex.JAVA_PATH)
        java_row.addWidget(self.java_input, 1)
        self.java_browse_button = QPushButton(
            resources.symbol("folder-symlink"), "Browse"
        )
        self.java_browse_button.setFixedWidth(100)
        self.java_browse_button.clicked.connect(self._browse_java)
        java_row.addWidget(self.java_browse_button)
        self.form.addRow("Java Executable:", java_row)

        self.jvm_args_input = QLineEdit()
        self.jvm_args_input.setPlaceholderText("(Use default arguments)")
        self.jvm_args_input.textChanged.connect(self._dirty_check)
        self.mapper.addMapping(self.jvm_args_input, MapIndex.JAVA_ARGS)
        self.form.addRow("JVM Arguments:", self.jvm_args_input)

        memory_row = QHBoxLayout()

        min_label = QLabel("Minimum:")
        memory_row.addWidget(min_label, 0)
        self.mem_min_input = QLineEdit("512M")
        self.mem_min_input.textChanged.connect(self._dirty_check)
        memory_row.addWidget(self.mem_min_input, 1)
        self.mapper.addMapping(self.mem_min_input, MapIndex.MIN_RAM)

        max_label = QLabel("Maximum:")
        memory_row.addWidget(max_label, 2)
        self.mem_max_input = QLineEdit("4G")
        self.mem_max_input.textChanged.connect(self._dirty_check)
        memory_row.addWidget(self.mem_max_input, 3)
        self.mapper.addMapping(self.mem_max_input, MapIndex.MAX_RAM)

        self.form.addRow("RAM", memory_row)

        self.res_combo_box = QComboBox()
        self.res_combo_box.setEditable(True)
        self.res_combo_box.setValidator(ProfileResolutionTextValidator())
        self.res_combo_box.currentTextChanged.connect(self._dirty_check)
        self.mapper.addMapping(self.res_combo_box, MapIndex.RESOLUTION,
                               b"currentText")
        self._populate_resolution_combo()
        self.form.addRow("Resolution:", self.res_combo_box)

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
        self.mods_folder_input = QLineEdit()
        self.mods_folder_input.setPlaceholderText(".../mods")
        self.mods_folder_input.setDisabled(True)
        self.mods_folder_input.textChanged.connect(self._dirty_check)
        self.mapper.addMapping(self.mods_folder_input, 9)
        self.mods_folder_row.addWidget(self.mods_folder_input)
        self.mods_folder_browse = QPushButton(
            resources.symbol("folder-symlink"), "Browse"
        )
        self.mods_folder_browse.clicked.connect(
            self._browse_mods_folder
        )
        self.mods_folder_browse.setDisabled(True)
        self.mods_folder_row.addWidget(self.mods_folder_browse)
        self.form.addRow("Mods folder:", self.mods_folder_row)
        self.form.setRowVisible(self.mods_folder_row, False)

        right_layout.addLayout(self.form)
        right_layout.addStretch()

        # Save/set current/delete buttons
        buttons_row = QWidget()
        buttons_row_layout = QHBoxLayout(buttons_row)

        self.save_button = QPushButton("Save")
        self.save_button.setProperty("accent", True)
        self.save_button.setDisabled(True)
        # self.save_button.clicked.connect(self._save_current)
        self.save_button.clicked.connect(self._save)
        buttons_row_layout.addWidget(self.save_button)

        self.reset_button = QPushButton("Reset")
        # use_button.clicked.connect(self._set_current)
        self.reset_button.setDisabled(True)
        self.reset_button.clicked.connect(self._reset)
        buttons_row_layout.addWidget(self.reset_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setProperty("danger", True)
        self.delete_button.clicked.connect(self._delete_profile)
        buttons_row_layout.addWidget(self.delete_button)

        buttons_row_layout.addStretch()

        right_layout.addWidget(buttons_row)

        self.mapper.setSubmitPolicy(
            QDataWidgetMapper.SubmitPolicy.ManualSubmit
        )

        layout.addWidget(right, 1)
        self.select.begin_change.connect(self._hook)


    def _populate_resolution_combo(self):
        self.res_combo_box.clear()
        resolution_list = [str(w) + "x" + str(h)
                           for w, h in COMMON_RESOLUTIONS]
        resolution_list.insert(0, "Auto")
        if screen:
            size = screen.size()
            sw, sh = size.width(), size.height()
            for frac in [1.0, .75, .5, .25]:
                w = int(sw * frac)
                h = int(sh * frac)
                res = f"{w}x{h}"
                if res not in resolution_list:
                    self.log.debug("Adding resolution %s to list" % res)
                    resolution_list.append(res)
        self.res_combo_box.addItems(resolution_list)
        self.res_combo_box.validator().set_resolutions( # type: ignore
            resolution_list
        )
        return
    
    def _abandon_changes_dialog(self):
        confirm = QMessageBox.question(
            self, "Abandon Changes?",
            "Are you sure you want to abandon your profile changes?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
        )
        if confirm == QMessageBox.StandardButton.Save:
            self._set_undirty()
            self._save()
        
    def _hook(self, prof:GameProfile):
        self.version_combo.setDisabled(prof.is_default_profile)
        self.icon_picker.profile_selected(prof)
        if self._dirty:
            self._abandon_changes_dialog()
        # item = self.icon_menu.itemText(2)
        # if item in ("<CUSTOM>"):
        #     self.icon_menu.removeItem(2)
        # if prof.has_custom_icon():
        #     assert prof.icon
        #     ico = resources.profile_icon(prof.icon)
        #     self.icon_menu.insertItem(2, ico, "<CUSTOM>", "<CUSTOM>")
        # elif prof.icon:
        #     if prof.icon not in resources.get_all_default_icons().keys():
        #         ico = resources.get_unknown_icon()
        #         self.icon_menu.insertItem(2, ico, prof.icon, prof.icon)
        self._set_mods_folder_row_visibility(prof.real_version_id, prof)

    def _process_mods_folder_checkbox(self, checked:bool|None=None):
        if not isinstance(checked, bool):
            checked = self.use_mods_folder_input.isChecked()
        assert isinstance(checked, bool)
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
        
    def _set_mods_folder_row_visibility(self, ver_id:str|None=None,
                                        prof:GameProfile|None=None,
                                        set_checkbox:bool=True):
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
    
    def _dirty_check(self, *args):
        if not self._loaded:
            return False
        profile = profile_manager.get_current_profile()
        is_dirty = False
        for i in range(10):
            if i == 8:
                continue
            widget = self.mapper.mappedWidgetAt(i)
            if widget is None:
                continue
            if getattr(widget, "currentText", None):
                val = widget.currentText() # type: ignore
                if not val:
                    if profile[i] is None:
                        val = None
                    else:
                        val = ""
            elif getattr(widget, "text", None):
                val = widget.text() # type: ignore
                if not val:
                    if profile[i] is None:
                        val = None
                    else:
                        val = ""
            else:
                continue
            if val != profile[i]:
                is_dirty = True
                continue
        """
        This entire section here for the icon check is stupid and I'm not proud
        of it, but it damn works at least.
        """
        if (self.icon_picker.text() == "<CUSTOM>"
            and profile.has_custom_icon()):
            # <CUSTOM> is always a loaded icon, means there's no change
            pass
        elif not profile.icon and not self.icon_picker.text():
            pass
        elif self.icon_picker.text() == "" and not profile.icon:
            pass
        elif (self.icon_picker.text().startswith("data:image/")
            or self.icon_picker.text() != profile.icon):
            # which also means that base64 in the data indicates a change
            is_dirty = True
        if is_dirty:
            self._set_dirty()
            return True
        else:
            self._set_undirty()
            return False

    def _save(self):
        if not self.form.isRowVisible(self.mods_folder_row):
            self.use_mods_folder_input.setChecked(False)
        self._set_undirty()
        row = self.select.currentIndex().row()
        idx = self.model.index(row, 8)
        # hacky workaround for mapper not supporting itemData :(
        self.model.setData(idx, self.icon_picker.text(),
                           Qt.ItemDataRole.UserRole)
        self.mapper.submit()

    def _reset(self):
        self._set_mods_folder_row_visibility()
        # TODO: see if i can remove this check during build
        if DEV:
            self._dirty_check()
        else:
            self._set_undirty()
        self.icon_picker.revert()
        self.mapper.revert()
    
    def _parse_resolution(self, text:str):
        """Parse `nxn` into `(n, n)`"""
        if text.lower() == "auto":
            return None, None
        try:
            w, h = text.split("x")
            w, h = int(w), int(h)
        except Exception as err:
            self.log.error("Failed to split resolution text!", exc_info=err)
            if screen:
                ssz = screen.size()
                return ssz.width(), ssz.height()
            else:
                return 720, 480
        else:
            return w, h
        
    def _resolution_to_text(self, width:int|None, height:int|None):
        if (not width) and (not height):
            return "Auto"
        return f"{width}x{height}"
        
    def _browse_game_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Game Directory"
        )
        if path:
            self.game_dir_input.setText(path)

    def _browse_java(self):
        # TODO: other OSes
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Java Executable", "",
            "Executables (*.exe);;All Files (*)"
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
                    exc_info=err
                )
                return
            else:
                self.mods_folder_input.setText(folder)

    def _load(self):
        profile_manager.profiles = load_launcher_profiles()
        # for name, icon in resources.get_all_default_icons().items():
        #     self.icon_menu.addItem(icon, name, name)

    def refresh_version_combo(self):
        log.debug("Refreshing version list")
        current_selected_ver = self.version_combo.currentText()
        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        self.version_combo.addItems(["latest-release", "latest-snapshot"])
        game_versions = version_manager.get_version_list(override=True)
        self._version_id_validator._refresh_versions()
        for ver in game_versions:
            id = ver.id
            ver_type = ver.type
            if constants.show_snapshots and constants.show_old_releases:
                self.version_combo.addItem(id, ver.local)
                continue
            match ver_type:
                case "release":
                    self.version_combo.addItem(id, ver.local)
                    continue
                case "snapshot":
                    if constants.show_snapshots:
                        self.version_combo.addItem(id, ver.local)
                case "old_beta" | "old_alpha":
                    if constants.show_old_releases:
                        self.version_combo.addItem(id, ver.local)
                case _:
                    self.version_combo.addItem(id, ver.local)
        prof = profile_manager.get_current_profile()
        if current_selected_ver in ["latest-release", "latest-snapshot"]:
            self.version_combo.setCurrentText(current_selected_ver)
        elif version_manager.version_exists(current_selected_ver):
            self.version_combo.setCurrentText(current_selected_ver)
        else:
            log.warning("Version '%s' either never existed or doesn't anymore!"
                        % current_selected_ver)
            if (prof.version_id != current_selected_ver
                and version_manager.version_exists(prof.version_id)):
                self.version_combo.setCurrentText(prof.version_id)
            self.version_combo.setCurrentText("latest-release")
        self.version_combo.blockSignals(False)
        self._dirty_check()
    
    def populate_version_combo(self):
        # refresh game versions (just in case)
        # TODO: is this necessary?
        game_versions = version_manager.get_version_list()
        self._version_id_validator._refresh_versions()
        for ver in game_versions:
            id = ver.id
            ver_type = ver.type
            if constants.show_snapshots and constants.show_old_releases:
                self.version_combo.addItem(id, ver.local)
                continue
            match ver_type:
                case "release":
                    self.version_combo.addItem(id, ver.local)
                    continue
                case "snapshot":
                    if constants.show_snapshots:
                        self.version_combo.addItem(id, ver.local)
                case "old_beta" | "old_alpha":
                    if constants.show_old_releases:
                        self.version_combo.addItem(id, ver.local)
                case _:
                    self.version_combo.addItem(id, ver.local)

    # def _on_select(self, row:int):
    #     item = self.profile_list.item(row)
    #     if row > len(profile_manager.profiles.keys()) or not item:
    #         self.log.warning("Couldn't find selected profile in index!")
    #         return
        
    #     profile:GameProfile|None = profile_manager.profiles.get(
    #         item.data(Qt.ItemDataRole.UserRole)
    #     )
    #     if profile is None:
    #         self.log.warning("Couldn't find selected profile!")
    #         return
    #     if profile_manager.get_current_profile() != profile:
    #         profile_manager.set_current_profile(profile)
        
    #     # Checks for latest-release/latest-snapshot profiles
    #     self.name_input.setEnabled(profile.can_edit)
    #     self.version_combo.setEnabled(profile.can_edit)
    #     self.delete_button.setEnabled(profile.can_edit)
        
    #     self.name_input.setText(profile.name)
    #     self.name_input.setModified(False)
    #     self.version_combo.setCurrentText(profile.version_id)
    #     self.version_combo.isWindowModified
    #     self.game_dir_input.setText(profile.game_dir)
    #     self.java_input.setText(profile.java_path)
    #     if profile.jvm_args and profile.has_custom_args:
    #         self.jvm_args_input.setText(profile.jvm_args)
    #     else:
    #         self._args_changer(profile.version_id)
    #     self.mem_min_input.setText(profile.memory_min)
    #     self.mem_max_input.setText(profile.memory_max)
    #     self.res_combo_box.setCurrentText(
    #         self._resolution_to_text(profile.resolution_width,
    #                                  profile.resolution_height)
    #     )

    def _check_changed_vals(self) -> list[tuple[str, str, str]]:
        if not self._selected_uuid:
            return []
        profile = profile_manager.get_current_profile()
        # (key, old, new)
        changed_values:list[tuple[str, str, str]] = []

        prof_name = self.name_input.text()
        if profile.name != prof_name:
            changed_values.append(
                ("name", profile.name, prof_name)
            )
        prof_ver_id = self.version_combo.currentText()
        if profile.version_id != prof_ver_id:
            changed_values.append(
                ("version_id", profile.version_id, prof_ver_id)
            )
        prof_game_dir = self.game_dir_input.text() or None
        if profile.game_dir != prof_game_dir:
            changed_values.append(
                ("game_dir", profile.game_dir or "None",
                 prof_game_dir or "None")
            )
        prof_java_path = self.java_input.text() or None
        if profile.java_path != prof_java_path:
            changed_values.append(
                ("java_path", profile.java_path or "None",
                 prof_java_path or "None")
            )
        jvm_args = self.jvm_args_input.text() or None
        if profile.jvm_args != jvm_args:
            changed_values.append(
                ("jvm_args", profile.jvm_args or "None",
                 jvm_args or "None")
            )
        mem_min = self.mem_min_input.text() or "512M"
        if profile.memory_min != mem_min:
            changed_values.append(
                ("memory_min", profile.memory_min, mem_min)
            )
        mem_max = self.mem_max_input.text() or "4G"
        if profile.memory_max != mem_max:
            changed_values.append(
                ("memory_max", profile.memory_max, mem_max)
            )
        width, height = self._parse_resolution(
            self.res_combo_box.currentText()
        )
        if profile.resolution_width != width:
            changed_values.append(
                ("resolution_width", str(profile.resolution_width) or "None",
                 str(width) or "None")
            )
        if profile.resolution_height != height:
            changed_values.append(
                ("resolution_height", str(profile.resolution_height) or "None",
                 str(height) or "None")
            )

        return changed_values

    def _save_current(self):
        if not self._selected_uuid:
            return
        profile = profile_manager.profiles[self._selected_uuid]
        changed_values = self._check_changed_vals()
        log.info("Saving profile '%s' (ID: %s)" % (profile.name, profile.uuid))
        string = []
        for name, old, new in changed_values:
            string.append(f"{name}: '{old}'->'{new}'")
        if string:
            log.debug("\n".join(string))

        self.mapper.submit()
        self.model
        save_single_profile(profile)

    def _new_profile(self):
        prof = profile_manager.create_profile()
        profile_manager.set_current_profile(prof)

    def _delete_profile(self, profile:GameProfile|None=None):
        if not profile:
            profile = profile_manager.get_current_profile()
        if not self._selected_uuid:
            return
        confirmation = QMessageBox.question(
            self, "Delete Profile?",
            "Are you sure you want to delete the profile \"%s\"?"
            % profile.name,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirmation == QMessageBox.StandardButton.Yes:
            log.info("Deleting profile '%s' (ID: %s)"
                     % (profile.name, profile.uuid))
            profile_manager.delete_single_profile(profile)
            del profile

    def get_selected_profile(self) -> GameProfile:
        prof = profile_manager.get_current_profile()
        if not prof:
            raise Exception(
                "Tried to get current profile before profiles were loaded."
            )
        return prof

    @property
    def current_jvm_args(self):
        return self.jvm_args_input.text()
    
    def _args_changer(self, version_id:str|int):
        prof = profile_manager.get_current_profile()
        if isinstance(version_id, int):
            version_id = self.version_combo.itemText(version_id)
        else:
            version_id = version_id
        self._bg_worker = VersionJsonBackgroundDownloader(
            version_id, self.get_selected_profile()
        )

        def set_args_final(args:str):
            nonlocal prof
            if args:
                prof.jvm_args = args
                self.jvm_args_input.setText(args)
        
        self._bg_worker.done.connect(set_args_final)
        self._bg_worker.finished.connect(self._bg_worker.deleteLater)
        self._bg_worker.start()

        self._set_mods_folder_row_visibility(version_id, set_checkbox=False)

    # def _icon_change(self, idx:int):
    #     sel_data = self.icon_menu.itemData(idx)
    #     prof_ico_data = profile_manager.get_current_profile().icon
    #     if prof_ico_data and not prof_ico_data.startswith("data:image/"):
    #         previous_icon = prof_ico_data
    #     elif prof_ico_data:
    #         previous_icon = "<CUSTOM>"
    #     else:
    #         previous_icon = ""
    #     if sel_data == "IMPORT":
    #         path, _ = QFileDialog.getOpenFileName(
    #             self, "Select Image File", "",
    #             "Portable Network Graphics Image (*.png);"
    #         )
    #         if path:
    #             p = Path(path)
    #             try:
    #                 pixmap = QPixmap(128, 128)
    #                 loaded = pixmap.load(path)
    #                 img_bytes = QByteArray()
    #                 buffer = QBuffer(img_bytes)
    #                 pixmap.save(buffer, "png")
    #             except Exception as err:
    #                 log.error("Failed to read image at '%s':" % path,
    #                           exc_info=err)
    #                 self.icon_menu.setCurrentText(previous_icon)
    #                 error_box("Couldn't read file at: %s" % path)
    #                 return
    #             if not loaded:
    #                 error_box("Couldn't read \"%s\"" % p.name)
    #                 self.icon_menu.setCurrentText(previous_icon)
    #                 return
    #             ico = QIcon(pixmap)
    #             data = self.icon_menu.itemData(2)
    #             if data in ("<CUSTOM>", "<UNKNOWN>"):
    #                 self.icon_menu.removeItem(2)
    #             img_b64 = base64.b64encode(img_bytes.data()).decode("utf-8")

    #             self.icon_menu.insertItem(
    #                 2, ico, "<CUSTOM>", "data:image/png;base64,%s" % img_b64
    #             )
    #             self.icon_menu.setCurrentIndex(2)
    #         else:
    #             self.icon_menu.setCurrentText(previous_icon)

    def _export_prof_icon(self, prof:GameProfile|None=None):
        if not prof:
            prof = profile_manager.get_current_profile()
        if not prof.icon:
            return
        str_path, _ = QFileDialog.getSaveFileName(
            self, "Save file", "",
            "PNG Image (*.png);;All Files (*)"
        )
        if not str_path:
            return
        path = Path(str_path)
        if not path.parent.exists():
            return
        log.debug("Saving profile icon to '%s'" % str_path)
        ico = resources.profile_icon(prof.icon)
        img = ico.pixmap(ico.actualSize(QSize(99999, 99999))).toImage()
        img.save(str_path)

    def _clone_profile(self, prof:GameProfile|None=None):
        if not prof:
            prof = profile_manager.get_current_profile()
        new = prof.copy()
        profile_manager.save_single_profile(new)

    def _profile_list_context_menu(self, e:QContextMenuEvent):
        e.ignore()
        if not e:
            return
        menu = QMenu(self.profile_list)
        idx = self.profile_list.indexAt(e.pos())
        prof = self.model.data(idx, 256)
        if not prof:
            new_prof = QAction(menu)
            new_prof.setIcon(resources.symbol("journal-plus"))
            new_prof.setText("New profile")
            new_prof.triggered.connect(
                self._new_profile
            )
            menu.addAction(new_prof)
            menu.exec(e.globalPos())
            return
        elif not isinstance(prof, GameProfile):
            raise TypeError("Unexpected type when getting profile from index")

        save_icon = QAction(menu)
        save_icon.setIcon(resources.symbol("save"))
        save_icon.setText("Save Icon as...")
        save_icon.triggered.connect(
            lambda c: self._export_prof_icon(prof)
        )
        if not prof.icon:
            save_icon.setDisabled(True)
        menu.addAction(save_icon)

        clone_prof = QAction(menu)
        clone_prof.setIcon(resources.symbol("copy"))
        clone_prof.setText("Create copy of \"%s\"" % prof.name)
        clone_prof.triggered.connect(
            lambda c: self._clone_profile(prof)
        )
        menu.addAction(clone_prof)

        delete_profile = QWidgetAction(menu)
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

        menu.exec(e.globalPos())