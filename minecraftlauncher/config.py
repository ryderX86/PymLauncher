from pathlib import Path
from typing import Any, Callable
from types import NoneType
from enum import StrEnum, Enum, IntEnum
import json
import logging
import os
import string

from PySide6.QtCore import QRect, QSize

from .constants import LAUNCHER_DATA_DIR, LAUNCHER_CONFIG_FILE
from . import DEV

_log = logging.getLogger(__name__)

class PostLaunchBehavior(IntEnum):
    KEEP_OPEN = 0
    HIDE = 1
    CLOSE_WHEN_DONE = 2
    CLOSE = 3

"""Config Values"""
window_size = [1100, 700]
open_browser_for_login:bool = False
post_launch_option:PostLaunchBehavior = PostLaunchBehavior.HIDE
maximized:bool = False
tooltip_icons_enabled:bool = True
ignored_messages:list[str] = []

def set(val_name:str, new_val:Any):
    current = globals().get(val_name)
    if val_name not in globals():
        raise IndexError("'%s' not found in conifg" % val_name)
    if val_name.startswith("_") or val_name.endswith("_"):
        raise IndexError("Can't override private var")
    if isinstance(current, type(new_val)):
        pass
    elif callable(current):
        raise TypeError("Can't override callable")
    else:
        _log.warning(
            "Type of '%s' changed: '%s' -> '%s'"
            % (val_name, type(current).__name__, type(new_val).__name__)
        )
    
    globals()[val_name] = new_val
    return

def load(config:dict|None=None):
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
        if not isinstance(val, (str, int, list, dict, bool, NoneType)):
            continue
        if key.startswith("_") or key.endswith("_"):
            continue
        if key.upper() == key:
            continue
        if isinstance(globals().get(key), NoneType):
            _log.warning("Unknown key in config.json: '%s'" % key)
            continue
        default = globals()[key]
        if not isinstance(default, type(val)):
            _log.warning(f"Value in '{key}' has conflicting type")
            continue
        if DEV and val != default:
            _log.debug(f"{key} def: {default}, new: {val}")
        globals()[key] = val

def save():
    obj_out = {}
    for key, val in globals().items():
        if not isinstance(val, (str, int, list, dict, bool, NoneType)):
            continue
        elif key.startswith("_") or key.endswith("_"):
            continue
        elif key.upper() == key:
            continue
        elif key[0] == key[0].upper():
            continue
        obj_out[key] = val
    json_out = json.dumps(obj_out)
    if not LAUNCHER_DATA_DIR.exists():
        LAUNCHER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCHER_CONFIG_FILE.write_text(json_out)

load()