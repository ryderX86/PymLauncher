"""
Handles fetching & downloading version manifest JSON files, resolving version
inheritence, and downloading the client JAR file.

`OS_PATH_DELIM` from `minecraftlauncher.constants` is imported as `D` for use
in `os.path` strings as a forward or back slash for OS independant behavior.
"""

from datetime import datetime, timedelta
from typing import Any, Callable
import hashlib
import json
import logging
import os
import re

from minecraftlauncher.constants import (
    VERSION_MANIFEST_URL,
    MINECRAFT_DIR,
    DEFAULT_JVM_ARGS,
)
from minecraftlauncher.datatypes.game_version import GameVersionStub
from minecraftlauncher.config import redownload_option
from minecraftlauncher import SESSION
from .library_manager import evaluate_rules
from .download_helpers import download

log = logging.getLogger(__name__)

VERSION_DIR = os.path.join(MINECRAFT_DIR, "versions")
manifest_cache: dict = {"latest": {}, "versions": []}

FABRIC_VER_RE = re.compile(
    r"(?:fabric-loader-)((?:[0-9]+\.?)+)-((?:[0-9]+\.?)+(?:-snapshot-[0-9]+)?)"
)

_version_list_cache: list[GameVersionStub] = []

_inheritence_cache: dict[str, dict] = {}

_args_cache: dict[str, str] = {}

_version_json_cache: dict[str, dict] = {}


def _get_manifest_cache_ids():
    fetch_version_manifest()
    version_list: list[str] = []
    for version in manifest_cache.get("versions", []):
        id_ = version.get("id", "")
        if not id_:
            continue
        version_list.append(id_)
    return version_list


def fetch_version_manifest(force_refresh: bool = False):
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
    global manifest_cache
    if manifest_cache["versions"] and not force_refresh:
        return manifest_cache

    log.info("Looking for existing version manifest")
    mf_path = os.path.join(
        MINECRAFT_DIR, "versions", "version_manifest_v2.json"
    )
    if os.path.isfile(mf_path) and not force_refresh:
        log.info("Found it! Checking age...")
        max_age = (datetime.now() - timedelta(hours=4)).timestamp()
        if os.lstat(mf_path).st_mtime > max_age:
            with open(mf_path, "r") as f:
                mf_text = f.read()
            try:
                mf = json.loads(mf_text)
            except json.JSONDecodeError as err:
                log.warning(
                    "Failed to read version manifest! Re-downloading...",
                    exc_info=err,
                )
            else:
                if (
                    "snapshot" not in mf["latest"]
                    or "release" not in mf["latest"]
                ):
                    log.warning(
                        "Manifest cache is in an invalid format, "
                        "re-downloading."
                    )
                else:
                    log.debug("Using existing versions cache.")
                    manifest_cache = mf
                    return manifest_cache
        else:
            log.info("Existing manifest is too old, getting a new one.")
    log.info("Fetching version manifest from '%s'", VERSION_MANIFEST_URL)
    os.makedirs(VERSION_DIR, exist_ok=True)
    try:
        resp = SESSION.get(VERSION_MANIFEST_URL, timeout=30)
    except:
        log.error("Failed to get version manifest!")
        return manifest_cache
    manifest_cache = resp.json()
    if "versions" not in manifest_cache:
        manifest_cache["versions"] = []
    elif "latest" not in manifest_cache:
        manifest_cache["latest"] = {}
    with open(mf_path, "w") as f:
        f.write(resp.text)
    return manifest_cache


def build_local_version_list(exclude: list[GameVersionStub] | None = None):
    if exclude is None:
        exclude = []
    ver_list: list[GameVersionStub] = []
    for folder in os.scandir(VERSION_DIR):
        if folder.name in exclude or not folder.is_dir():
            continue
        jar_path = os.path.join(folder.path, f"{folder.name}.jar")
        json_path = os.path.join(folder.path, f"{folder.name}.json")
        if not os.path.isfile(json_path):
            log.warning("Version %r doesn't have a JSON file!", folder.name)
            continue
        try:
            with open(json_path, "r") as f:
                ver_json_text = f.read()
        except Exception as err:
            log.warning(
                "Failed to read file at %r for version %r",
                json_path,
                folder.name,
                exc_info=err,
            )
            continue
        try:
            ver_json: dict = json.loads(ver_json_text)
        except json.JSONDecodeError as err:
            log.warning("Failed to parse JSON in %r:", json_path, exc_info=err)
            continue
        if (
            "downloads" not in ver_json
            and "inheritsFrom" not in ver_json
            and not os.path.isfile(jar_path)
        ):
            log.warning(
                "Version %r has no jar file and doesn't inherit from "
                "anything!",
                folder.name,
            )
            continue
        version_info = GameVersionStub(
            folder.name,
            ver_json.get("type", "release"),
            json_path,
            True,
            ver_json.get("releaseTime"),
            ver_json.get("time"),
        )
        ver_list.append(version_info)
    return ver_list


