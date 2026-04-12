from typing import Any
from functools import lru_cache
from zipfile import ZipFile
import logging
import json
import xml

from minecraftlauncher.constants import LAUNCHER_DATA_DIR, MINECRAFT_DIR
from minecraftlauncher.back.download_manager import (
    download, should_download_file, file_exists_or_age
)
from minecraftlauncher.functions.text import indent

FALLBACK_DOMAIN = "maven.creeperhost.net"

VERSION_MANIFEST_URL = ("https://maven.neoforged.net/api/maven/versions/"
                        "releases/net/neoforged/neoforge")
"""
Version manifest in JSON format. When looking for a game version <26.1, always
take the "1." out of the version (i.e. "1.21.2" becomes "21.2"), then look for
any IDs starting with that number.
"""
LEGACY_VERSIONS_MANIFEST = "https://maven.neoforged.net/api/maven/versions/" \
                           "releases/net/neoforged/forge"

DOWNLOAD_URL = "https://maven.neoforged.net/releases/net/neoforged/neoforge/" \
               "VERSION/neoforge-VERSION-installer.jar"
"""
change "installer" to "universal" if there actually is a way to get the version
JSON from the API, but until then, open the installer JAR as ZIP, manifest JSON
will be at `/version.json` and the client will be LZMA compressed at
`/data/client.lzma`
"""
LEGACY_DOWNLOAD_URL = "https://maven.neoforged.net/releases/net/neoforged/forge/" \
                      "VERSION/neoforge-VERSION-installer.jar"

log = logging.getLogger(__name__)

_versions_list:dict[str, str] = {}

@lru_cache(maxsize=1)
def get_master(force_refresh:bool=False):
    global _versions_list
    if _versions_list and not force_refresh:
        return _versions_list
    log.debug("Grabbing NeoForge version manifest")
    _versions_list = {}
    response = download(VERSION_MANIFEST_URL)
    versions:list[str] = response.json().get("versions", [])
    if not versions:
        err = RuntimeError("Couldn't get version list")
        err.add_note("Original response:\n%s"
                     % indent(json.dumps(response.json(), indent=2)))
        raise err
    # versions go from oldest>newest
    versions.reverse()
    for v in versions:
        full_id = v.split("-")
        id_ = full_id[0]
        if id_[:1].isdecimal():
            ids = id_.split(".")
            if int(id_[:1]) >= 26:
                if ids[2] != "0":
                    len_ = 2
                else:
                    len_= 1
                id_ = ".".join(ids[:len_])
            else:
                id_ = "1." + ".".join(ids[:1])
        elif id_[1] == ".":
            continue # april fools version
        else:
            log.warning("Unknown version type: %s" % v)
            continue
        _versions_list[id_] = v
    
    # legacy version list
    response = download(LEGACY_VERSIONS_MANIFEST)
    versions:list[str] = response.json().get("versions", [])
    if not versions:
        log.warning("Legacy versions list is empty!")
        return _versions_list

    for v in versions:
        full_id = v.split("-")
        if len(full_id) != 2:
            log.warning("Unexpected amount of dashes in version '%s'!" % v)
            continue
        id_ = full_id[0]
        neo = full_id[1]
        if id_[0] != "1":
            # unfortunately i have no idea what mc version 47.1.82 is for
            continue
        _versions_list[id_] = neo
    return _versions_list

@lru_cache(maxsize=1)
def get_minecraft_versions():
    log.debug("Sort Minecraft versions")
    return [*get_master().keys()]

@lru_cache(maxsize=4)
def get_neoforge_versions(mc_id:str):
    versions = []
    for mc, neo in get_master().items():
        if mc != mc_id:
            continue
        versions.append(neo)
    return versions

def install(neoforge_version:str, override=False):
    log.debug("Install requested for neoforge-%s" % neoforge_version)
    if neoforge_version not in get_master():
        if neoforge_version not in get_master(True):
            raise RuntimeError("Couldn't find NeoForge version %s"
                               % neoforge_version)
    
    if neoforge_version[0:1] != "1.":
        url = DOWNLOAD_URL.replace("VERSION", neoforge_version)
    else:
        url = LEGACY_DOWNLOAD_URL.replace("VERSION", neoforge_version)
    
    