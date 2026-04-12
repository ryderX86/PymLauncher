"""
Handles fetching & downloading version manifest JSON files, resolving version
inheritence, and downloading the client JAR file.
"""

from datetime import datetime, timedelta
from typing import Any, Callable
from functools import lru_cache
import hashlib
import json
import logging
import os
import re

import requests

from minecraftlauncher.constants import (
    VERSION_MANIFEST_URL, MINECRAFT_DIR, offline_mode, LOG4J_FIX_TIME,
    LOG4J_VULN_MIN_TIME, LOG4J_116_5_FIX_MAX_TIME, LOG4J_17_112_FIX_MAX_TIME
)
from minecraftlauncher.datatypes.game_version import GameVersionStub
from .download_manager import download

log = logging.getLogger(__name__)

VERSION_DIR = MINECRAFT_DIR / "versions"
_manifest_cache:dict = {
    "latest": {},
    "versions": []
}

FABRIC_VER_RE = re.compile(
    r"(?:fabric-loader-)((?:[0-9]+\.?)+)-((?:[0-9]+\.?)+(?:-snapshot-[0-9]+)?)"
)

_version_list_cache:list[GameVersionStub] = []

_inheritence_cache:dict[str,dict] = {}

def _get_manifest_cache_ids():
    fetch_version_manifest()
    version_list:list[str] = []
    for version in _manifest_cache.get("versions", []):
        id = version.get("id", "")
        if not id:
            continue
        version_list.append(id)
    return version_list

def fetch_version_manifest(force_refresh:bool=False):
    """
    Fetch full verison manifest from Mojang. (Won't force refresh <1d unless
    specified)

    Returns the parsed dict.
    Ex.:

    ```
    {
        "latest": {
            "release": "1.21.11",
            "snapshot": "26.1-rc-2"
        },
        "versions": [
            {
                "id": "26.1-rc-2",
                "type": "snapshot",
                "url": "<manifest URL>",
                "time": "<build time>",
                "releaseTime": "<release time>",
                "sha1": "<manifest SHA1>",
                "complianceLevel": 0|1 # (int as boolean, whether or not safety
                                       # features are supported)
            },
            ...
        ]
    }
    ```
    """
    global _manifest_cache
    if _manifest_cache.get("versions", []) and not force_refresh:
        return _manifest_cache
    
    log.debug("Looking for existing version manifest")
    mf_path = MINECRAFT_DIR / "versions" / "version_manifest_v2.json"
    if mf_path.exists():
        log.debug("Found it! Checking age...")
        max_age = (datetime.now() - timedelta(days=1)).timestamp()
        if mf_path.stat().st_mtime > max_age:
            mf_text = mf_path.read_text()
            try:
                mf = json.loads(mf_text)
            except json.JSONDecodeError as err:
                log.error("JSON decoding failed:", exc_info=err)
                log.info("Failed to read version manifest! Re-downloading...")
                mf_path.unlink()
            else:
                _manifest_cache = mf
                return _manifest_cache
        else:
            log.debug("Existing manifest is too old, getting a new one.")
    
    log.info("Fetching version manifest from '%s'" % VERSION_MANIFEST_URL)
    VERSION_DIR.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(VERSION_MANIFEST_URL, timeout=30)
    except:
        log.error("Failed to get version manifest!")
        return _manifest_cache
    _manifest_cache = resp.json()
    mf_path.touch()
    mf_path.write_text(json.dumps(_manifest_cache))
    return _manifest_cache

def _build_local_version_list(exclude:list[GameVersionStub]|None=None):
    if not exclude:
        exclude = []
    versions_dir = MINECRAFT_DIR / "versions"
    ver_list:list[GameVersionStub] = []
    for folder in os.scandir(versions_dir):
        if not folder.is_dir():
            continue
        jar_path = versions_dir / folder.name / f"{folder.name}.jar"
        json_path = versions_dir / folder.name / f"{folder.name}.json"
        if not json_path.exists():
            log.warning("Version %s doesn't have a JSON file!" % folder.name)
            continue
        try:
            ver_json_text = json_path.read_text()
        except Exception as err:
            log.warning("Failed to read file at '%s' for version %s"
                        % (str(json_path), folder.name), exc_info=err)
            continue
        try:
            ver_json = json.loads(ver_json_text)
        except json.JSONDecodeError as err:
            log.warning("Failed to parse JSON in '%s':" % str(json_path),
                        exc_info=err)
            continue
        version_info = GameVersionStub(folder.name,
                                       ver_json.get("type", "release"),
                                       json_path, True,
                                       ver_json.get("releaseTime"),
                                       ver_json.get("time"))
        if version_info in exclude:
            continue
        ver_list.append(version_info)
    return ver_list

