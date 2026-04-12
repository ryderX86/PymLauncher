"""
minecraftlauncher.back.profile_manager

Manages game profiles (version selection, game directory, JVM args,
etc.)

Supports reading the official Minecraft launcher's
``launcher_profiles.json`` format for compatibility.
"""
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Literal, Callable, overload, Any, Iterable, Iterator
from types import FunctionType
from functools import lru_cache
import json
import inspect
import logging
import os
import re
import uuid

from PySide6.QtCore import Signal, QObject

from minecraftlauncher.constants import LAUNCHER_DATA_DIR, MINECRAFT_DIR
from minecraftlauncher.back import (
    version_manager, asset_manager, library_manager, java_manager,
    game_launcher
)
from minecraftlauncher.datatypes.game_version import GameVersionStub
from minecraftlauncher.datatypes.GameProfile import GameProfile
# from minecraftlauncher.front.icons.profile import (ICO, icon_from_name,
#                                                    icon_from_b64)

log = logging.getLogger(__name__)

PROFILES_PATH = MINECRAFT_DIR / "launcher_profiles.json"
PROFILES_META = MINECRAFT_DIR / "launcher_profiles_meta.json"
_DEFAULT_SETTINGS_JSON = {
    "crashAssistance": False,
    "enableAdvanced": True,
    "enableAnalytics": False,
    "enableHistorical": True,
    "enableReleases": True,
    "enableSnapshots": True,
    "keepLauncherOpen": False,
    "showGameLog": False,
    "showMenu": False,
    "soundOn": False
}

type ProfileType = Literal["custom", "latest-release", "latest-snapshot"]

profiles:dict[str, GameProfile] = {}

_current_profile:GameProfile|None=None
_profile_switch_handlers:list[Callable[[GameProfile], None]] = []
_profile_refresh_handlers:list[Callable] = []

@lru_cache(maxsize=32)
def get_row_from_profile(profile:GameProfile):
    i=0
    for _, prof in profiles.items():
        if prof == profile:
            return i
        else:
            i += 1
    raise IndexError("Profile '%s' (ID: %s) not in cache"
                     % (profile.name, profile.uuid))

def reorder_profiles(new_order:Iterable[str]):
    """
    Reorder profiles cache in the order of IDs provided
    """
    global profiles
    new_profiles:dict[str, GameProfile] = {}
    for id in new_order:
        if id not in profiles:
            raise ValueError(
                "ID given for profile reordering doesn't exist: '%s'" % id
            )
        
        new_profiles[id] = profiles[id]
    leftover = [*filter(lambda k: k not in new_order, profiles.keys())]
    if leftover:
        for id in leftover:
            log.warning("Profile with ID '%s' was orphaned during reordering, "
                        "adding it back in." % id)
            new_profiles[id] = profiles[id]
    profiles = new_profiles
    _refresh_profiles()
    _save_sorting_order(profiles.keys())
    return

def reorder_single_profile(prof:GameProfile, idx:int):
    ids = [*profiles.keys()]
    if prof.uuid not in ids:
        raise ValueError("Profile ID not present in profiles!")
    ids.pop(ids.index(prof.uuid))
    ids.insert(idx, prof.uuid)
    return reorder_profiles(ids)

def add_profile_switch_handler(func:Callable[[GameProfile], None]):
    """
    Adds a function to the profile switch handler list, then outputs the index.

    TODO: See if `pyqtSignal()` is better for this.
    """
    global _profile_switch_handlers
    _profile_switch_handlers.append(func)
    return _profile_switch_handlers.index(func)

def remove_profile_switch_handler(func_idx:Callable[[GameProfile], None]|int):
    match type(func_idx):
        case int():
            if func_idx > len(_profile_switch_handlers):
                raise IndexError()
            _profile_switch_handlers.pop(func_idx)
            return
        case FunctionType():
            if func_idx not in _profile_switch_handlers:
                return
            _profile_switch_handlers.pop(_profile_switch_handlers.index(func_idx))
        case _:
            raise TypeError("Unexpected type: %s" % type(func_idx).__name__)
    return

