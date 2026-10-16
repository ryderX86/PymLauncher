"""
Paths for launcher & game data
"""

from socket import gethostname
import inspect
import logging
import os
import sys

from launcher.functions import is_path_valid, pathsafe_str
import launcher._launchargs
import launcher.constants as constants

# pylint: disable-next=protected-access
launchargs = launcher._launchargs.launchargs

log = logging.getLogger(__name__)

if constants.DEV:
    LAUNCHERDIR_FP = os.path.join(os.getcwd(), "portable.txt")
else:
    LAUNCHERDIR_FP = os.path.join(sys.executable, "portable.txt")


class AutoMkdirProperty(property):
    """
    Quick and dirty `property` subclass for tracking/iterating purposes.
    """


def get_user_data_dir():
    home = os.path.expanduser("~")
    match constants.PLATFORM:
        case "win32" | "cygwin":
            if "APPDATA" in os.environ:
                return os.environ["APPDATA"]
            else:
                return os.path.join(home, "AppData", "Roaming")
        case "linux":
            return home
        case "darwin":
            return os.path.join(home, "Library", "Application Support")
        case _:
            if "XDG_DATA_HOME" in os.environ:
                return os.environ["XDG_DATA_HOME"]
            else:
                return os.path.join(home, ".local", "share")


def get_portable_path():
    """
    Detect existence of "portable.txt" file in the same directory as the
    executable, and either set the path to that file's parent directory, or the
    contents of the file.

    Raises `ValueError` if the file path is invalid.
    """
    if not os.path.isfile(LAUNCHERDIR_FP):
        return None
    with open(LAUNCHERDIR_FP, "r") as file:
        text = file.read()
    if not text:
        return os.getcwd()
    elif text:
        text = os.path.expanduser(text)
        text = os.path.expandvars(text)
        text = os.path.normpath(text)
        if not is_path_valid(text):
            raise ValueError(f"Invalid working directory: {text!r}")
        return text
    return text


def _check_create_dir(directory: str, recursive: bool = True):
    if not os.path.isdir(directory):
        try:
            if recursive:
                log.debug("Creating directory: %r (recursive)", directory)
                os.makedirs(directory, exist_ok=True)
            else:
                log.debug("Creating directory: %r", directory)
                os.mkdir(directory)
        except FileExistsError as err:
            log.error(
                "FileExistsError on %r, swallowing it.",
                directory,
                exc_info=err,
            )
            return
        except PermissionError as err:
            log.error(
                "Not enough permissions to create directory at %r",
                directory,
                exc_info=err,
            )
            raise err
        except NotADirectoryError as err:
            log.error(
                "Path at %r is an invalid directory", directory, exc_info=err
            )
            raise
        except OSError as err:
            log.error(
                "Unexpected OSError whilst creating directory at %r:",
                directory,
                exc_info=err,
            )
            raise


