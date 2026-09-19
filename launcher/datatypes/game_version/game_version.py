from copy import deepcopy
from datetime import datetime
from typing import Iterable
import json
import logging

from launcher import constants
from launcher.back.download_helpers import RunnableDownloader

from .asset_index import AssetIndex
from .asset_index_stub import AssetIndexStub
from .game_version_stub import GameVersionStub, GameVersionType
from .jar_file import JarFile
from .launch_arg import GameLaunchArg, JVMLaunchArg
from .library import Library
from .log4j import Log4JConfig

log = logging.getLogger(__name__)

LEGACY_LAUNCH_ARGS_DEFAULT = (
    "--username ${auth_player_name} --session ${auth_session} "
    "--versionName ${version_name} "
    "--accessToken ${auth_access_token} --gameDir ${game_directory} "
    "--assetsDir ${assets_root} --userProperties {} "
    "--userType msa"
)

LEGACY_LAUNCH_ARGS_JVM = [
    "-Djava.library.path=${natives_directory}",
    f"-Dminecraft.launcher.brand={constants.LAUNCHER_NAME}",
    f"-Dminecraft.launcher.version={constants.LAUNCHER_VERSION}",
    "-Dminecraft.client.jar=${jar_path}",
    "-cp",
    "${classpath}",
]

DEFAULT_USER_JVM = (
    "-XX:+UnlockExperimentalVMOptions "
    "-XX:+UseG1GC "
    "-XX:G1NewSizePercent=20 "
    "-XX:G1ReservePercent=20 "
    "-XX:MaxGCPauseMillis=50 "
    "-XX:G1HeapRegionSize=32M"
)