def _refresh_profiles():
    # something probably changed in the main cache, so clear LRU for row getter
    get_row_from_profile.cache_clear()
    for func in _profile_refresh_handlers:
        func()

def add_profile_refresh_handler(func:Callable):
    global _profile_refresh_handlers
    _profile_refresh_handlers.append(func)
    return _profile_refresh_handlers.index(func)

def remove_profile_refresh_handler(func_idx:Callable|int):
    if isinstance(func_idx, int):
        if func_idx > len(_profile_refresh_handlers):
            raise IndexError()
        _profile_refresh_handlers.pop(func_idx)
        return
    if func_idx not in _profile_refresh_handlers:
        return
    _profile_refresh_handlers.pop(_profile_refresh_handlers.index(func_idx))
    return

def get_current_profile():
    """
    Retrieves the currently selected profile.
    
    For automation, use `add_profile_switch_handler()`.

    If called before loading profiles, will raise an `Exception`.
    """
    if not _current_profile:
        # raise Exception("get_current_profile() called before loading profiles")
        load_launcher_profiles()
        assert _current_profile
    return _current_profile

def get_profile(idx:str|int) -> GameProfile:
    match idx:
        case str():
            if idx not in profiles:
                raise ValueError(f"{idx} not found in profile cache.")
            return profiles[idx]
        case int():
            if idx > (len(profiles.values()) - 1):
                raise IndexError(f"Index '{idx}' out of range")
            return [*profiles.values()][idx]
        case _:
            raise TypeError("Unexpected type for 'idx': '%s'"
                            % type(idx).__name__)

def set_current_profile_uuid(uid:str):
    current_prof:GameProfile|None=None
    for id, prof in profiles.items():
        if uid == id:
            current_prof = prof
            break
    if not current_prof:
        raise NameError(name=uid)
    return set_current_profile(current_prof)

def set_current_profile(prof:GameProfile):
    global _current_profile
    # print(inspect.stack()[1].function)
    log.info("Switching profile to '%s' (ID: %s)"
             % (prof.name, prof.uuid))
    _current_profile = prof
    for func in _profile_switch_handlers:
        func(prof)
    return

def current_profile_used():
    prof = get_current_profile()
    log.info("Setting profile '%s' (ID: %s) last used to now."
             % (prof.name, prof.uuid))
    prof.last_used = datetime.now().isoformat()
    save_single_profile(prof)
    
class _Signal(QObject):
    profile_added = Signal(GameProfile)
    profile_deleted = Signal(str, int) # uid, row
    """`uid: str, row: int`"""

SIGNAL = _Signal()

_meta_cache = {}

def get_launcher_meta():
    if _meta_cache:
        return _meta_cache
    if PROFILES_META.exists():
        txt = PROFILES_META.read_text()
        try:
            meta = json.loads(txt)
        except Exception as err:
            log.error("", exc_info=err)
            log.error("Failed to read launcher_profiles_meta.json")
            return {}
        else:
            return meta
    return {}
        
def save_launcher_meta():
    if not _meta_cache:
        return
    try:
        meta_json = json.dumps(_meta_cache)
    except:
        raise
    else:
        PROFILES_META.write_text(meta_json)

def get_profile_sorting():
    meta = get_launcher_meta()
    if meta:
        return meta.get("order", [])
    return [*profiles.keys()]

def _save_sorting_order(data:Iterable[str]):
    log.info("Saving launcher_profiles_meta.json")
    match data:
        case list():
            pass
        case _:
            data = [*data]
    _meta_cache["order"] = data
    save_launcher_meta()
    return True
    
