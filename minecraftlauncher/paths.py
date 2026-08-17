"""
Paths for launcher & game data
"""

from socket import gethostname
import os
import sys
import logging

from . import constants
from .launchargs import launchargs
from .functions import is_path_valid, pathsafe_str

log = logging.getLogger(__name__)

if constants.DEV:
    LAUNCHERDIR_FP = os.path.join(os.getcwd(), "portable.txt")
else:
    LAUNCHERDIR_FP = os.path.join(sys.executable, "portable.txt")


def get_user_data_dir():
    home = os.path.expanduser("~")
    match constants.PLATFORM:
        case "Windows":
            if "APPDATA" in os.environ:
                return os.environ["APPDATA"]
            else:
                return os.path.join(home, "AppData", "Roaming")
        case "Linux":
            return home
        case "Darwin":
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
        if recursive:
            log.debug("Creating directory: %r (recursive)", directory)
            os.makedirs(directory, exist_ok=True)
        else:
            log.debug("Creating directory: %r", directory)
            os.mkdir(directory)


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
        if not is_path_valid(self._data):
            raise ValueError(f"Invalid data directory: {self._data!r}")
        self.ready = True

        if launchargs.unencrypted_accounts:
            self._accsuffix = "json"

    @property
    def game(self):
        return self._game

    @property
    def data(self):
        return self._data

    @property
    def textures_cache(self):
        return os.path.join(self._data, "textures_cache")

    @property
    def launcher_logs(self):
        return os.path.join(self._data, "logs")

    @property
    def config_file(self):
        return os.path.join(self._data, "config.json")

    @property
    def jre_path(self):
        return os.path.join(self._game, "jre")

    @property
    def libraries(self):
        return os.path.join(self._game, "libraries")

    @property
    def versions(self):
        return os.path.join(self._game, "versions")

    @property
    def jvm_manifest(self):
        return os.path.join(self._game, "versions", "jvm_manifest.json")

    @property
    def assets(self):
        return os.path.join(self._game, "assets")

    @property
    def assets_indexes(self):
        return os.path.join(self._game, "assets", "indexes")

    @property
    def assets_virtual(self):
        return os.path.join(self._game, "assets", "virtual", "legacy")

    @property
    def assets_objects(self):
        return os.path.join(self._game, "assets", "objects")

    @property
    def profiles_file(self):
        return os.path.join(self._game, "launcher_profiles.json")

    @property
    def profiles_meta_file(self):
        return os.path.join(self._game, "launcher_profiles_meta.json")

    @property
    def accounts_file(self):
        if self._uses_portable:
            return os.path.join(
                self._data, f"accounts-{self._hostname}.{self._accsuffix}"
            )
        return os.path.join(self._data, f"accounts.{self._accsuffix}")

    def generate_folder_structure(self):
        _check_create_dir(self.game)
        _check_create_dir(self.jre_path)
        _check_create_dir(self.data)
        _check_create_dir(self.textures_cache)
        _check_create_dir(os.path.join(self.textures_cache, "skins"))
        _check_create_dir(os.path.join(self.textures_cache, "capes"))
        _check_create_dir(self.launcher_logs)
        _check_create_dir(self.assets)
        _check_create_dir(self.assets_indexes)
        _check_create_dir(self.assets_objects)
        _check_create_dir(self.assets_virtual)


paths = PathFinder()