def get_version_list(
    override: bool = False,
) -> list[GameVersionStub]:
    """
    Returns a list of versions from both the manifest and locally installed.

    Duplicates will side with the manifest and the local version won't be
    included.

    Each entry is a dict with at least `id` and `type`, and will contain `url`
    or `path`.
    """
    global _version_list_cache
    global _version_json_cache
    global _inheritence_cache
    manifest = fetch_version_manifest()
    mf_versions: list[dict] = manifest.get("versions", [])
    if _version_list_cache and not override:
        return _version_list_cache
    elif override:
        log.debug("Forcibly refreshing versions cache")
        _inheritence_cache = {}
        _version_json_cache = {}
    versions = []
    for ver in mf_versions:
        id_ = ver.get("id")
        if not id_:
            log.warning(
                "Skipping unknown version (no ID) in get_version_list()."
            )
            continue
        url = ver.get("url")
        if not url:
            log.warning(
                "Skipping version %r since it has no manifest URL.", id_
            )
            continue
        type_ = ver.get("type", "release")
        timestamp = ver.get("releaseTime", ver.get("time"))
        build_ts = ver.get("time", ver.get("releaseTime"))
        stub = GameVersionStub(id_, type_, url, False, timestamp, build_ts)
        versions.append(stub)
    versions.extend(build_local_version_list(versions))
    _version_list_cache = versions
    # forge is expected to always appear at the bottom unfortuantely, since for
    # some ungodly reason before more recent versions they always set the time
    # to 1 DECADE before unix epoch (also 1 decade before???? WHY)
    versions.sort(reverse=True)
    log.info("Parsed complete versions list successfully.")
    return versions


def get_latest_release() -> str:
    """Returns the latest version ID, if possible."""
    fetch_version_manifest()
    if not manifest_cache["latest"]:
        return ""
    return manifest_cache["latest"]["release"]


def get_latest_snapshot() -> str:
    """Returns the latest snapshot ID, if possible."""
    fetch_version_manifest()
    if not manifest_cache["latest"]:
        return ""
    return manifest_cache["latest"]["snapshot"]


def get_latest_release_stub() -> GameVersionStub:
    id_ = get_latest_release()
    version = None
    for v in get_version_list():
        if v.id == id_:
            version = v
            break
    if not version:
        raise RuntimeError("Couldn't get the latest version's info")
    return version


def get_latest_snapshot_stub() -> GameVersionStub:
    id_ = get_latest_snapshot()
    version = None
    for v in get_version_list():
        if v.id == id_:
            version = v
            break
    if not version:
        raise RuntimeError("Couldn't get the latest snapshot's info")
    return version


def _get_manifest_entry(version_id: str) -> dict[str, Any] | None:
    for ver in manifest_cache["versions"]:
        if ver["id"] == version_id:
            return ver