def _default_profs_factory():
    """
    Returns the default `latest-release` and `latest-snapshot` profiles in
    JSON format.
    """
    latest_uid = str(uuid.uuid4())
    snapshot_uid = str(uuid.uuid4())
    return {
        latest_uid: GameProfile(
            "Latest Release",
            type="latest-release",
            uuid=latest_uid,
            is_default_profile=True,
            icon="Grass"
        ),
        snapshot_uid: GameProfile(
            "Latest Snapshot",
            version_id="latest-snapshot",
            uuid=snapshot_uid,
            type="latest-snapshot",
            is_default_profile=True,
            icon="Dirt"
        )
    }
    
def _default_lp_file_factory():
    """
    Creates a new `launcher_profiles.json` with default options and profiles.

    This will be in the Mojang launcher format (see
    `load_launcher_profiles()`).
    """
    return {
        "profiles": _default_profs_factory(),
        "settings": {**_DEFAULT_SETTINGS_JSON},
        "version": 6
    }
    
def load_launcher_profiles():
    """
    Read `launcher_profiles.json` and parse it into a dict of `GameProfile`s.

    (Will not immediately create a new profile if broken or not present, allows
    saving malformed/corrupted profiles)

    Uses the Mojang launcher's format (all fields only present if not `null`):
    ```
    {
        "profiles": {
            "<profile-uid>": {
                "created": "<iso timestamp>",
                "gameDir": "<launch directory>",
                "icon": "<vanilla launcher icon>", # TODO: implement
                "lastUsed": "<iso timestamp, unix epoch if never>",
                "lastVersionId": "<version ID or latest-[version|snapshot]>",
                "name": "<display name>",
                "type": "<see ProfileType>",
                "javaArgs": "<JVM args>",
                "resolution": {
                    "height": "<target window height>",
                    "width": "<target window width>"
                }
            }
        },
        "settings": {
            ...
        },
        "version": 6 # current version as of writing this docstring
    }
    ```
    """
    global profiles, _current_profile
    profile_order = get_profile_sorting()
    if PROFILES_PATH.exists() and PROFILES_PATH.is_file():
        lp_text = PROFILES_PATH.read_text()
        try:
            lp_json = json.loads(lp_text)
        except json.JSONDecodeError as err:
            log.error("Failed reading launcher profiles JSON:", exc_info=err)
            log.warning("Loading default profiles. User should be notified.")
        else:
            profs_raw:dict = lp_json.get("profiles", _default_profs_factory())
            profs:dict[str, GameProfile] = {}
            has_latest_profile = False
            has_snapshot_profile = False
            if profile_order:
                new_order = []
                keys_leftover = [*profs_raw.keys()]
                for key in profile_order:
                    if key not in profs_raw:
                        log.warning(
                            "Sorting key doesn't exist as a profile, ignoring..."
                        )
                        continue
                    new_order.append(key)
                    keys_leftover.pop(keys_leftover.index(key))
                if keys_leftover:
                    log.warning("Orphaned profiles from sorting list, sorting "
                                "by creation date... (may be slow!)")
                    creation_order = []
                    for key in keys_leftover:
                        val = profs_raw[key]
                        dt_str = val.get("created", "1970-01-01T00:00:00.000Z")
                        try:
                            dt = datetime.fromisoformat(dt_str)
                        except:
                            log.error("Failed to get datetime from '%s', "
                                      "continuing..." % dt_str)
                            dt = datetime.min
                        idx = 0
                        for id in creation_order:
                            other_dt_str = profs_raw[id].get("created")
                            try:
                                other_dt = datetime.fromisoformat(other_dt_str)
                            except:
                                log.error("Failed to get datetime from '%s', "
                                          "ignoring..." % other_dt_str)
                                other_dt = datetime.min
                            if other_dt < dt:
                                idx += 1
                        if idx >= len(creation_order) - 1:
                            creation_order.append(key)
                        else:
                            creation_order.insert(idx, key)
                    new_order = new_order + creation_order
                profile_order = new_order
            else:
                profile_order = profs_raw.keys()
            for key in profile_order:
                val = profs_raw[key]
                prof_type = val.get("type", "")
                profs[key] = GameProfile.from_dict_compat(val, key)
                match prof_type:
                    case "latest-release":
                        has_latest_profile = True
                        profs[key].is_default_profile = True
                    case "latest-snapshot":
                        has_snapshot_profile = True
                        profs[key].is_default_profile = True
            if not has_latest_profile:
                log.warning("Missing latest release profile! Creating one...")
                uid = str(uuid.uuid4())
                profs[uid] = GameProfile("", type="latest-release",
                                         version_id="latest-release")
            if not has_snapshot_profile:
                log.warning("Missing latest snapshot profile! Creating one...")
                uid = str(uuid.uuid4())
                profs[uid] = GameProfile("", type="latest-snapshot",
                                         version_id="latest-snapshot")
            log.debug("Loaded %d profiles from 'launcher_profiles.json'"
                      % len(profs))
            profiles = profs
    else:
        log.info("Couldn't find 'launcher_profiles.json', generating new one.")
        profiles = _default_profs_factory()
    _current_profile = get_last_used_profile()
    _refresh_profiles()
    return profiles

