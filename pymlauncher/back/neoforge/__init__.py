from functools import lru_cache
from io import BytesIO
from zipfile import ZipFile
import json
import logging
import os

from pymlauncher.back.download_helpers import download
from pymlauncher.functions.text import indent
from pymlauncher.paths import paths

FALLBACK_DOMAIN = "maven.creeperhost.net"

VERSION_MANIFEST_URL = (
    "https://maven.neoforged.net/api/maven/versions/"
    "releases/net/neoforged/neoforge"
)
"""
Version manifest in JSON format. When looking for a game version <26.1, always
take the "1." out of the version (i.e. "1.21.2" becomes "21.2"), then look for
any IDs starting with that number.
"""
LEGACY_VERSIONS_MANIFEST = (
    "https://maven.neoforged.net/api/maven/versions/"
    "releases/net/neoforged/forge"
)

DOWNLOAD_URL = (
    "https://maven.neoforged.net/releases/net/neoforged/neoforge/"
    "VERSION/neoforge-VERSION-installer.jar"
)
"""
change "installer" to "universal" if there actually is a way to get the version
JSON from the API, but until then, open the installer JAR as ZIP, manifest JSON
will be at `/version.json` and the client will be LZMA compressed at
`/data/client.lzma`
"""
LEGACY_DOWNLOAD_URL = (
    "https://maven.neoforged.net/releases/net/neoforged/forge/"
    "VERSION/forge-VERSION-installer.jar"
)

log = logging.getLogger(__name__)

_versions_list: dict[str, list] = {}


@lru_cache(maxsize=1)
def get_master(force_refresh: bool = False):
    global _versions_list
    if _versions_list and not force_refresh:
        return _versions_list
    elif (
        os.path.isfile(os.path.join(paths.data, "neoforge-versions.json"))
        and not force_refresh
    ):
        with open(
            os.path.join(paths.data, "neoforge-versions.json"), "r"
        ) as file:
            manifest_text = file.read()
        try:
            manifest = json.loads(manifest_text)
        except json.JSONDecodeError as err:
            log.error(
                "Failed to read neoforge-versions.json, redownloading...\n",
                exc_info=err,
            )
            os.unlink(os.path.join(paths.data, "neoforge-versions.json"))
        else:
            _versions_list = manifest
        finally:
            del manifest_text
    log.debug("Grabbing NeoForge version manifest")
    _versions_list = {}
    response = download(VERSION_MANIFEST_URL)
    versions: list[str] = response.json().get("versions", [])
    if not versions:
        err = RuntimeError("Couldn't get version list")
        err.add_note(
            "Original response:\n"
            f"{indent(json.dumps(response.json(), indent=2))}"
        )
        raise err
    # versions go from oldest>newest
    versions.reverse()
    for v in versions:
        full_id = v.split("-")
        id_ = full_id[0]
        if id_[:2].isdecimal():
            ids = id_.split(".")
            if int(id_[:2]) >= 26:
                id_ = ".".join(ids[:3])
            else:
                id_ = ".".join(["1", *ids[:2]])
        elif id_[1] == ".":
            log.debug("Skipping NeoForge version %s", v)
            continue  # april fools version
        else:
            log.warning("Unknown version type: %s", v)
            continue
        if id_ not in _versions_list:
            _versions_list[id_] = []
        _versions_list[id_].append(v)

    # legacy version list
    response = download(LEGACY_VERSIONS_MANIFEST)
    versions: list[str] = response.json().get("versions", [])
    if not versions:
        log.warning("Legacy versions list is empty!")
        return _versions_list

    for v in versions:
        full_id = v.split("-")
        if len(full_id) != 2:
            log.warning("Unexpected amount of dashes in version '%s'!", v)
            continue
        id_ = full_id[0]
        neo = full_id[1]
        if id_[0] != "1":
            # unfortunately i have no idea what mc version 47.1.82 is for
            continue
        if id_ not in _versions_list:
            _versions_list[id_] = []
        _versions_list[id_].append(neo)

    log.info("Successfully fetched & parsed NeoForge versions, saving to disk")
    with open(os.path.join(paths.data, "neoforge-versions.json"), "w") as file:
        file.write(json.dumps(_versions_list))
    return _versions_list


@lru_cache(maxsize=1)
def get_minecraft_versions():
    log.debug("Sort Minecraft versions")
    return [*get_master().keys()]


@lru_cache(maxsize=4)
def filter_neoforge_versions(mc_id: str):
    if mc_id in _versions_list:
        return _versions_list[mc_id]
    return []


def get_neoforge_versions(override: bool = False):
    vers = []
    for ver_list in get_master(override).values():
        vers.extend(ver_list)
    return vers


def install(neoforge_version: str, override: bool = False):
    inf = neoforge_version.split("-")
    neoforge_version_id = "-".join([inf[0], "forge", inf[1]])
    if override:
        log.info("User requested re-install for neoforge-%s", neoforge_version)
    else:
        log.debug("Install requested for neoforge-%s", neoforge_version)

    if neoforge_version[0:2] != "1.":
        url = DOWNLOAD_URL.replace("VERSION", neoforge_version)
        dest_dir = os.path.join(paths.versions, f"neoforge-{neoforge_version}")
        dest_path = os.path.join(dest_dir, f"neoforge-{neoforge_version}.json")
    else:
        url = LEGACY_DOWNLOAD_URL.replace("VERSION", neoforge_version)
        dest_dir = os.path.join(paths.versions, neoforge_version_id)
        dest_path = os.path.join(dest_dir, f"{neoforge_version_id}.json")

    if os.path.isfile(dest_path) and not override:
        raise FileExistsError(str(dest_path))
    if neoforge_version not in get_neoforge_versions():
        if neoforge_version not in get_neoforge_versions(True):
            raise RuntimeError(
                f"Couldn't find NeoForge version {neoforge_version}"
            )

    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)

    resp = download(url)
    b = BytesIO(resp.content)

    with ZipFile(b) as zipf:
        with zipf.open("version.json") as json_file:
            try:
                json.load(json_file)  # lazy check validity
            except json.JSONDecodeError as err:
                err.add_note(
                    f"Couldn't read verison.json from '{neoforge_version_id}.zip'"
                )
                raise
            else:
                json_file.seek(0)
                with open(dest_path, "wb") as f:
                    f.write(json_file.read())

        # with zipf.open("data/client.lzma") as client:
        #     # TODO: reverse engineer fatjar
        #     pass

    log.info("Installed NeoForge version %s", neoforge_version_id)
    return True
