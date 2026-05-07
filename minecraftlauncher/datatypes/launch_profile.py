from dataclasses import dataclass, field, asdict
from typing import Literal, overload, Any
from datetime import datetime
import logging
import uuid
import re
import os

from minecraftlauncher.back import version_manager
from minecraftlauncher.exceptions.datatypes import InvalidVersionIdError
from .game_version import GameVersionStub

log = logging.getLogger(__name__)

type ProfileType = Literal["custom", "latest-release", "latest-snapshot"]

MEMORY_REGEX = re.compile(r"[0-9]+[gGmMkKbB]")
MIN_ARG_REGEX = re.compile(r"(-Xms)([0-9]+[gGmMkKbB])")
MAX_ARG_REGEX = re.compile(r"(-Xmx)([0-9]+[gGmMkKbB])")
MODS_DIR_REGEX = re.compile(
    r"-Dfabric\.(modsFolder|addMods)=((?:\"[^\"]+\"|\S+))"
)

NEW_DEFAULT_ARGS = (
    "-XX:+UseCompactObjectHeaders "
    "-XX:+AlwaysPreTouch "
    "-XX:+UseStringDeduplication "
    "-XX:+UseZGC"
)
DEFAULT_ARGS = (
    "-XX:+UnlockExperimentalVMOptions "
    "-XX:+UseG1GC "
    "-XX:G1NewSizePercent=20 "
    "-XX:G1ReservePercent=20 "
    "-XX:MaxGCPauseMillis=50 "
    "-XX:G1HeapRegionSize=32M"
)

DEFAULT_ARGS_LIST = {
    "-XX:+UseCompactObjectHeaders "
    "-XX:+AlwaysPreTouch "
    "-XX:+UseStringDeduplication "
    "-XX:+UseZGC",
    "-XX:+UnlockExperimentalVMOptions "
    "-XX:+UseG1GC "
    "-XX:G1NewSizePercent=20 "
    "-XX:G1ReservePercent=20 "
    "-XX:MaxGCPauseMillis=50 "
    "-XX:G1HeapRegionSize=32M",
}


