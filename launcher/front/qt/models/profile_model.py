from collections.abc import Sequence
from enum import IntEnum
from types import NoneType
from typing import Any
import logging

from PySide6.QtCore import (
    QAbstractTableModel,
    QMimeData,
    QModelIndex,
    QPersistentModelIndex,
    QSize,
    Qt,
)

from launcher.back import profile_manager, version_manager
from launcher.datatypes.launch_profile import LaunchProfile
from launcher.front import resources

log = logging.getLogger(__name__.replace("_", ""))

MIME_TYPE = "application/minecraft.profile"


class ProfileModel(QAbstractTableModel):
    """
    QAbstractListModel child class

    Data order:
    0. Profile Name
    1. Version ID
    2. Game directory
    3. JRE path
    4. JVM args
    5. Minimum memory
    6. Maximum memory
    7. Resolution (split by `"x"`) when saving
    """

    class MapIndex(IntEnum):
        NAME = 0
        VERSION = 1
        GAME_DIR = 2
        JAVA_PATH = 3
        JAVA_ARGS = 4
        MIN_RAM = 5
        MAX_RAM = 6
        RESOLUTION = 7
        ICON = 8

    def setup(self):
        profile_manager.SIGNAL.profile_added.connect(self._handle_new_prof)
        profile_manager.SIGNAL.profile_deleted.connect(self._handle_del_prof)
        profile_manager.add_profile_refresh_handler(self.refresh)
        self.refresh()

    def mimeTypes(self):
        return super().mimeTypes() + [MIME_TYPE]

    def canDropMimeData(
        self,
        data: QMimeData,
        action: Qt.DropAction,
        row: int,
        column: int,
        parent: QModelIndex | QPersistentModelIndex,
    ):
        if action == Qt.DropAction.MoveAction and data.hasFormat(MIME_TYPE):
            return True
        return False

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def supportedDragActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def flags(self, index: QModelIndex | QPersistentModelIndex):
        default = super().flags(index)
        if index.isValid():
            return (
                Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
                | default
            )
        return Qt.ItemFlag.ItemIsDropEnabled | default

    def mimeData(self, indexes: Sequence[QModelIndex]) -> QMimeData:
        data = QMimeData()
        ids = []
        for idx in indexes:
            if not idx.isValid():
                log.warning("Invalid QModelIndex in Sequence[]")
                continue
            prof = self.profile(idx)
            if not prof:
                log.warning("Profile from index in Sequence[] not found?!")
                continue
            ids.append(prof.uuid)
        id_list = ";".join(ids)
        data.setData(MIME_TYPE, id_list.encode("utf-8"))
        return data

    def dropMimeData(
        self,
        data: QMimeData,
        action: Qt.DropAction,
        row: int,
        column: int,
        parent: QModelIndex | QPersistentModelIndex,
    ):
        if not self.canDropMimeData(data, action, row, column, parent):
            return False
        if action == Qt.DropAction.IgnoreAction:
            return True
        if column < 0 and not parent.data():
            return False

        id_list_data = data.data(MIME_TYPE).data()
        match id_list_data:
            case bytes() | bytearray():
                id_list = id_list_data.decode("utf-8")
            case memoryview():
                id_list = id_list_data.tobytes().decode("utf-8")
            case _:
                raise TypeError(
                    f"Unexpected type: '{type(id_list_data).__name__}'"
                )

        ids = id_list.split(";")
        if len(ids) > 1 or len(ids) < 0:
            return False
        prof = profile_manager.get_profile(ids[0])

        # this is a very messy workaround for the contrast in the way Qt
        # handles drag-and-drop events on models, and the way *I* handled them,
        # which is probably flawed to begin with.
        current_idx = profile_manager.get_row_from_profile(prof)

        begin_row = 0
        if parent.data():
            begin_row = parent.row()
        elif row >= 0:
            begin_row = row
            if current_idx < begin_row:
                begin_row -= 1
        elif parent.isValid():
            begin_row = parent.row()
        else:
            begin_row = self.rowCount()
            if current_idx < begin_row:
                begin_row -= 1

        profile_manager.reorder_single_profile(prof, begin_row)
        return True

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ):
        return len(profile_manager.profiles.values())

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ):
        return 10

    def profile(self, idx: QModelIndex | QPersistentModelIndex):
        if not idx.isValid():
            return
        prof: LaunchProfile = self.data(idx, Qt.ItemDataRole.UserRole)
        assert isinstance(prof, LaunchProfile)
        return prof

    def data(self, index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        profile = profile_manager.get_profile(index.row())

        match index.column(), role:
            case (
                1,
                Qt.ItemDataRole.DisplayRole | Qt.ItemDataRole.EditRole,
            ) if profile.version_id in {
                "latest-release",
                "latest-snapshot",
            } or version_manager.version_exists(
                profile.version_id
            ):
                return profile.version_id
            case 1, Qt.ItemDataRole.DisplayRole | Qt.ItemDataRole.EditRole:
                log.warning("Version %r doesn't exist", profile.version_id)
                return version_manager.fetch_version("latest-release")
            case 4, Qt.ItemDataRole.DisplayRole:  # args, display
                return profile.jvm_args
            case 4, Qt.ItemDataRole.EditRole:  # args, editing
                if profile.has_custom_args:
                    return profile.jvm_args
                return None
            case (
                7,  # resolution
                Qt.ItemDataRole.DisplayRole | Qt.ItemDataRole.EditRole,
            ):
                if (
                    not profile.resolution_height
                    or not profile.resolution_width
                ):
                    return "Auto"
                return (
                    f"{profile.resolution_width}x"
                    f"{profile.resolution_height}"
                )
            case (
                8,
                Qt.ItemDataRole.DisplayRole | Qt.ItemDataRole.EditRole,
            ) if profile.has_custom_icon():
                return "<CUSTOM>"
            case _, Qt.ItemDataRole.DisplayRole | Qt.ItemDataRole.EditRole:
                return profile[index.column()]
            case _, Qt.ItemDataRole.DecorationRole if profile.icon:
                return resources.profile_icon(profile.icon)
            case _, Qt.ItemDataRole.DecorationRole:
                return None
            case _, Qt.ItemDataRole.UserRole:
                return profile
            case _, Qt.ItemDataRole.SizeHintRole:
                return QSize(0, 56)
            case _, _:
                return None

    def _split_resolution(self, res: str) -> tuple[int, int]:
        res_split = res.split("x")
        if len(res_split) != 2:
            raise ValueError(res)
        return int(res_split[0].strip()), int(res_split[1].strip())

    def setData(self, index, value, role: int = Qt.ItemDataRole.EditRole):
        if role == Qt.ItemDataRole.EditRole:
            profile = profile_manager.get_profile(index.row())
            match index.column():
                case 4:  # skip setting values for icon from the mapper
                    pass
                case 8:
                    assert isinstance(value, (str, NoneType))
                    if (
                        value
                        and set(value.split()) != profile.jvm_args.split()
                    ):
                        profile[index.column()] = value
                    elif not value:
                        profile[index.column()] = None
                case _:
                    profile[index.column()] = value
            self.dataChanged.emit(index, index, [role])
            if index.column() > 8:
                profile_manager.save_single_profile(profile)
            return True
        if role == Qt.ItemDataRole.UserRole:
            profile = profile_manager.get_profile(index.row())
            if value not in ("<CUSTOM>", "<UNKNOWN>"):
                profile[index.column()] = value
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def _handle_new_prof(self, profile: LaunchProfile):
        row = profile_manager.get_row_from_profile(profile)
        self.beginInsertRows(QModelIndex(), row, row)
        self.endInsertRows()

    def _handle_del_prof(self, id_: str, row: int):
        self.beginRemoveRows(QModelIndex(), row, row)
        self.endRemoveRows()

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()
