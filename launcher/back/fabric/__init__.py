import json
import logging
import os

from launcher.back.download_helpers import (
    download,
    file_exists_or_age,
)
from launcher.functions.text import indent
from launcher.paths import paths

log = logging.getLogger(__name__)

BASE_URL = "https://meta.fabricmc.net"
FABRIC_MANIFEST_URL = "https://meta.fabricmc.net/v2/versions"
FAB_LOAD_MF_URL = "https://meta.fabricmc.net/v2/versions/loader/%s"

_master_manifest = {}

game_versions_list: list[tuple[str, bool]] = []
loader_versions_list: list[str] = []


def _ensure_master(force_refresh: bool = False):
    global _master_manifest
    if force_refresh or not _master_manifest:
        log.debug("Loading Fabric manifest...")
        if (
            file_exists_or_age(
                os.path.join(paths.data, "fabric-versions.json")
            )
            and not force_refresh
        ):
            with open(
                os.path.join(paths.data, "fabric-versions.json"), "r"
            ) as f:
                manifest_cache_text = f.read()
            try:
                _manifest_cache = json.loads(manifest_cache_text)
            except json.JSONDecodeError:
                log.warning(
                    "Failed to read fabric-manifest.json from disk, "
                    "downloading new..."
                )
                _manifest_cache = {}
                del manifest_cache_text
            else:
                _master_manifest = _manifest_cache
                log.info("Using cached fabric-versions.json")
                return True
        log.info("Downloading Fabric manifest...")
        response = download(FABRIC_MANIFEST_URL)
        _master_manifest = response.json()
        del _master_manifest["mappings"]
        del _master_manifest["intermediary"]
        del _master_manifest["installer"]
        if not _master_manifest:
            raise RuntimeError(
                "Couldn't get game versions manifest for Fabric"
            )
        with open(os.path.join(paths.data, "fabric-versions.json"), "w") as f:
            f.write(response.text)
    return True


def get_game_versions_list(force_refresh: bool = False):
    global game_versions_list
    _ensure_master()

    if game_versions_list and not force_refresh:
        return game_versions_list

    log.debug("Building game version list for Fabric")

    new_list: list[tuple[str, bool]] = []

    for v_dict in _master_manifest.get("game", []):
        version_id = v_dict.get("version", "")
        if not version_id:
            log.warning(
                "Couldn't get ID for JSON object: %s", json.dumps(v_dict)
            )
        new_list.append((version_id, v_dict.get("stable", False)))

    if not new_list:
        raise RuntimeError(
            "Couldn't get supported game version list from manifest"
        )

    game_versions_list = new_list
    return game_versions_list


def get_loader_versions_list(force_refresh: bool = False):
    global loader_versions_list
    _ensure_master()

    if loader_versions_list and not force_refresh:
        return loader_versions_list

    log.debug("Building loader versions list for Fabric")

    new_list: list[str] = []

    for v_dict in _master_manifest.get("loader", []):
        new_list.append(v_dict.get("version", ""))

    loader_versions_list = new_list
    return loader_versions_list


# maybe TODO(?): insert 'jar' into the version JSON?
def install(game_ver: str, fabric_ver: str, override: bool = False):
    _ensure_master()
    log.debug("fabric-loader-%s-%s install requested", fabric_ver, game_ver)
    URL = (
        "https://meta.fabricmc.net/v2/versions/loader/"
        f"{game_ver}/{fabric_ver}/profile/json"
    )

    log.debug("Download: %s", URL)

    dir_ = os.path.join(
        paths.game, "versions", f"fabric-loader{fabric_ver}-{game_ver}"
    )
    path = os.path.join(dir_, f"fabric-loader-{fabric_ver}-{game_ver}.json")

    if not os.path.isdir(dir_):
        os.makedirs(dir_, exist_ok=True)
    if os.path.isdir(path) and not override:
        log.warning(
            "'fabric-loader-%s-%s' exists already!", fabric_ver, game_ver
        )
        raise FileExistsError(str(path))

    log.info("Installing fabric-loader-%s-%s", fabric_ver, game_ver)
    response = download(URL)
    # check JSON data:
    try:
        json.loads(response.text)
    except json.JSONDecodeError as err:
        new = RuntimeError("Server returned malformed JSON data:")
        new.add_note("".join(['"', indent(response.text), '"']))
        raise new from err
    with open(path, "w") as file:
        file.write(response.text)
    return True