@dataclass(slots=True)
class GameProfile:
    """Launcher game profile"""

    name: str = "Untitled"
    version_id: str = "latest-release"
    game_dir: str | None = None
    java_path: str | None = None
    jvm_args: str | None = None
    resolution_width: int | None = None
    resolution_height: int | None = None
    icon: str | None = None
    memory_min: str = "512M"
    memory_max: str = "4G"
    mods_folder: str | None = None
    mods_folder_mode: str | None = None
    is_default_profile: bool = False
    type: ProfileType = field(default="custom")
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: str = field(
        default="1970-01-01T00:00:00.000Z"
    )  # same as vanilla

    def __post_init__(self):
        match self.type:
            case "latest-release" | "latest-snapshot":
                self.is_default_profile = True
        if not self.jvm_args:
            self.jvm_args = self.default_jvm_args()
        min_match = MIN_ARG_REGEX.search(self.jvm_args)
        if min_match:
            self.jvm_args = self.jvm_args.replace(min_match[0], "")
        max_match = MAX_ARG_REGEX.search(self.jvm_args)
        if max_match:
            self.jvm_args = self.jvm_args.replace(max_match[0], "")
        if min_match or max_match:
            self.jvm_args = self.jvm_args.strip()
        modloader_arg = MODS_DIR_REGEX.search(self.jvm_args)
        if modloader_arg:
            self.jvm_args = self.jvm_args.replace(modloader_arg[0], "")
        if modloader_arg or self.mods_folder:
            if not self.mods_folder_mode:
                self.mods_folder_mode = "modsFolder"
        if "  " in self.jvm_args:  # probably not necessary?
            while "  " in self.jvm_args:
                self.jvm_args = self.jvm_args.replace("  ", " ")
        # this is definitely necessary or the file will keep getting bigger
        if self.jvm_args.startswith(" ") or self.jvm_args.endswith(" "):
            self.jvm_args = self.jvm_args.strip()

    def to_dict(self):
        """
        Returns the raw JSON format version of this, not suitable for saving
        to `launcher_profiles.json`.

        For saving to disk, use `to_dict_compat()`.
        """
        return asdict(self)

    # def get_icon(self):
    #     if not self.icon:
    #         return icon_from_name("")
    #     if self.icon.startswith("data:image/png;base64,"):
    #         return icon_from_b64(self.icon[21:])
    #     else:
    #         return icon_from_name(self.icon.lower())

    @property
    def has_custom_args(self):
        default_args = DEFAULT_ARGS_LIST
        if self.version_id not in [
            "latest-release",
            "latest-snapshot",
            *version_manager.manifest_cache.get("versions", []),
        ]:
            v = version_manager.fetch_version_json(self.version_id)
            default_args = {version_manager.default_user_jvm_args_factory(v)}
        if self.jvm_args and self.jvm_args in default_args:
            return False
        elif not self.jvm_args:
            return False
        return True

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
                    if new_val not in [
                        a.id for a in version_manager.get_version_list()
                    ]:
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
                self.jvm_args = new_val
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
            self.resolution_height = None
            self.resolution_height = None
            return
        res = new.split("x")
        if len(res) != 2:
            raise ValueError(
                "Resolution must be in the format of a screen resolution "
                f"(given input: '{str(new)}')"
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
        version_info = version_manager.resolve_inheritence(
            version_stub.get_json()
        )
        if version_info.get("arguments", {}).get("default-user-jvm"):
            return " ".join(
                [
                    "-XX:+UseCompactObjectHeaders",
                    "-XX:+AlwaysPreTouch",
                    "-XX:+UseStringDeduplication",
                    "-XX:+UseZGC",
                ]
            )
        else:
            return " ".join(
                [
                    "-XX:+UnlockExperimentalVMOptions",
                    "-XX:+UseG1GC",
                    "-XX:G1NewSizePercent=20",
                    "-XX:G1ReservePercent=20",
                    "-XX:MaxGCPauseMillis=50",
                    "-XX:G1HeapRegionSize=32M",
                ]
            )

    def _get_final_jvm_args(self):
        if self.jvm_args:
            args = self.jvm_args.split(" ")
        else:
            args = []
        if self.mods_folder:
            if not self.mods_folder_mode:
                self.mods_folder_mode = "modsFolder"
            elif not os.path.isfile(self.mods_folder):
                self.mods_folder_mode = "modsFolder"
            elif os.path.isfile(self.mods_folder.split(";")[0]):
                self.mods_folder_mode = "addMods"
            if " " in self.mods_folder:
                mods_dir = f'"{self.mods_folder.strip('"')}"'
            else:
                mods_dir = self.mods_folder
            args.insert(0, "-Dfabric." f"{self.mods_folder_mode}={mods_dir}")
        args.insert(0, f"-Xms{self.memory_min}")
        args.insert(1, f"-Xmx{self.memory_max}")
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
        new = cls.from_dict_compat(props, uid)
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
                "javaArgs": self._get_final_jvm_args(),
                "javaDir": self.java_path,
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
        version_info = version_manager.resolve_inheritence(
            version_stub.get_json()
        )
        return version_manager.check_client_jar(version_info)

    @property
    def real_version_id(self) -> str | None:
        match self.version_id:
            case "latest-release":
                version_type = "release"
            case "latest-snapshot":
                version_type = "snapshot"
            case _:
                return self.version_id
        return version_manager.manifest_cache["latest"].get(version_type)

    @classmethod
    def from_dict_compat(cls, data: dict, uid: str):
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

        # initialize with defaults then try to update them with
        # existing values if possible
        memory_min = "512M"
        memory_max = "4G"
        modloader_arg = None
        modloader_mode = None
        if data.get("javaArgs"):
            min_search = MIN_ARG_REGEX.search(data["javaArgs"])
            if min_search:
                memory_min = min_search[2]
            max_search = MAX_ARG_REGEX.search(data["javaArgs"])
            if max_search:
                memory_max = max_search[2]

            mods_dir_search = MODS_DIR_REGEX.search(data["javaArgs"])
            if mods_dir_search:
                modloader_mode = mods_dir_search[1]
                modloader_arg = mods_dir_search[2].strip('"')

        t = data.get("type", "custom")
        if t in ("latest-release", "latest-snapshot"):
            if not data.get("name"):
                match t:
                    case "latest-release":
                        data["name"] = "Latest Release"
                    case "latest-snapshot":
                        data["name"] = "Latest Snapshot"

        return GameProfile(
            name=data.get("name", "Untitled"),
            version_id=data.get("lastVersionId", "latest-release"),
            game_dir=data.get("gameDir"),
            java_path=data.get("javaDir"),
            jvm_args=data.get("javaArgs"),
            resolution_height=data.get("resolution", {}).get("height"),
            resolution_width=data.get("resolution", {}).get("width"),
            uuid=uid,
            memory_max=memory_max,
            memory_min=memory_min,
            mods_folder=modloader_arg,
            mods_folder_mode=modloader_mode,
            icon=data.get("icon"),
            created=data.get("created", "1970-01-01T00:00:00.000Z"),
            last_used=data.get("lastUsed", "1970-01-01T00:00:00.000Z"),
            type=data.get("type", "custom"),
        )

    @classmethod
    def from_dict(cls, data: dict, uid: str):
        known: list[str] = [
            f.name
            for f in cls.__dataclass_fields__.values()  # pylint: disable=E1101
        ]
        unknown: list[str] = [f.name for f in data.keys() if f not in known]
        filtered_data = {k: v for k, v in data.items() if k in known}
        if unknown:
            for key in unknown:
                log.warning(
                    "Unexpected entry in launcher profile '%s': '%s'", uid, key
                )
        return cls(**filtered_data)

    def has_valid_uuid(self):
        uid_fmt = self.uuid.replace("-", "")
        chars = "0123456789abdef"

        def valid_chars():
            nonlocal chars, uid_fmt
            for char in uid_fmt:
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
