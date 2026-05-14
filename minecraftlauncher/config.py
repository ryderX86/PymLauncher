"""
Config module. Badly written, should change to a class and initialize in
minecraftlauncher.__init__ instead of having this mess.
"""

from typing import Any
from enum import IntEnum
import os
import json
import logging

from .constants import (
    LAUNCHER_DATA_DIR,
    LAUNCHER_CONFIG_FILE,
)
from .functions import reswrite, error_box

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
ignored_messages: set[int] = set()
jump_list_items: list[str] = []  # profiles
dialog_answers: dict[str, bool] = {}
show_animation_on_skin_dialog: bool = False
show_logs_on_home: bool = False
allow_audio: bool = True
enforce_json_spec: bool = False
show_snapshots: bool = True
"""
Whether or not snapshots/pre-releases should be shown in the versions list.
"""
show_old_releases: bool = True
"""
Whether or not old releases (pre-alpha, alpha, beta, etc.) should be shown in
the versions list.
"""
# icon_pack: str = ICON_PACK_BOOTSTRAP

__config__ = {
    "window_size",
    "open_browser_for_login",
    "copy_code_for_login",
    "post_launch_option",
    "redownload_option",
    "maximized",
    "tooltip_icons_enabled",
    "ignored_messages",
    "jump_list_items",
    "dialog_answers",
    "show_animation_on_skin_dialog",
    "show_logs_on_home",
    "allow_audio",
    "enforce_json_spec",
    "show_snapshots",
    "show_old_releases",
}


def set_(val_name: str, new_val: Any):
    if val_name not in __config__:
        raise IndexError(f"'{val_name}' not found in config")
    current = globals().get(val_name)
    if val_name.startswith("_") or val_name.endswith("_"):
        raise IndexError("Can't override private var")
    if not isinstance(new_val, type(current)):
        _log.warning(
            "Type of '%s' changed: '%s' -> '%s'",
            val_name,
            type(current).__name__,
            type(new_val).__name__,
        )

    globals()[val_name] = new_val
    return


def load(config: dict | None = None):
    if config is None:
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
    for key, val in config.items():  # type: ignore
        if key not in __config__:
            _log.warning("Ignoring unknown key in config.json: '%s'", key)
            continue
        default = globals()[key]
        if isinstance(default, set) and isinstance(val, list):
            globals()[key] = set(val)
        elif not isinstance(default, type(val)):
            _log.warning("Value in '%s' has conflicting type, ignoring", key)
            continue
        else:
            globals()[key] = val


def save():
    obj_out = {}
    for key in __config__:
        val = globals()[key]
        if val is None:
            continue
        elif isinstance(val, (list, dict, set)) and not val:
            continue  # skip bloat
        elif isinstance(val, set):
            obj_out[key] = [*val]
        else:
            obj_out[key] = val
    json_out = json.dumps(obj_out, indent=4, sort_keys=True)
    if not os.path.isdir(LAUNCHER_DATA_DIR):
        _log.debug("Creating launcher data directory")
        os.makedirs(LAUNCHER_DATA_DIR, exist_ok=True)
    reswrite(LAUNCHER_CONFIG_FILE, json_out)
    _log.info("Saved config.json.")


try:
    load()
except Exception as err:
    error_box(
        "Failed to initialize config! Please report this.", err, fatal=True
    )
