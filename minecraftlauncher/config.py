"""
Config module. Badly written, should change to a class and load in
minecraftlauncher.__init__ instead of having this mess.
"""

from typing import Any
from types import NoneType
from enum import IntEnum
import json
import logging

from .constants import LAUNCHER_DATA_DIR, LAUNCHER_CONFIG_FILE
from .functions import reswrite
from . import DEV

_log = logging.getLogger(__name__)


class PostLaunchBehavior(IntEnum):
    KEEP_OPEN = 0
    HIDE = 1
    CLOSE_WHEN_DONE = 2
    CLOSE = 3


class JarRedownloadBehavior(IntEnum):
    NEVER = 0
    REDOWNLOAD = 1
    REDOWNLOAD_ONCE = 2


class IgnoreMe:
    def __init__(self, value: bool = False):
        self._bool = bool(value)

    def __bool__(self) -> bool:
        return self._bool

    def __eq__(self, a):
        if isinstance(a, type(self)) or isinstance(self, type(a)):
            return True
        elif isinstance(a, bool):
            return not a
        return False

    def __ne__(self, a):
        return True


# default values
window_size = [1100, 700]
open_browser_for_login: bool = False
copy_code_for_login: bool = True
post_launch_option: PostLaunchBehavior = PostLaunchBehavior.HIDE
redownload_option: JarRedownloadBehavior = JarRedownloadBehavior.REDOWNLOAD
maximized: bool = False
tooltip_icons_enabled: bool = True
ignored_messages: list[int] = []
jump_list_items: list[str] = []  # profiles
dialog_answers: dict[int, bool] = {}
show_animation_on_skin_dialog: bool = False
show_logs_on_home: bool = False

# konami code, just does comic sans. possibly resource intense.
want_easter_eggs: IgnoreMe | bool = IgnoreMe(False)


def set_(val_name: str, new_val: Any):
    current = globals().get(val_name)
    if val_name not in globals():
        raise IndexError(f"'{val_name}' not found in conifg")
    if val_name.startswith("_") or val_name.endswith("_"):
        raise IndexError("Can't override private var")
    if isinstance(current, type(new_val)):
        pass
    elif callable(current):
        raise TypeError("Can't override callable")
    else:
        _log.warning(
            "Type of '%s' changed: '%s' -> '%s'",
            val_name,
            type(current).__name__,
            type(new_val).__name__,
        )

    globals()[val_name] = new_val
    return


def load(config: dict | None = None):
    if not config:
        config = {}
        if LAUNCHER_CONFIG_FILE.exists():
            try:
                config = json.loads(LAUNCHER_CONFIG_FILE.read_text())
            except json.JSONDecodeError:
                _log.warning("Failed to open config")
                config = {}
        else:
            save()
            config = {}
    assert not isinstance(config, NoneType)
    for key, val in config.items():
        if key[0] == key[0].upper():
            continue
        elif not isinstance(val, (str, int, list, dict, bool, NoneType)):
            continue
        elif key.startswith("_") or key.endswith("_"):
            continue
        elif key.upper() == key:
            continue
        elif isinstance(globals().get(key), NoneType):
            _log.warning("Ignoring unknown key in config.json: '%s'", key)
            continue
        default = globals()[key]
        if isinstance(default, IgnoreMe) and isinstance(val, bool):
            pass
        elif not isinstance(default, type(val)):
            _log.warning("Value in '%s' has conflicting type, ignoring", key)
            continue
        if DEV and val != default:
            _log.debug("%s def: %s, new: %s", key, default, val)
        globals()[key] = val


def save():
    obj_out = {}
    for key, val in globals().items():
        if not isinstance(val, (str, int, list, dict, bool, NoneType)):
            continue
        elif isinstance(val, (list, dict)) and not val:
            continue  # skip bloat
        elif key.startswith("_") or key.endswith("_"):
            continue
        elif key.upper() == key:
            continue
        elif key[0] == key[0].upper():
            continue
        obj_out[key] = val
    json_out = json.dumps(obj_out, indent=2)
    if not LAUNCHER_DATA_DIR.exists():
        LAUNCHER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    reswrite(LAUNCHER_CONFIG_FILE, json_out)
    _log.debug("Saved config.json.")


load()
