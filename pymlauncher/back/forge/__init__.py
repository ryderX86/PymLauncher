from functools import lru_cache
from typing import Any
from xml.etree import ElementTree
import json
import logging

from pymlauncher.back.download_helpers import (
    download,
    file_exists_or_age,
    should_download_file,
)
from pymlauncher.constants import LAUNCHER_DATA_DIR, MINECRAFT_DIR

log = logging.getLogger(__name__)

VERSION_LIST_URL = (
    "https://maven.minecraftforge.net/net/minecraftforge/forge"
    "/maven-metadata.xml"
)
VERSION_LIST_RECOMMENDED = (
    "https://files.minecraftforge.net/net/minecraftfor"
    "ge/forge/promotions_slim.json"
)

_DOWNLOAD_BASE = "https://maven.minecraftforge.net/net/minecraftforge"

LOADER_MANIFEST_PATH = LAUNCHER_DATA_DIR / "forge-versions.json"

_master_manifest: dict[str, list[str]] = {}


def download_url(forge_ver: str):
    return "/".join(
        [_DOWNLOAD_BASE, forge_ver, f"forge-{forge_ver}-installer.jar"]
    )


def version_xml_to_json(version_list: ElementTree.Element | str):
    if isinstance(version_list, str):
        version_list = ElementTree.fromstring(version_list)
    versioning = version_list.find("versioning")
    if versioning is None:
        raise RuntimeError(
            "Couldn't get version info from %s" % VERSION_LIST_URL
        )

    versions = versioning.find("versions")
    if versions is None:
        raise RuntimeError(
            "Couldn't get version list from %s" % VERSION_LIST_URL
        )

    forge_versions: list[str] = []
    for el in versions.iter():
        if not el.text:
            continue
        forge_versions.append(el.text)

    json_out: dict[str, list[str]] = {}
    for version in forge_versions:
        v_info = version.split("-")
        mc_ver = v_info[0]
        if mc_ver not in json_out:
            json_out[mc_ver] = []
        f_ver = "-".join(v_info[1:])
        json_out[mc_ver].append(f_ver)
    return json_out


@lru_cache(maxsize=1)
def get_master(override: bool = False):
    global _master_manifest
    if _master_manifest and not override:
        return _master_manifest
    elif LOADER_MANIFEST_PATH.exists() and not override:
        manifest_text = LOADER_MANIFEST_PATH.read_text()
        try:
            manifest = json.loads(manifest_text)
        except json.JSONDecodeError as err:
            log.warning(
                "Couldn't read JSON at '%s', re-downloading",
                LOADER_MANIFEST_PATH,
                exc_info=err,
            )
        else:
            _master_manifest = manifest
            return _master_manifest
    log.info("Downloading Forge metadata from %s", VERSION_LIST_URL)
    try:
        resp = download(VERSION_LIST_URL)
    except:
        log.error("Couldn't download Forge metadata, giving up")
        return _master_manifest
    try:
        mf = version_xml_to_json(resp.text)
    except:
        log.error("Failed parsing Forge metadata (XML), giving up")
    else:
        _master_manifest = mf
    return _master_manifest


def forge_versions_list(version: str):
    get_master()
    return _master_manifest.get(version, [])


def game_versions_list():
    get_master()
    return [*_master_manifest.keys()]
