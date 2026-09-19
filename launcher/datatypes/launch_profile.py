from datetime import datetime
from typing import (
    Any,
    Final,
    Literal,
    NamedTuple,
    get_args,
    overload,
)
import logging
import os
import re
import uuid

from launcher import constants
from launcher.back import version_manager
from launcher.exceptions.datatypes import InvalidVersionIdError

from .game_version import GameVersionStub

log = logging.getLogger(__name__)

type ProfileType = Literal["custom", "latest-release", "latest-snapshot"]

MEMORY_REGEX = re.compile(r"[0-9]+[gGmMkKbB]")
MIN_ARG_REGEX = re.compile(r"(-Xms)([0-9]+[gGmMkKbB])")
MAX_ARG_REGEX = re.compile(r"(-Xmx)([0-9]+[gGmMkKbB])")
MODS_DIR_REGEX = re.compile(
    r"-Dfabric\.(modsFolder|addMods)=((?:\"[^\"]+\"|\S+))"
)


class SplitJVMArgs(NamedTuple):
    args: str | None
    memory_min: str | None
    memory_max: str | None
    mods_folder: str | None
    mods_folder_mode: str | None


class LaunchProfile:
    """
    Game launch profile. Same as profiles in the official launcher.

    When updating arguments, check both
    :meth:`~LaunchProfile.to_dict_compat` AND
    :meth:`~LaunchProfile.to_dict_meta`.
    """

    __slots__ = (
        "name",
        "version_id",
        "game_dir",
        "java_path",
        "_jvm_args",
        "resolution_width",
        "resolution_height",
        "icon",
        "memory_min",
        "memory_max",
        "mods_folder",
        "mods_folder_mode",
        "type",
        "uuid",
        "created",
        "last_used",
        "is_default_profile",
        "_extra_args",
    )

    name: str
    version_id: str
    game_dir: str | None
    java_path: str | None
    _jvm_args: str | None
    resolution_width: int | None
    resolution_height: int | None
    icon: str | None
    memory_min: str
    memory_max: str
    mods_folder: str | None
    mods_folder_mode: str | None
    is_default_profile: Final[bool]
    type: ProfileType
    uuid: str
    created: str
    last_used: str
    _extra_args: dict[str, Any] | None

    @staticmethod
    def split_jvm_args(args: str | None) -> SplitJVMArgs:
        if not args:
            return SplitJVMArgs(None, None, None, None, None)
        min_match = MIN_ARG_REGEX.search(args)
        if min_match:
            args = args.replace(min_match[0], "")
            memory_min = min_match[2]
        else:
            memory_min = None
        max_match = MAX_ARG_REGEX.search(args)
        if max_match:
            args = args.replace(max_match[0], "")
            memory_max = max_match[2]
        else:
            memory_max = None
        modloader_arg = MODS_DIR_REGEX.search(args)
        if modloader_arg:
            args = args.replace(modloader_arg[0], "")
            mod_folder_mode = modloader_arg[1]
            mods_folder = modloader_arg[2].strip('"')
        else:
            mods_folder = None
            mod_folder_mode = None
        args = args.strip()
        while "  " in args:
            args = args.replace("  ", " ")
        return SplitJVMArgs(
            args, memory_min, memory_max, mods_folder, mod_folder_mode
        )

    @overload
    def __init__(
        self,
        /,
        *,
        name: str = "Untitled",
        version_id: str = "latest-release",
        game_dir: str | None = None,
        java_path: str | None = None,
        resolution: dict | None = None,
        icon: str | None = None,
        jvm_args: str | None = None,
        memory_min: str | None = "512M",
        memory_max: str | None = "4G",
        # pylint: disable-next=redefined-outer-name
        uuid: str = ...,
        created: str = ...,
        last_used: str = "1970-01-01T00:00:00.000Z",
        mods_folder: str | None = None,
        mods_folder_mode: str | None = None,
        # pylint: disable-next=redefined-builtin
        type: ProfileType = "custom",
    ): ...

    @overload
    def __init__(
        self,
        /,
        *,
        name: str = "Untitled",
        version_id: str = "latest-release",
        game_dir: str | None = None,
        java_path: str | None = None,
        resolution_width: int | None = None,
        resolution_height: int | None = None,
        icon: str | None = None,
        jvm_args: str | None = None,
        memory_min: str | None = "512M",
        memory_max: str | None = "4G",
        # pylint: disable-next=redefined-outer-name
        uuid: str = ...,
        created: str = ...,
        last_used: str = "1970-01-01T00:00:00.000Z",
        mods_folder: str | None = None,
        mods_folder_mode: str | None = None,
        # pylint: disable-next=redefined-builtin
        type: ProfileType = "custom",
    ): ...

    def __init__(
        self,
        **kwargs,
    ):
        self.name = kwargs.pop("name", "Untitled")
        self.version_id = kwargs.pop("version_id", "latest-release")
        self.game_dir = kwargs.pop("game_dir", None)
        self.java_path = kwargs.pop("java_path", None)
        if "resolution" in kwargs:
            resolution = kwargs.pop("resolution")
            self.resolution_width = resolution.get("width")
            self.resolution_height = resolution.get("height")
        else:
            self.resolution_width = kwargs.pop("resolution_width", None)
            self.resolution_height = kwargs.pop("resolution_height", None)
        self.icon = kwargs.pop("icon", None)
        self._jvm_args = kwargs.pop("jvm_args", None)

        self.type: ProfileType = kwargs.pop("type", "custom")
        # pylint: disable-next=no-member
        if self.type not in get_args(ProfileType.__value__):
            raise ValueError(f"Invalid profile type: {self.type}")
        match self.type:
            case "latest-release" | "latest-snapshot":
                self.is_default_profile = True
            case _:
                self.is_default_profile = False
        self.uuid = kwargs.pop("uuid", str(uuid.uuid4()))
        self.created = kwargs.pop("created", datetime.now().isoformat())
        self.last_used = kwargs.pop("last_used", "1970-01-01T00:00:00.000Z")

        parsed_args = self.split_jvm_args(self._jvm_args)
        if parsed_args.args:
            version = version_manager.fetch_version(self.version_id)
            if (
                set(parsed_args.args.split())
                != version.default_user_jvm_args_set
            ):
                self._jvm_args = parsed_args.args
            else:
                self._jvm_args = None
        else:
            self._jvm_args = None
        self.memory_min = parsed_args.memory_min or kwargs.pop(
            "memory_min", constants.DEFAULT_MEMORY_MIN
        )
        self.memory_max = parsed_args.memory_max or kwargs.pop(
            "memory_max", constants.DEFAULT_MEMORY_MAX
        )
        self.mods_folder = parsed_args.mods_folder or kwargs.pop(
            "mods_folder", None
        )
        self.mods_folder_mode = parsed_args.mods_folder_mode or kwargs.pop(
            "mods_folder_mode", None
        )

        if kwargs:
            self._extra_args = {}

        for key, value in kwargs.items():
            assert self._extra_args
            log.warning(
                "Unexpected key/value pair in profile JSON: {%r: %r} "
                "(Will be deleted by Mojang's launcher!)",
                str(key),
                str(value),
            )
            self._extra_args[key] = value

    def needs_save_args(self):
        if self.memory_min.upper() != constants.DEFAULT_MEMORY_MIN:
            return True
        if self.memory_max.upper() != constants.DEFAULT_MEMORY_MAX:
            return True
        if self.mods_folder:
            return True
        return False

    @property
    def has_custom_args(self):
        return bool(self._jvm_args)

    def __eq__(self, other: object):
        """Checks UUIDs, nothing else."""
        if isinstance(other, type(self)):
            return other.uuid == self.uuid
        return False

    def __ne__(self, other: object):
        """Checks UUIDs, nothing else."""
        if isinstance(other, type(self)):
            return other.uuid != self.uuid
        return True

    def __getitem__(self, index: int | str):
        match index:
            case 0 | "name":
                return self.name
            case 1 | "version_id":
                return self.version_id
            case 2 | "game_dir":
                return self.game_dir
            case 3 | "java_path":
                return self.java_path
            case 4 | "jvm_args":
                return self.jvm_args
            case 5 | "memory_min":
                return self.memory_min
            case 6 | "memory_max":
                return self.memory_max
            case 7 | "resolution":
                return self.resolution
            case 8 | "icon":
                return self.icon
            case 9 | "mods_folder":
                return self.mods_folder
            case _:
                if isinstance(index, str):
                    raise IndexError(f"Bad index: '{index}'")
                raise IndexError(f"Out of range: {index}")

    @property
    def jvm_args(self) -> str:
        if not self._jvm_args:
            match self.version_id:
                case "latest-release":
                    version_info = version_manager.fetch_version(
                        version_manager.get_latest_release()
                    )
                case "latest-snapshot":
                    version_info = version_manager.fetch_version(
                        version_manager.get_latest_snapshot()
                    )
                case _:
                    version_info = version_manager.fetch_version(
                        self.version_id
                    )
            return version_info.default_user_jvm_args
        return self._jvm_args

    @jvm_args.setter
    def jvm_args(self, args: str):
        self._jvm_args = args

    @overload
    def __setitem__(
        self, index: Literal[0, 1, "name", "version_id"], new_val: str
    ): ...

    @overload
    def __setitem__(self, index: str | int, new_val: str | None): ...

    def __setitem__(self, index: int | str, new_val: str | None):
        def check_type(item: Any, type_: type):
            if not isinstance(item, type_):
                raise TypeError(
                    f"Item at index '{str(index)}' must be of type "
                    f"'{type_.__name__}', not '{type(item).__name__}'."
                )

        match index:
            case 0 | "name":
                if not new_val:
                    new_val = ""
                check_type(new_val, str)
                self.name = new_val
            case 1 | "version_id":
                check_type(new_val, str)
                if new_val not in ["latest-release", "latest-snapshot"]:
                    if new_val not in {
                        a.id for a in version_manager.get_version_list()
                    }:
                        log.warning("Invalid version ID: %s", new_val)
                        new_val = version_manager.get_latest_release()
                self.version_id = new_val
            case 2 | "game_dir":
                if not new_val:
                    new_val = None
                self.game_dir = new_val
            case 3 | "java_path":
                if not new_val:
                    new_val = None
                self.java_path = new_val
            case 4 | "jvm_args":
                if not new_val:
                    new_val = None
                self._jvm_args = new_val
            case 5 | "memory_min":
                if not new_val:
                    new_val = "512M"
                self.memory_min = new_val
            case 6 | "memory_max":
                if not new_val:
                    new_val = "4G"
                self.memory_max = new_val
            case 7 | "resolution":
                if not new_val:
                    new_val = None
                self.resolution = new_val
            case 8 | "icon":
                if not new_val:
                    new_val = None
                self.icon = new_val
            case 9 | "mods_folder":
                if not new_val:
                    new_val = None
                self.mods_folder = new_val
            case _:
                if isinstance(index, str):
                    raise IndexError(f"Bad index: '{index}'")
                raise IndexError(f"Out of range: {index}")

    @property
    def resolution(self):
        """Resolution width + height as a single string"""
        if (not self.resolution_height) or (not self.resolution_width):
            return "Auto"
        return str(self.resolution_width) + "x" + str(self.resolution_height)

    @resolution.setter
    def resolution(self, new: str | None):
        if new is None or new == "Auto":
            self.resolution_width = None
            self.resolution_height = None
            return
        res = new.split("x")
        if len(res) != 2:
            raise ValueError(
                "Resolution must be in the format of a screen resolution "
                f'(given input: "{str(new)}")'
            )
        self.resolution_width = int(res[0])
        self.resolution_height = int(res[1])

    def has_custom_icon(self):
        if not self.icon:
            return False
        return self.icon.startswith("data:image/") and "base64" in self.icon

    def default_jvm_args(self) -> str:
        id_ = self.real_version_id
        if not id_:
            log.warning(
                "Couldn't get true version ID from '%s' initially.",
                self.version_id,
            )
            match self.version_id:
                case "latest-release":
                    id_ = version_manager.get_latest_release()
                case "latest-snapshot":
                    id_ = version_manager.get_latest_snapshot()
                case _:
                    log.warning(
                        "Couldn't assign '%s' to 'real_version_id'!",
                        self.version_id,
                    )
                    id_ = version_manager.get_latest_release()
        versions = version_manager.get_version_list()
        version_stub: GameVersionStub | None = None
        for stub in versions:
            if stub.id == id_:
                version_stub = stub
                break
        if not version_stub:
            log.warning("Couldn't get version stub, no JVM args by default")
            return ""
        version_info = version_manager.fetch_version(version_stub.id)
        return version_info.default_user_jvm_args

    def _get_final_jvm_args(self):
        args = (self.jvm_args or "").split(" ")
        if self.mods_folder:
            if not self.mods_folder_mode:
                self.mods_folder_mode = "modsFolder"
            elif os.path.isdir(self.mods_folder):
                self.mods_folder_mode = "modsFolder"
            elif os.path.isfile(self.mods_folder.split(";")[0]):
                self.mods_folder_mode = "addMods"
            if " " in self.mods_folder:
                mods_dir = f'"{self.mods_folder.strip('"')}"'
            else:
                mods_dir = self.mods_folder
            args.insert(0, "-Dfabric." f"{self.mods_folder_mode}={mods_dir}")
        args.insert(
            0, f"-Xms{self.memory_min or constants.DEFAULT_MEMORY_MIN}"
        )
        args.insert(
            1, f"-Xmx{self.memory_max or constants.DEFAULT_MEMORY_MAX}"
        )
        return " ".join(args)

    @property
    def can_edit(self):
        match self.type:
            case "latest-release" | "latest-snapshot":
                return False
        return True

    def copy(self):
        # TODO: find out if this is necessary?
        cls = type(self)
        props = self.to_dict_compat()
        props["name"] = f"Copy of {self.name}"
        props["type"] = "custom"
        props["created"] = datetime.now().isoformat()
        uid = str(uuid.uuid4())
        new = cls.from_storage(props, uid)
        return new

    def _icon_compat(self):
        if not self.icon:
            return None
        if self.icon.startswith("data:image/"):
            return self.icon
        return "_".join([a.capitalize() for a in self.icon.split("_")])

    def to_dict_compat(self):
        """
        Returns the profile as vanilla compatible JSON with any null or
        otherwise blank fields stripped from it (matches vanilla launcher
        behavior).
        """
        return {
            k: v
            for k, v in {
                "created": self.created,
                "gameDir": self.game_dir,
                "icon": self._icon_compat(),
                "javaDir": self.java_path,
                "javaArgs": (
                    self._get_final_jvm_args()
                    if self.has_custom_args or self.needs_save_args()
                    else None
                ),
                "lastUsed": self.last_used,
                "lastVersionId": self.version_id,
                "name": self.name,
                "type": self.type,
                "resolution": {
                    k: v
                    for k, v in {
                        "width": self.resolution_width,
                        "height": self.resolution_height,
                    }.items()
                    if v
                },
            }.items()
            if v
        }

    def to_dict_meta(self):
        return {"jvm_args": self.jvm_args, "custom_args": self.has_custom_args}

    def check_install(self):
        """Returns `True` if the version is installed"""
        id_ = self.real_version_id
        if not id_:
            log.warning('Profile has no "real" version!')
            return False
        versions = version_manager.get_version_list()
        version_stub: GameVersionStub | None = None
        for stub in versions:
            if stub.id == id_:
                version_stub = stub
                break
        if not version_stub:
            raise InvalidVersionIdError(f"No version stub found for '{id_}'")
        version_info = version_manager.fetch_version(version_stub.id)
        return version_info.jar_file.available()

    @property
    def real_version_id(self) -> str:
        match self.version_id:
            case "latest-release":
                version_type = "release"
            case "latest-snapshot":
                version_type = "snapshot"
            case _:
                return self.version_id
        return version_manager.manifest_cache["latest"].get(version_type)

    @classmethod
    def from_storage(cls, data: dict[str, Any], uid: str):
        known_keys = [
            "created",
            "gameDir",
            "icon",
            "javaArgs",
            "javaDir",
            "lastUsed",
            "lastVersionId",
            "name",
            "type",
            "resolution",
        ]
        unknown_keys = [k for k in data.keys() if k not in known_keys]
        for key in unknown_keys:
            log.warning(
                "Unexpected entry '%s' in 'launcher_profiles.json'", key
            )

        t = data.get("type", "custom")
        if t in ("latest-release", "latest-snapshot"):
            if not data.get("name"):
                match t:
                    case "latest-release":
                        data["name"] = "Latest Release"
                    case "latest-snapshot":
                        data["name"] = "Latest Snapshot"

        return LaunchProfile(
            name=data.get("name", "Untitled"),
            version_id=data.get("lastVersionId", "latest-release"),
            game_dir=data.get("gameDir"),
            java_path=data.get("javaDir"),
            jvm_args=data.get("javaArgs"),
            resolution_width=data.get("resolution", {}).get("width"),
            resolution_height=data.get("resolution", {}).get("height"),
            uuid=uid,
            icon=data.get("icon"),
            created=data.get("created", "1970-01-01T00:00:00.000Z"),
            last_used=data.get("lastUsed", "1970-01-01T00:00:00.000Z"),
            type=data.get("type", "custom"),
        )

    def has_valid_uuid(self):
        uid_fmt = self.uuid.replace("-", "")
        chars = "0123456789abcdef"

        def valid_chars():
            nonlocal chars, uid_fmt
            for char in uid_fmt.lower():
                if char not in chars:
                    return False
            return True

        return len(uid_fmt) == 32 and valid_chars()

    def __hash__(self):
        if self.has_valid_uuid():
            h = uuid.UUID(hex=self.uuid)
        else:
            h = hash(self.uuid)
        return int(h)

    def set_last_used(self):
        self.last_used = datetime.now().isoformat()

    @property
    def type_text(self):
        match self.type:
            case "custom":
                return "Custom"
            case "latest-release":
                return "Latest Release"
            case "latest-snapshot":
                return "Latest Snapshot"