def save_launcher_profiles(profiles_:dict[str, GameProfile]|None=None,
                           settings:dict[str, bool|str]|None=None):
    """
    Saves profiles to `launcher_profiles.json`.
    
    Valid `settings` entries:
    - `crashAssistance: bool`
    - `enableAdvanced: bool`
    - `enableAnalytics: bool`
    - `enableHistorical: bool`
    - `enableReleases: bool`
    - `enableSnapshots: bool`
    - `keepLauncherOpen: bool`
    - `profileSorting: str` **(Unknown values)**
    - `showGameLog: bool`
    - `showMenu: bool`
    - `soundOn: bool`
    """
    global profiles
    if profiles_:
        log.warning("Overriding global profiles list!")
        profiles = profiles_
    if not profiles:
        log.warning("No profiles are present! Saving default list...")
        profiles = _default_profs_factory()
    if not settings:
        settings = {**_DEFAULT_SETTINGS_JSON}
    profiles_json = {k: v.to_dict_compat() for k, v in profiles.items()}
    output = {
        "profiles": profiles_json,
        "settings": settings,
        "version": 6
    }
    _save_sorting_order(profiles_json.keys())
    json_out = json.dumps(
        output, indent=2, sort_keys=True, separators=(", ", " : ")
    )
    PROFILES_PATH.write_text(json_out)
    log.debug("Saved %d profiles to 'launcher_profiles.json'"
              % len(profiles_json))
    _refresh_profiles()
    return True

def get_last_used_profile(profiles_:dict[str, GameProfile]|None=None):
    """Returns the last used profile in the dict."""
    if not profiles_:
        global profiles
    else:
        profiles = profiles_
    latest = -1.0
    last_used_profile:GameProfile|None=None
    for uid, profile in profiles.items():
        ts = datetime.fromisoformat(profile.last_used).timestamp()
        if ts > latest:
            latest = ts
            last_used_profile = profile
    if not last_used_profile:
        raise ValueError("No profiles were present!")
    return last_used_profile

def save_single_profile(profile:GameProfile):
    global profiles
    profiles[profile.uuid] = profile
    save_launcher_profiles()
    _refresh_profiles()

def delete_single_profile(profile:GameProfile):
    global profiles, _current_profile
    row = get_row_from_profile(profile)
    del profiles[profile.uuid]
    if profile == _current_profile:
        set_current_profile(get_last_used_profile())
    SIGNAL.profile_deleted.emit(profile.uuid, row)
    save_launcher_profiles()

def create_profile():
    log.info("Creating new profile...")
    global profiles
    prof = GameProfile()
    profiles[prof.uuid] = prof
    SIGNAL.profile_added.emit(prof)
    set_current_profile(prof)
    save_launcher_profiles()
    return prof