@lru_cache(maxsize=1)
def get_installed_versions():
    return _build_local_version_list()

@lru_cache(maxsize=1)
def get_latest_installed():
    versions_initial = get_installed_versions()
    versions = []
    for v in versions_initial:
        if v.jar_path.exists():
            versions.append(v)
    if len(versions) < 1:
        raise RuntimeError("No versions installed!")
    latest_version_installed = versions[0]
    for v in versions:
        if latest_version_installed.timestamp < v.timestamp:
            latest_version_installed = v
    return latest_version_installed

def get_version_list(include_snapshots:bool=True,
                     include_old:bool=True,
                     override:bool=False) -> list[GameVersionStub]:
    """
    Returns a list of versions from both the manifest and locally installed.
    
    Duplicates will side with the manifest and the local version won't be
    included.
    
    Each entry is a dict with at least `id` and `type`, and will contain `url`
    or `path`.
    """
    global _version_list_cache
    global _inheritence_cache
    manifest = fetch_version_manifest()
    mf_versions:list[dict] = manifest.get("versions", [])
    if _version_list_cache and not override:
        return _version_list_cache
    elif override:
        log.debug("Forcibly refreshing versions cache")
        _inheritence_cache = {}
    versions = []
    for ver in mf_versions:
        id = ver.get("id")
        if not id:
            log.warning("Skipping unknown version (no ID) in\
                        get_version_list().")
            continue
        url = ver.get("url")
        if not url:
            log.warning("Skipping version '%s' since it has no manifest URL."
                        % id)
            continue
        type_ = ver.get("type", "release")
        match type_:
            case "snapshot":
                if not include_snapshots:
                    continue
            case "old_alpha" | "old_beta":
                if not include_old:
                    continue
            case "release":
                pass
            case _:
                log.debug("Unexpected release type: '%s'" % type_)
        timestamp = ver.get("releaseTime", ver.get("time"))
        build_ts = ver.get("time", ver.get("releaseTime"))
        new_ver = GameVersionStub(id, type_, url, False, timestamp, build_ts)
        versions.append(new_ver)
    versions.extend(_build_local_version_list(versions))
    _version_list_cache = versions
    versions.sort(key=lambda v: v.timestamp, reverse=True)
    log.debug("Done refreshing versions")
    return versions

def get_latest_release() -> str:
    """Returns the latest version ID, if possible."""
    fetch_version_manifest()
    if not _manifest_cache.get("latest"):
        return ""
    return _manifest_cache["latest"].get("release")

def get_latest_snapshot() -> str:
    """Returns the latest snapshot ID, if possible."""
    fetch_version_manifest()
    if not _manifest_cache.get("latest"):
        return ""
    return _manifest_cache["latest"].get("snapshot")

def _get_manifest_entry(version_id:str) -> dict[str, Any]|None:
    for ver in _manifest_cache["versions"]:
        if ver["id"] == version_id:
            return ver

def fetch_version_json(version_id:str) -> dict[str, Any]:
    """
    Fetch and return the full version JSON for `version_id`.

    The JSON is saved to `.minecraft/versions/<id>/<id>.json` as is done in the
    official launcher.

    When downloading, the file will be cached. If the file exists but isn't in
    the manifest, it'll be returned if it can be read as JSON. If the file
    exists and is in the manifest, the SHA1 will be compared, and if it
    matches, it'll be returned, else it'll redownload.

    If the file doesn't exist but the ID is in the manifest, it'll download
    the manifest.

    If all else fails (or JSON decoding for a local version fails) it'll raise
    a `ValueError`.
    """
    fetch_version_manifest()
    ver_dir = VERSION_DIR / version_id
    local_path = ver_dir / f"{version_id}.json"

    mf_entry = _get_manifest_entry(version_id)

    # check local files
    if local_path.exists():
        local_bytes = local_path.read_bytes()
        local_sha1 = hashlib.sha1(local_bytes).hexdigest()
        if (mf_entry and mf_entry["sha1"] == local_sha1) or (not mf_entry):
            local_text = local_path.read_text("utf-8")
            try:
                return json.loads(local_text)
            except json.JSONDecodeError as err:
                log.error("JSON decode failed for '%s':" % str(local_path),
                          exc_info=err)
                raise ValueError("Version '%s' has corrupted JSON"
                                 % version_id)
        else:
            log.warning("Version info at '%s' doesn't match SHA1 in manifest!"
                        % str(local_path))
    # no local file + no mf entry = bad bad very bad
    if not mf_entry:
        raise ValueError("Version '%s' not found in manifest or locally"
                         % version_id)
    
    url = mf_entry["url"]
    sha1 = mf_entry["sha1"]
    log.info("Downloading version JSON for '%s' from '%s'" % (version_id, url))
    try:
        resp = download(url, hash=sha1)
    except:
        raise

    if not ver_dir.exists():
        ver_dir.mkdir(parents=True, exist_ok=True)
    local_path.touch()
    local_path.write_text(resp.text)
    return resp.json()