def fetch_version_json(
    version_id: str, override: bool = False
) -> dict[str, Any]:
    """
    Fetch and return the full version JSON for `version_id`.

    The JSON is saved to `.minecraft/versions/<id>/<id>.json` as is done in the
    official launcher.

    When downloading, the file will be cached. If the file exists but isn't in
    the manifest, it'll be returned if it can be read as JSON. If the file
    exists and is in the manifest, the SHA1 will be compared, and if it
    matches, it'll be returned, otherwise it'll redownload.

    If the file doesn't exist but the ID is in the manifest, it'll download
    the manifest.

    If all else fails (or JSON decoding for a local version fails) it'll raise
    a `ValueError`.
    """
    if version_id in _version_json_cache and not override:
        return _version_json_cache[version_id]
    elif override:
        log.debug("Overriding cached version JSON for %r", version_id)
    fetch_version_manifest()
    ver_dir = os.path.join(VERSION_DIR, version_id)
    local_path = os.path.join(ver_dir, f"{version_id}.json")

    mf_entry = _get_manifest_entry(version_id)

    # check local files
    if os.path.isdir(ver_dir):
        with open(local_path, "rb") as f:
            local_bytes = f.read()
            local_text = local_bytes.decode("utf-8")
        local_sha1 = hashlib.sha1(local_bytes).hexdigest()
        if (mf_entry and mf_entry["sha1"] == local_sha1) or (not mf_entry):
            try:
                _version_json_cache[version_id] = json.loads(local_text)
                return _version_json_cache[version_id]
            except json.JSONDecodeError as err:
                log.error(
                    "JSON decode failed for %r:",
                    str(local_path),
                    exc_info=err,
                )
                raise ValueError(
                    f"Version {version_id!r} has corrupted JSON"
                ) from err
        else:
            log.warning(
                "Version info at %r doesn't match SHA1 in manifest!",
                str(local_path),
            )
    # no local file + no mf entry = bad bad very bad
    if not mf_entry:
        raise ValueError(
            f"Version '{version_id}' not found in manifest or locally"
        )

    url = mf_entry["url"]
    sha1 = mf_entry["sha1"]
    log.info("Downloading version JSON for %r from %r", version_id, url)
    try:
        resp = download(url, sha=sha1)
    except Exception as err:
        log.error(
            "Failed to download version.json for %r!", version_id, exc_info=err
        )
        raise

    if not os.path.isdir(ver_dir):
        os.makedirs(ver_dir)
    with open(local_path, "w") as f:
        f.write(resp.text)
    _version_json_cache[version_id] = resp.json()
    return _version_json_cache[version_id]


def _resolve_inheritence(
    version_json: dict, recursion: int = 0, *, force_refresh: bool = False
) -> dict[str, Any]:
    if version_json["id"] in _inheritence_cache and not force_refresh:
        return _inheritence_cache[version_json["id"]]
    if recursion > 20:
        raise RecursionError()

    if "inheritsFrom" not in version_json.keys():
        return version_json

    parent_id: str = version_json["inheritsFrom"]
    log.info("Game version %r inherits from %r", version_json["id"], parent_id)

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
            parent_list: list = merged_json[key]
            child_list: list = version_json[key]
            parent_list = [x for x in parent_list if x not in child_list]
            child_list.extend(parent_list)
            merged_json[key] = child_list
        else:
            merged_json[key] = val
    _inheritence_cache[version_json["id"]] = merged_json
    return merged_json


def resolve_inheritence(version_json: dict):
    """
    Resolve `inheritsFrom` chains and merges all data into the given JSON.

    If the chain exceeds 20 *(an already far, far excessive amount)*, then a
    `RecursionError` is raised.
    <br><sub>Stub function that calls `_resolve_inheritence()`.</sub>
    """
    return _resolve_inheritence(version_json)


def get_client_jar_info(version_json: dict) -> dict[str, Any] | None:
    """
    Returns either the `version_json.downloads.client` dict (containing `sha1`,
    `size`, and `url`) or `None` if not present.
    """
    return version_json.get("downloads", {}).get("client")