class GameVersion:
    id: str
    arguments_game: list[str | GameLaunchArg] | list[str]
    arguments_jvm: list[str | JVMLaunchArg] | list[str]
    assets_index: str
    assets_stub: AssetIndexStub
    main_class: str
    release_time: float
    time: float
    logging: Log4JConfig | None
    _libraries: list[Library]
    jar_file: JarFile
    compliance_level: int
    inherits_from: str | None
    type: GameVersionType
    java_version: str
    java_version_id: int
    use_jar_file: str | None
    """
    Some Forge versions specifically marked that the launcher shouldn't
    download a copy of the client JAR and should just use the client JAR, since
    generally modloads don't modify the client JAR and instead use their own
    libraries' class as the main class for Java and instead use an argument to
    point their own library towards the client JAR's main class.
    
    This allows for the use of that functionality here. If specified, the
    `jar_file` property of this class will use the original JAR file's path.

    For example, a value of `1.8.9` will point the launcher to use the JAR file
    at `.../versions/1.8.9/1.8.9.jar`.
    """
    default_user_jvm_args: str
    default_user_jvm_args_set: frozenset

    @staticmethod
    def _rem_mem_args(args: Iterable[dict | str]):
        """
        Overly-complex function to remove any `-Xms#M` and `-Xmx#G` arguments,
        if present.
        """
        args_out = []
        for arg in args:
            match arg:
                case dict():
                    if "value" not in arg:
                        raise ValueError("Value missing from arguments")
                    if isinstance(arg["value"], list):
                        arg["value"] = [
                            v
                            for v in arg["value"]
                            if not (
                                v.startswith("-Xms") or v.startswith("-Xmx")
                            )
                        ]
                        args_out.append(arg)
                    else:
                        value = arg["value"]
                        if not (
                            value.startswith("-Xms")
                            or value.startswith("-Xmx")
                        ):
                            args_out.append(arg)
                case str() if not (
                    arg.startswith("-Xms") or arg.startswith("-Xmx")
                ):
                    args_out.append(arg)
        return args_out

    def __init__(self, version_json: dict):
        version = deepcopy(version_json)
        min_launcher_version = version.pop("minimumLauncherVersion", 0)
        if min_launcher_version > 21:
            raise RuntimeError(
                f"Unexpected minimum launcher version: {min_launcher_version}"
            )
        if "id" not in version:
            raise ValueError("Version ID not supplied in kwargs")
        self.id = version.pop("id")
        self.inherits_from = version.pop("inheritsFrom", None)
        self.use_jar_file = version.pop("jar", None)
        self.type = version.pop("type")

        arguments_all = version.pop("arguments", None)
        if arguments_all:
            if "jvm" not in arguments_all:
                raise ValueError(
                    "JVM args missing from default 'arguments' object"
                )
            if "game" not in arguments_all:
                raise ValueError(
                    "Game args missing from default 'arguments' object"
                )
            if "default-user-jvm" in arguments_all:
                self.default_user_jvm_args = " ".join(
                    x.string() if isinstance(x, JVMLaunchArg) else x
                    for x in [
                        (
                            JVMLaunchArg.parse_dict(a)
                            if isinstance(a, dict)
                            else str(a)
                        )
                        for a in self._rem_mem_args(
                            arguments_all["default-user-jvm"]
                        )
                    ]
                    if (isinstance(x, JVMLaunchArg) and x.allowed())
                    or isinstance(x, str)
                )
                self.default_user_jvm_args_set = frozenset(
                    self.default_user_jvm_args.split()
                )
            else:
                self.default_user_jvm_args = DEFAULT_USER_JVM
            jvm_args_raw = self._rem_mem_args(arguments_all["jvm"])
            game_args_raw: list[dict | str] = arguments_all["game"]
            self.arguments_jvm = [
                JVMLaunchArg.parse_dict(a) if isinstance(a, dict) else str(a)
                for a in jvm_args_raw
            ]
            self.arguments_game = [
                GameLaunchArg.parse(arg) for arg in game_args_raw
            ]
        if not arguments_all:
            self.default_user_jvm_args = DEFAULT_USER_JVM
            game_args = version.pop(
                "minecraftArguments", LEGACY_LAUNCH_ARGS_DEFAULT
            )
            match game_args:
                case str():
                    self.arguments_game = game_args.split()
                case list():
                    self.arguments_game = [
                        GameLaunchArg.parse(arg) for arg in game_args
                    ]
            jvm = deepcopy(LEGACY_LAUNCH_ARGS_JVM)
            self.arguments_jvm = [JVMLaunchArg.parse_dict(a) for a in jvm]

        # asset index info:
        self.assets_index = version.pop("assets")
        if "assetIndex" not in version:
            raise ValueError("assetIndex missing from version object")
        self.assets_stub = AssetIndexStub.parse_dict(version.pop("assetIndex"))

        # log4j logging config

        # forge always has an empty dict, we need to check for the client key
        # before proceeding like all is good, because all may very much not be
        # good actually.
        if "logging" in version and "client" in version["logging"]:
            logging_info = version.pop("logging")
            client = logging_info["client"]
            file = client["file"]
            self.logging = Log4JConfig(
                client["argument"],
                file["id"],
                file["sha1"],
                file["size"],
                file["url"],
                client["type"],
            )
        else:
            self.logging = None

        # client JAR
        try:
            client_jar = version.pop("downloads").pop("client")
        except KeyError as err:
            if "downloads" not in version:
                raise ValueError(
                    "Missing JAR download information from version object"
                ) from err
            else:
                raise ValueError(
                    f"Missing client JAR info from downloads object: {version["downloads"]!r}"
                ) from err

        self.jar_file = JarFile(
            self.id,
            client_jar["url"],
            client_jar["sha1"],
            client_jar["size"],
        )

        # libraries
        self._libraries = list(
            Library.parse(l) for l in version.pop("libraries")
        )

        # one-liners:
        self.main_class = version.pop(
            "mainClass", "net.minecraft.client.main.Main"
        )
        self.release_time = datetime.fromisoformat(
            version.pop("releaseTime", "1970-01-01T00:00:00.000Z")
        ).timestamp()
        self.time = datetime.fromisoformat(
            version.pop("time", "1970-01-01T00:00:00.000Z")
        ).timestamp()
        self.compliance_level = version.pop("complianceLevel", 0)
        self.java_version = version["javaVersion"]["component"]
        self.java_version_id = version["javaVersion"]["majorVersion"]
        version.pop("javaVersion")

        # warn for unknown keys
        for key, value in version.items():
            match key:
                case "_comment_":
                    continue
            log.warning(
                "Ignoring unexpected key/val in version object: {%r: %r}",
                key,
                value,
            )

    def get_game_args(self, features: dict[str, bool]):
        return [
            a if isinstance(a, str) else a.get_result(features)
            for a in self.arguments_game
        ]

    def get_jvm_args_iter(self):
        # pylint: disable=no-member
        # pylint is ragebaiting me
        for arg in self.arguments_jvm:
            match arg:
                case str():
                    yield arg
                case JVMLaunchArg() if arg.allowed():
                    yield arg.string()
        return

    def get_jvm_args(self, return_type: type[list | set] = list):
        return return_type(a for a in self.get_jvm_args_iter())

    def get_asset_index(self):
        if not self.assets_stub.available():
            err = FileNotFoundError("Assets index unavailable")
            err.filename = self.assets_stub.file_path
            raise err
        with open(self.assets_stub.file_path, "r") as file:
            try:
                index_raw = json.loads(file.read())
            except json.JSONDecodeError as err:
                raise RuntimeError(
                    f"JSON parsing error in assets index {self.assets_index!r} "
                    f"for game version {self.id!r}"
                    f"{
                        f" (inheriting from {self.inherits_from})"
                        if self.inherits_from else ""
                    }"
                ) from err
        return AssetIndex.parse_dict(index_raw)

    @property
    def libraries(self):
        return list(l for l in self._libraries if l.allowed())

    def library_downloads(self, callback=None) -> set[RunnableDownloader]:
        output = set()
        for lib in self.libraries:
            if lib.url:
                output.add(lib.downloader())
        return output

    def __eq__(self, other):
        match other:
            case GameVersion() | GameVersionStub():
                return self.id == other.id
            case _:
                return NotImplemented

    def __ne__(self, other):
        match other:
            case GameVersion() | GameVersionStub():
                return self.id != other.id
            case _:
                return NotImplemented

    def __lt__(self, other):
        match other:
            case GameVersion():
                return self.release_time < other.release_time
            case GameVersionStub():
                return self.release_time < other.timestamp
            case _:
                return NotImplemented

    def __gt__(self, other):
        match other:
            case GameVersion():
                return self.release_time > other.release_time
            case GameVersionStub():
                return self.release_time > other.timestamp
            case _:
                return NotImplemented

    def __le__(self, other):
        match other:
            case GameVersion():
                return self.release_time <= other.release_time
            case GameVersionStub():
                return self.release_time <= other.timestamp
            case _:
                return NotImplemented

    def __ge__(self, other):
        match other:
            case GameVersion():
                return self.release_time >= other.release_time
            case GameVersionStub():
                return self.release_time >= other.timestamp
            case _:
                return NotImplemented