def _resolve_inheritence(version_json:dict, recursion:int=0, *,
                         force_refresh:bool=False) -> dict[str, Any]:
    global _inheritence_cache
    if version_json["id"] in _inheritence_cache and not force_refresh:
        return _inheritence_cache[version_json["id"]]
    if recursion > 20:
        raise RecursionError()
    
    if "inheritsFrom" not in version_json.keys():
        return version_json
    
    parent_id:str = version_json["inheritsFrom"]
    log.debug("Game version '%s' inherits from '%s'"
              % (version_json["id"], parent_id))
    
    parent_json = fetch_version_json(parent_id)
    parent_json = _resolve_inheritence(parent_json, recursion=recursion + 1)

    merged_json = {**parent_json}

    for key, val in version_json.items():
        # continue is used so `case _` doesn't have to be, since we're already
        # very close to getting to col 80 and it might as well be the same
        match key:
            case "inheritsFrom":
                continue
            case "libraries":
                parent_libs = parent_json.get("libraries", [])
                val.extend(parent_libs)
                merged_json["libraries"] = val
                continue
            case "arguments":
                merged_args = parent_json.get("arguments", {})
                for argtype in ("game", "jvm"):
                    child_args = val.get(argtype, [])
                    parent_args = merged_args.get(argtype, [])
                    child_args.extend(parent_args)
                    merged_args[argtype] = child_args
                merged_json["arguments"] = merged_args
                continue
        if isinstance(val, dict) and isinstance(merged_json.get(key), dict):
            merged_dict = merged_json[key]
            merged_dict.update(val)
            merged_json[key] = merged_dict
        elif isinstance(val, list) and isinstance(merged_json.get(key), list):
            parent_list:list = merged_json[key]
            child_list:list = version_json[key]
            parent_list = [x for x in parent_list if x not in child_list]
            child_list.extend(parent_list)
            merged_json[key] = child_list
        else:
            merged_json[key] = val
    _inheritence_cache[version_json["id"]] = merged_json
    return merged_json

def resolve_inheritence(version_json:dict):
    """
    Resolve `inheritsFrom` chains and merges all data into the given JSON.

    If the chain exceeds 20 *(an already far, far excessive amount)*, then a
    `RecursionError` is raised.

    <sub>Stub function that calls `_resolve_inheritence()`.</sub>
    """
    return _resolve_inheritence(version_json)

def get_client_jar_info(version_json:dict) -> dict[str, Any]|None:
    """
    Returns either the `version_json.downloads.client` dict (containing `sha1`,
    `size`, and `url`) or `None` if not present.
    """
    return version_json.get("downloads", {}).get("client")

