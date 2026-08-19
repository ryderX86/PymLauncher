"""
minecraftlauncher.back.profile_manager

Manages game profiles (version selection, game directory, JVM args,
etc.)

Supports reading the official Minecraft launcher's
``launcher_profiles.json`` format for compatibility.
"""

from collections.abc import Callable, Iterable
from typing import Any, Literal
from datetime import datetime
from types import FunctionType
from functools import lru_cache
import logging
import time
import json
import uuid
import os

from PySide6.QtCore import Signal, QObject

from minecraftlauncher.config import config
from minecraftlauncher.paths import paths
from minecraftlauncher.datatypes import LaunchProfile
from minecraftlauncher.functions import reswrite
from minecraftlauncher import get_exit_status

log = logging.getLogger(__name__)

_DEFAULT_SETTINGS_JSON: dict[str, Any] = {
    "crashAssistance": False,
    "enableAdvanced": True,
    "enableAnalytics": False,
    "enableHistorical": True,
    "enableReleases": True,
    "enableSnapshots": True,
    "keepLauncherOpen": False,
    "showGameLog": False,
    "showMenu": False,
    "soundOn": False,
}

type ProfileType = Literal["custom", "latest-release", "latest-snapshot"]

profiles: dict[str, LaunchProfile] = {}

_current_profile: LaunchProfile | None = None
_profile_switch_handlers: list[Callable[[LaunchProfile], None]] = []
_profile_refresh_handlers: list[Callable] = []

_launcher_settings = {**_DEFAULT_SETTINGS_JSON}


@lru_cache(maxsize=32)
def get_row_from_profile(profile: LaunchProfile):
    i = 0
    for _, prof in profiles.items():
        if prof == profile:
            return i
        else:
            i += 1
    raise IndexError(
        f"Profile {profile.name!r} (ID: {profile.uuid!r}) not in cache"
    )


def reorder_profiles(new_order: Iterable[str]):
    """
    Reorder profiles cache in the order of IDs provided
    """
    global profiles
    new_profiles: dict[str, LaunchProfile] = {}
    for profile_id in new_order:
        if profile_id not in profiles:
            raise ValueError(
                f"ID given for profile reordering doesn't exist: {profile_id!r}"
            )

        new_profiles[profile_id] = profiles[profile_id]
    leftover = [*filter(lambda k: k not in new_order, profiles.keys())]
    if leftover:
        for profile_id in leftover:
            log.warning(
                "Profile with ID '%s' was orphaned during reordering, "
                "adding it back in.",
                profile_id,
            )
            new_profiles[profile_id] = profiles[profile_id]
    profiles = new_profiles
    _refresh_profiles()
    _save_sorting_order(profiles.keys())
    return


def reorder_single_profile(prof: LaunchProfile, idx: int):
    ids = [*profiles.keys()]
    if prof.uuid not in ids:
        raise ValueError("Profile ID not present in profiles!")
    ids.pop(ids.index(prof.uuid))
    ids.insert(idx, prof.uuid)
    return reorder_profiles(ids)


def add_profile_switch_handler(func: Callable[[LaunchProfile], None]):
    """
    Adds a function to the profile switch handler list, then outputs the index.

    TODO: See if `pyqtSignal()` is better for this.
    """
    _profile_switch_handlers.append(func)
    return _profile_switch_handlers.index(func)


def remove_profile_switch_handler(
    func_idx: Callable[[LaunchProfile], None] | int,
):
    match func_idx:
        case int():
            if func_idx > len(_profile_switch_handlers):
                raise IndexError()
            _profile_switch_handlers.pop(func_idx)
            return
        case FunctionType() | Callable():
            if func_idx not in _profile_switch_handlers:
                return
            _profile_switch_handlers.pop(
                _profile_switch_handlers.index(func_idx)
            )
        case _:
            raise TypeError(f"Unexpected type: {type(func_idx).__name__!r}")
    return


def _refresh_profiles():
    if get_exit_status():
        return
    # something probably changed in the main cache, so clear LRU for row getter
    get_row_from_profile.cache_clear()
    for func in _profile_refresh_handlers:
        func()