def download_client_jar(
    version_json: dict, *, progress_callback: Callable | None = None
):
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
    ver_id: str = version_json["id"]
    client_info = get_client_jar_info(version_json)
    if not client_info:
        raise ValueError(f"No download info for version {ver_id!r}")
    expected_sha1 = client_info.get("sha1")

    ver_dir = os.path.join(VERSION_DIR, ver_id)
    jar_path = os.path.join(ver_dir, f"{ver_id}.jar")

    # check for existing file and return if SHA1 matches
    if os.path.isfile(jar_path) and expected_sha1:
        with open(jar_path, "rb") as f:
            sha1 = hashlib.sha1(f.read()).hexdigest()
        if sha1 == expected_sha1:
            log.debug(
                "Skipping download for '%s.jar' since it already exists.",
                ver_id,
            )
            return jar_path
        else:
            log.warning(
                "'%s.jar' SHA1 doesn't match expected: %r != %r",
                ver_id,
                sha1,
                str(expected_sha1),
            )
    elif os.path.isfile(jar_path) and not redownload_option:
        log.info(
            "Skipping download for '%s.jar' since it exists and option is"
            "to not redownload",
            ver_id,
        )
        return jar_path

    url = client_info["url"]
    total_size = client_info.get("size", 0)
    log.info("Downloading client JAR for %r (%d bytes)", ver_id, total_size)

    os.makedirs(ver_dir, exist_ok=True)

    resp = SESSION.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    downloaded = 0
    sha1 = hashlib.sha1()
    with open(jar_path, "wb") as fb:
        for chunk in resp.iter_content(chunk_size=None):
            fb.write(chunk)
            sha1.update(chunk)
            if progress_callback:
                downloaded += len(chunk)
                progress_callback(downloaded, total_size)

    sha1_final = sha1.hexdigest()
    if expected_sha1 and sha1_final != expected_sha1:
        log.warning("SHA1 mismatch, deleting JAR.")
        os.unlink(jar_path)
        err = RuntimeError("SHA1 mismatch for client JAR")
        err.add_note(f"Expected {expected_sha1!r}, got {sha1_final!r}")
        raise err

    return jar_path


def check_client_jar(version_json: dict):
    """
    Checks if the client jar is installed or not.

    Returns `True` if the client JAR is installed.
    """
    ver_id: str = version_json["id"]
    client_info = get_client_jar_info(version_json)
    if not client_info:
        raise ValueError(f"No download info for version '{ver_id}'")
    expected_sha1: str | None = client_info.get("sha1")

    jar_path = os.path.join(VERSION_DIR, ver_id, f"{ver_id}.jar")

    if os.path.isfile(jar_path) and expected_sha1:
        with open(jar_path, "rb") as f:
            sha1 = hashlib.sha1(f.read()).hexdigest()
        return bool(sha1 == expected_sha1)
    elif os.path.isfile(jar_path):
        log.warning("Unable to check SHA1 for JAR at '%s'", str(jar_path))
        return True
    return False


def version_exists(id_: str):
    """
    Checks if a version exists in the Mojang manifest or locally

    Returns a bool
    """
    json_path = os.path.join(VERSION_DIR, id_, f"{id_}.json")
    if id_ in [a.get("id", "") for a in manifest_cache["versions"]]:
        return True
    elif os.path.exists(json_path):
        with open(json_path, "r") as f:
            txt = f.read()
        try:
            json.loads(txt)
        except json.JSONDecodeError as err:
            log.error(
                "Reading failed for bad JSON file at %r:",
                json_path,
                exc_info=err,
            )
            return False
        except Exception as err:
            log.error(
                "Unknown error occured reading JSON file at %r:",
                json_path,
                exc_info=err,
            )
        else:
            return True
    return False


def is_vanilla(id_: str):
    """
    Check if a version ID points towards a Mojang release, or a modded version
    locally installed.
    """
    if id_ in [a.get("id", "") for a in manifest_cache["versions"]]:
        return True
    return False


def check_fabric_mod_arg_support(version_id: str):
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


def default_user_jvm_args_factory(version_json: dict) -> str:
    if version_json["id"] in _args_cache:
        return _args_cache[version_json["id"]]
    args = version_json.get("arguments", {})
    if args.get("default-user-jvm", []):
        jvm_args = []
        for arg in args["default-user-jvm"]:
            if arg.get("rules", []):
                if not evaluate_rules(arg["rules"]):
                    continue
            match arg["value"]:
                case str():
                    jvm_args.append(arg["value"])
                case list():
                    for text in arg["value"]:
                        if text.startswith("-Xms"):
                            continue
                        elif text.startswith("-Xmx"):
                            continue
                        else:
                            jvm_args.append(text)
                case _:
                    raise TypeError(
                        "Expected list or str, "
                        f"got {type(arg["value"].__name__)}"
                    )
        # mojang is very interesting at making decisions regarding their
        # manifest files
        # if "-XX:UseZGC" in jvm_args and "-XX:UseG1GC" in jvm_args:
        #     i = jvm_args.index("-XX:UseG1GC")
        #     del jvm_args[i]
        _args_cache[version_json["id"]] = " ".join(jvm_args)
        return " ".join(jvm_args)
    return DEFAULT_JVM_ARGS