def download_client_jar(version_json:dict, *,
                        progress_callback:Callable|None=None):
    """
    Downloads the client JAR file for the given version JSON, if it doesn't
    exist; or check the existing JAR file's SHA1 and either return its path,
    or redownload it depending on if the SHA1 matches or not.

    Returns the path to the downloaded file.

    If `progress_callback` is given, this will call it with `(bytes_downloaded,
    total_bytes)`.

    ### Raises
    - `ValueError`, if the download info isn't in the version info JSON.
    - `requests.HTTPError`, if a non-20X HTTP status code was given.
    - `requests.RequestException` (or sub-class), if a request exception
    occurs.
    - `RuntimeError`, if the download failed enough times.
    """
    ver_id:str = version_json["id"]
    client_info = get_client_jar_info(version_json)
    if not client_info:
        raise ValueError("No download info for version '%s'" % ver_id)
    expected_sha1 = client_info.get("sha1")
    
    ver_dir = VERSION_DIR / ver_id
    jar_path = ver_dir / f"{ver_id}.jar"

    # check for existing file and return if SHA1 matches
    if jar_path.exists() and jar_path.is_file() and expected_sha1:
        jar_bytes = jar_path.read_bytes()
        sha1 = hashlib.sha1(jar_bytes).hexdigest()
        if sha1 == expected_sha1:
            log.debug("Skipping download for '%s.jar' since it already exists."
                      % ver_id)
            return jar_path
        else:
            log.warning("'%s.jar' SHA1 doesn't match expected: '%s' != '%s'"
                        % (ver_id, sha1, str(expected_sha1)))
    
    url = client_info["url"]
    total_size = client_info.get("size", 0)
    log.info("Downloading client JAR for %s (%s bytes)" % (ver_id, total_size))

    ver_dir.mkdir(parents=True, exist_ok=True)

    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    downloaded = 0
    sha1 = hashlib.sha1()
    with open(jar_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            sha1.update(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total_size)

    if expected_sha1 and sha1.hexdigest() != expected_sha1:
        log.debug("SHA1 mismatch, deleting JAR.")
        jar_path.unlink()
        err = RuntimeError("SHA1 mismatch for client JAR")
        err.add_note("Expected '%s', got '%s'"
                     % (expected_sha1, sha1.hexdigest()))
        raise err
    
    return jar_path

def check_client_jar(version_json:dict):
    """
    Checks if the client jar is installed or not.
    
    Returns `True` if the client JAR is installed.
    """
    ver_id:str = version_json["id"]
    client_info = get_client_jar_info(version_json)
    if not client_info:
        raise ValueError("No download info for version '%s'" % ver_id)
    expected_sha1:str|None = client_info.get("sha1")

    ver_dir = VERSION_DIR / ver_id
    jar_path = ver_dir / f"{ver_id}.jar"

    if jar_path.exists() and jar_path.is_file() and expected_sha1:
        jar_bytes = jar_path.read_bytes()
        sha1 = hashlib.sha1(jar_bytes).hexdigest()
        return bool(sha1 == expected_sha1)
    elif jar_path.exists() and jar_path.is_file():
        log.warning("Unable to check SHA1 for JAR at '%s'" % str(jar_path))
        return True
    return False

def version_exists(id:str):
    """
    Checks if a version exists in the Mojang manifest or locally
    
    Returns a bool
    """
    if id in _manifest_cache["versions"]:
        return True
    elif (VERSION_DIR / id).exists():
        return True
    elif (VERSION_DIR / id / f"{id}.json").exists():
        try:
            json.loads((VERSION_DIR / id / f"{id}.json").read_text())
        except:
            return False
        else:
            return True
    return False

def check_fabric_mod_arg_support(version_id:str):
    """
    Checks if a given version ID is newer than Fabric 0.12.0
    """
    fabric_match = FABRIC_VER_RE.match(version_id)
    if not fabric_match:
        return False
    elif not fabric_match[1]:
        return False
    
    fabric_ver_split = fabric_match[1].split(".")
    if fabric_ver_split[0].isdecimal():
        i = int(fabric_ver_split[0])
        if i > 0:
            return True
    if fabric_ver_split[1].isdecimal():
        i = int(fabric_ver_split[1])
        if i >= 12:
            return True
    return False

def log4j_fix(version_info:dict|GameVersionStub):
    """
    Returns the log4j fix for the version given, as well as a bool as to if
    the client may be vulnerable regardless or not to notify the user.
    """
    max_dt = datetime.fromisoformat(LOG4J_FIX_TIME).timestamp()
    dt_112_1165 = datetime.fromisoformat(LOG4J_116_5_FIX_MAX_TIME).timestamp()
    dt_17_112 = datetime.fromisoformat(LOG4J_17_112_FIX_MAX_TIME).timestamp()
    min_dt = datetime.fromisoformat(LOG4J_VULN_MIN_TIME)
    t = rt = min_ = datetime.min.timestamp()
    
    client_unverified = False
    if isinstance(version_info, dict):
        version_info = resolve_inheritence(version_info)
        if version_info.get("releaseTime"):
            rt = datetime.fromisoformat(
                version_info["releaseTime"]
            ).timestamp()
        if version_info.get("time"):
            t = datetime.fromisoformat(version_info["time"]).timestamp()
        if (not version_info.get("releaseTime")
            and not version_info.get("time")):
            log.warning("Couldn't get release time! Client may be vulnerable.")
            client_unverified = True
    else:
        rt = version_info.timestamp
        t = version_info.build_timestamp
    # get the oldest timestamp:
    if t != min_ and rt != min_:
        ts = min(rt, t)
    elif t != min_ and rt > t:
        ts = t
    elif rt != min_ and t > rt:
        ts = rt
    else:
        log.warning("Couldn't get timestamp! Client may be vulnerable.")
        client_unverified = True
        ts = t

    FIX = None

    if ts >= max_dt:
        return "", client_unverified
    elif ts < max_dt and ts >= dt_112_1165:
        FIX = "112_1165"
    elif ts < dt_112_1165 and ts >= dt_17_112:
        FIX = "17_112"
    elif ts < dt_17_112:
        return "", client_unverified
    else:
        raise

    if FIX is None:
        client_unverified = True
        return "", client_unverified
    