class PathFinder:
    ready: bool = False

    _game: str
    _data: str
    _uses_portable: bool
    _hostname: str | None
    _accsuffix: str = "bin"

    def setup(self, game_dir: str | None = None, data_dir: str | None = None):
        default = get_user_data_dir()
        portable = get_portable_path()
        if portable:
            self._uses_portable = True
            self._hostname = pathsafe_str(gethostname())
        else:
            self._uses_portable = False
            self._hostname = None

        # order: func override -> CLI args -> env vars -> portable.txt file
        if game_dir:
            self._game = game_dir
        elif launchargs.game_dir:
            self._game = launchargs.game_dir
        elif "MINECRAFTDIR" in os.environ:
            self._game = os.environ["MINECRAFTDIR"]
        elif portable:
            self._game = os.path.join(portable, ".minecraft")
        else:
            self._game = os.path.join(default, ".minecraft")
        try:
            self._game = os.path.realpath(self._game)
        except Exception as err:
            raise ValueError(
                f"Invalid game directory: {self._game!r}"
            ) from err
        if not is_path_valid(self._game):
            raise ValueError(f"Invalid game directory: {self._game!r}")

        if data_dir:
            self._data = data_dir
        elif launchargs.work_dir:
            self._data = launchargs.work_dir
        elif "LAUNCHERDIR" in os.environ:
            self._data = os.environ["LAUNCHERDIR"]
        elif portable:
            self._data = os.path.join(portable, constants.LAUNCHER_NAME)
        else:
            self._data = os.path.join(default, constants.LAUNCHER_NAME)
        try:
            self._data = os.path.realpath(self._data)
        except Exception as err:
            raise ValueError(
                f"Invalid data directory: {self._data!r}"
            ) from err
        if not is_path_valid(self._data):
            raise ValueError(f"Invalid data directory: {self._data!r}")
        self.ready = True

    @property
    def game(self) -> str:
        return self._game

    @property
    def data(self) -> str:
        return self._data

    @AutoMkdirProperty
    def icon_themes(self) -> str:
        return os.path.join(self.data, "theme", "icon")

    @AutoMkdirProperty
    def themes(self) -> str:
        return os.path.join(self.data, "theme", "style")

    @AutoMkdirProperty
    def textures_cache(self) -> str:
        return os.path.join(self._data, "textures_cache")

    @AutoMkdirProperty
    def launcher_logs(self) -> str:
        return os.path.join(self._data, "logs")

    @property
    def config_file(self) -> str:
        return os.path.join(self._data, "config.json")

    @AutoMkdirProperty
    def jre_path(self) -> str:
        return os.path.join(self._game, "jre")

    @AutoMkdirProperty
    def libraries(self) -> str:
        return os.path.join(self._game, "libraries")

    @AutoMkdirProperty
    def versions(self) -> str:
        return os.path.join(self._game, "versions")

    @property
    def jvm_manifest(self) -> str:
        return os.path.join(self._game, "versions", "jre_manifest.json")

    @AutoMkdirProperty
    def assets(self) -> str:
        return os.path.join(self._game, "assets")

    @AutoMkdirProperty
    def assets_indexes(self) -> str:
        return os.path.join(self._game, "assets", "indexes")

    @AutoMkdirProperty
    def assets_virtual(self) -> str:
        return os.path.join(self._game, "assets", "virtual", "legacy")

    @AutoMkdirProperty
    def assets_objects(self) -> str:
        return os.path.join(self._game, "assets", "objects")

    @AutoMkdirProperty
    def assets_log_configs(self) -> str:
        return os.path.join(self._game, "assets", "log_configs")

    @property
    def profiles_file(self) -> str:
        return os.path.join(self._game, "launcher_profiles.json")

    @property
    def profiles_meta_file(self) -> str:
        return os.path.join(self._game, "launcher_profiles_pyml_meta.json")

    @property
    def accounts_file(self) -> str:
        if self._uses_portable:
            return os.path.join(
                self._data, f"accounts-{self._hostname}.{self._accsuffix}"
            )
        return os.path.join(self._data, f"accounts.{self._accsuffix}")

    @property
    def sha1_cache(self):
        return os.path.join(self._data, "sha1-cache.bin")

    @staticmethod
    def get_user_dir():
        """Gets the current OS user's directory"""
        return os.path.expanduser("~")

    @classmethod
    def get_pics_dir(cls):
        """Gets the current OS user's pictures/images directory"""
        base = cls.get_user_dir()
        match sys.platform:
            case "win32" | "darwin" | "linux":
                if os.path.exists((pics := os.path.join(base, "Pictures"))):
                    return pics
                return base
            case _:
                return base

    @staticmethod
    def to_qt_path(path: str):
        return path.replace("\\", "/")

    def generate_folder_structure(self):
        _check_create_dir(self.data)
        _check_create_dir(self.game)
        for name, value in inspect.getmembers(type(self)):
            if not isinstance(value, AutoMkdirProperty):
                continue
            _check_create_dir(getattr(self, name))


paths = PathFinder()
