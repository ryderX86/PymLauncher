import logging
import json

from minecraftlauncher.constants import LAUNCHER_DATA_DIR, MINECRAFT_DIR
from minecraftlauncher.back.download_helpers import download, file_exists_or_age

log = logging.getLogger(__name__)

BASE_URL = "https://meta.fabricmc.net"
FABRIC_MANIFEST_URL = "https://meta.fabricmc.net/v2/versions"
FAB_LOAD_MF_URL = "https://meta.fabricmc.net/v2/versions/loader/%s"

LOADER_MANIFEST_PATH = LAUNCHER_DATA_DIR / "fabric-versions.json"

_master_manifest = {}

game_versions_list: list[tuple[str, bool]] = []
loader_versions_list: list[str] = []


def _get_master(force_refresh: bool = False):
    global _master_manifest
    if force_refresh or not _master_manifest:
        log.debug("Loading Fabric manifest...")
        if file_exists_or_age(LOADER_MANIFEST_PATH) and not force_refresh:
            cached = LOADER_MANIFEST_PATH.read_text()
            try:
                _master_manifest = json.loads(cached)
            except json.JSONDecodeError:
                log.warning(
                    "Failed to read fabric-manifest.json from disk, "
                    "downloading new..."
                )
                _master_manifest = {}
                del cached
            else:
                log.info("Using cached fabric-versions.json")
                return
        log.info("Downloading Fabric manifest...")
        response = download(FABRIC_MANIFEST_URL)
        _master_manifest = response.json()
        del _master_manifest["mappings"]
        del _master_manifest["intermediary"]
        del _master_manifest["installer"]
        if not _master_manifest:
            raise RuntimeError("Couldn't get game versions manifest for Fabric")
        LOADER_MANIFEST_PATH.write_text(response.text, "utf-8")
    return


def get_game_versions_list(force_refresh: bool = False):
    global game_versions_list
    _get_master()

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
    _get_master()

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
    _get_master()
    log.debug("fabric-loader-%s-%s install requested", fabric_ver, game_ver)
    URL = (
        "https://meta.fabricmc.net/v2/versions/loader/"
        f"{game_ver}/{fabric_ver}/profile/json"
    )

    log.debug("Download: %s", URL)

    dir_ = MINECRAFT_DIR / "versions" / f"fabric-loader-{fabric_ver}-{game_ver}"
    path = dir_ / f"fabric-loader-{fabric_ver}-{game_ver}.json"

    if not dir_.exists():
        dir_.mkdir(parents=True)
    if path.exists() and not override:
        log.warning(
            "'fabric-loader-%s-%s' exists already!", fabric_ver, game_ver
        )
        raise FileExistsError(str(path))

    log.info("Installing fabric-loader-%s-%s", fabric_ver, game_ver)
    response = download(URL)
    path.write_text(response.text)
    return True