def add_profile_refresh_handler(func: Callable):
    _profile_refresh_handlers.append(func)
    return _profile_refresh_handlers.index(func)


def remove_profile_refresh_handler(func_idx: Callable | int):
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


def get_profile(idx: str | int) -> LaunchProfile:
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
            raise TypeError(
                f"Unexpected type for 'idx': {type(idx).__name__!r}"
            )


def set_current_profile_uuid(uid: str):
    current_prof: LaunchProfile | None = None
    if uid not in profiles:
        raise NameError(name=uid)
    current_prof = profiles[uid]
    return set_current_profile(current_prof)


def set_current_profile(prof: LaunchProfile):
    if get_exit_status():
        return
    global _current_profile
    log.debug("Switching profile to %r (ID: %r)", prof.name, prof.uuid)
    _current_profile = profiles[prof.uuid]
    for func in _profile_switch_handlers:
        func(prof)
    return


def current_profile_used():
    prof = get_current_profile()
    log.info(
        "Setting profile %r (ID: %r) last used to now.", prof.name, prof.uuid
    )
    prof.last_used = datetime.now().isoformat()
    save_single_profile(prof)


class _Signal(QObject):
    profile_added = Signal(LaunchProfile)
    profile_deleted = Signal(str, int)  # uid, row
    """`uid: str, row: int`"""


SIGNAL = _Signal()

_meta_cache = {}


def get_launcher_meta():
    if _meta_cache or getattr(get_launcher_meta, "ran_once", False):
        return _meta_cache
    get_launcher_meta.ran_once = True  # type: ignore
    if os.path.isfile(paths.profiles_meta_file):
        with open(paths.profiles_meta_file, "r") as f:
            txt = f.read()
        try:
            meta = json.loads(txt)
        except Exception as err:
            log.error(
                "Failed to read launcher_profiles_meta.json:", exc_info=err
            )
            return {}
        else:
            return meta
    return {}


def save_launcher_meta():
    if not _meta_cache:
        return
    try:
        meta_json = json.dumps(_meta_cache)
    except Exception as err:
        log.error("Failed to dump _meta_cache JSON!", exc_info=err)
        raise
    else:
        reswrite(paths.profiles_meta_file, meta_json)


def get_profile_sorting():
    meta = get_launcher_meta()
    if meta:
        return meta.get("order", [])
    return [*profiles.keys()]


def _save_sorting_order(data: Iterable[str]):
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
        latest_uid: LaunchProfile(
            "Latest Release",
            type="latest-release",
            uuid=latest_uid,
            is_default_profile=True,
            icon="Grass",
        ),
        snapshot_uid: LaunchProfile(
            "Latest Snapshot",
            version_id="latest-snapshot",
            uuid=snapshot_uid,
            type="latest-snapshot",
            is_default_profile=True,
            icon="Dirt",
        ),
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
        "version": 6,
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
    if os.path.isfile(paths.profiles_file):
        with open(paths.profiles_file, "r") as f:
            lp_text = f.read()
        try:
            lp_json = json.loads(lp_text)
        except json.JSONDecodeError as err:
            log.error("Failed reading launcher profiles JSON:", exc_info=err)
            raise
        else:
            profs_raw: dict = lp_json.get("profiles", _default_profs_factory())
            profs: dict[str, LaunchProfile] = {}
            has_latest_profile = False
            has_snapshot_profile = False
            for k, v in lp_json.get("settings", {}).items():
                if k not in _DEFAULT_SETTINGS_JSON:
                    log.warning(
                        'Unknown key in launcher_profiles.json["settings"]: '
                        "%r",
                        k,
                    )
                    continue
                elif not isinstance(v, type(_launcher_settings[k])):
                    log.warning(
                        "Type mismatch for launcher_profiles.json[%r]; "
                        "expected %r, got %r. Discarding value and ignoring.",
                        k,
                        type(_launcher_settings[k]),
                        type(v),
                    )
                    continue
                _launcher_settings[k] = v
            if (
                profile_order
            ):  # TODO: change sorting methods to less crappy ones
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
                    log.warning(
                        "Orphaned profiles from sorting list, sorting "
                        "by last used date... (may be slow!)"
                    )
                    creation_order = []
                    for key in keys_leftover:
                        val = profs_raw[key]
                        dt_str = val.get("lastUsed", "1970-01-01T00:00:00.000Z")
                        try:
                            dt = datetime.fromisoformat(dt_str)
                        except:
                            log.error(
                                "Failed to get datetime from '%s', "
                                "continuing...",
                                dt_str,
                            )
                            dt = datetime.min
                        idx = 0
                        for id_ in creation_order:
                            other_dt_str = profs_raw[id_].get("lastUsed")
                            try:
                                other_dt = datetime.fromisoformat(other_dt_str)
                            except:
                                log.error(
                                    "Failed to get datetime from '%s', "
                                    "ignoring...",
                                    other_dt_str,
                                )
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
                profs[key] = LaunchProfile.from_dict_compat(val, key)
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
                profs[uid] = LaunchProfile(
                    "", type="latest-release", version_id="latest-release"
                )
            if not has_snapshot_profile:
                log.warning("Missing latest snapshot profile! Creating one...")
                uid = str(uuid.uuid4())
                profs[uid] = LaunchProfile(
                    "", type="latest-snapshot", version_id="latest-snapshot"
                )
            log.info(
                "Loaded %s profiles from 'launcher_profiles.json'", len(profs)
            )
            profiles = profs
    else:
        log.info("Couldn't find 'launcher_profiles.json', generating new one.")
        profiles = _default_profs_factory()
    _current_profile = get_last_used_profile()
    _refresh_profiles()
    return profiles


def save_launcher_profiles(
    profiles_: dict[str, LaunchProfile] | None = None,
    settings: dict[str, bool | str | int] | None = None,
):
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
    if _launcher_settings != _DEFAULT_SETTINGS_JSON and not settings:
        settings = _launcher_settings
    elif settings:
        log.warning(
            'Overriding launcher_profiles["settings"] with defined value'
        )
    else:
        settings = _DEFAULT_SETTINGS_JSON
    profiles_json = {k: v.to_dict_compat() for k, v in profiles.items()}
    output = {"profiles": profiles_json, "settings": settings, "version": 6}
    _save_sorting_order(profiles_json.keys())
    if config.enforce_json_spec:
        separators = None
    else:
        separators = (", ", " : ")
    json_out = json.dumps(
        output, indent=2, sort_keys=True, separators=separators
    )
    reswrite(paths.profiles_file, json_out)
    log.info(
        "Saved %s profiles to 'launcher_profiles.json'", len(profiles_json)
    )
    _refresh_profiles()
    return True


def reset_profiles():
    """
    Renames launcher_profiles.json and launcher_profiles_meta.json to store
    them as backups
    """
    backup_time = int(time.time())
    os.replace(paths.profiles_file, f"{paths.profiles_file}-{backup_time}.bak")
    os.replace(
        paths.profiles_meta_file,
        f"{paths.profiles_meta_file}-{backup_time}.bak",
    )


def get_last_used_profile(profiles_: dict[str, LaunchProfile] | None = None):
    """Returns the last used profile in the dict."""
    if not profiles_:
        global profiles
    else:
        profiles = profiles_
    latest = -1.0
    last_used_profile: LaunchProfile | None = None
    for profile in profiles.values():
        ts = datetime.fromisoformat(profile.last_used).timestamp()
        if ts > latest:
            latest = ts
            last_used_profile = profile
    if not last_used_profile:
        raise ValueError("No profiles were present!")
    return last_used_profile


def save_single_profile(profile: LaunchProfile):
    profiles[profile.uuid] = profile
    save_launcher_profiles()
    _refresh_profiles()


def delete_single_profile(profile: LaunchProfile):
    row = get_row_from_profile(profile)
    del profiles[profile.uuid]
    if profile == _current_profile:
        set_current_profile(get_last_used_profile())
    SIGNAL.profile_deleted.emit(profile.uuid, row)
    save_launcher_profiles()


def create_profile():
    log.info("Creating new profile...")
    prof = LaunchProfile()
    profiles[prof.uuid] = prof
    SIGNAL.profile_added.emit(prof)
    set_current_profile(prof)
    save_launcher_profiles()
    return prof
