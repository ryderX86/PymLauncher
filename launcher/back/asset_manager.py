"""
minecraftlauncher.back.asset_manager

Handles downloading the asset index and individual asset objects
for a given Minecraft version.
"""

from collections.abc import Callable
from xml.etree import ElementTree
from xml.parsers import expat
import hashlib
import logging
import os

from PySide6.QtCore import QThreadPool

from launcher.back.download_helpers import (
    BulkDownloadError,
    RunnableDownloader,
)
from launcher.constants import (
    RESOURCES_URL,
)
from launcher.datatypes.game_version import (
    AssetIndex,
)
from launcher.exceptions.back import (
    AssetDownloadError,
    Log4JConfigReadError,
)
from launcher.networking import make_request
from launcher.paths import paths

log = logging.getLogger(__name__)


def patch_logging_config(filepath: str | os.PathLike):
    if not isinstance(filepath, str):
        filepath = str(filepath)
    # raw string isn't particularly necessary here probably
    PATTERN = r"[%d{HH:mm:ss}] [%t/%level]: %msg{nolookups}%n"
    with open(filepath, "r") as f:
        txt = f.read()
    try:
        xml = ElementTree.fromstring(txt)
    except expat.error as err:
        log.error("Failed to parse XML from %r:", filepath, exc_info=err)
        raise Log4JConfigReadError(filepath, err.lineno, err.offset) from err
    # find all tags that will output XML in any form
    layout_elements = [*xml.iter("XMLLayout"), *xml.iter("LegacyXMLLayout")]
    if not layout_elements:
        log.debug("No XMLLayout elements in logging config, skipping patch")
        return filepath
    for c in layout_elements:
        c.clear()

        # <PatternLayout pattern="..." />
        c.tag = "PatternLayout"
        c.set("pattern", PATTERN)
    log.debug("Patched %r with non-XML config", os.path.split(filepath)[1])
    stem, suffix = os.path.splitext(filepath)
    new_path = f"{stem}_patched{suffix}"
    with open(new_path, "wb") as fb:
        fb.write(ElementTree.tostring(xml))
    return new_path


def check_or_download_logging_config(version_json: dict) -> str | None:
    """
    Check for the client logging info and if it doesn't exist, download it.

    Returns the complete argument to add to the JVM args if there's a logging
    config for the client, or `None` otherwise.

    Also tries to patch the config to not use XML layouts
    """
    logging_info: dict = version_json.get("logging", {}).get("client", {})
    # older versions didn't have logging stuff:
    if not logging_info:
        return None

    arg: str = logging_info.get(
        "argument", "-Dlog4j.configurationFile=${path}"
    )
    if "file" not in logging_info:
        log.warning("No 'file' key in logging config, considering it invalid.")
        return None
    file_info: dict = logging_info["file"]

    # check essential keys
    # TODO: check function uses to see if we need to raise AssetDownloadError
    id_: str = file_info.get("id", "")
    sha1: str = file_info.get("sha1", "")
    url: str = file_info.get("url", "")
    if not all((id_, sha1, url)):
        log.warning("Invalid logging config details")
        return None

    dest_folder = os.path.join(paths.assets, "log_configs")
    if not os.path.isdir(dest_folder):
        os.makedirs(dest_folder, exist_ok=True)

    dest_path = os.path.join(dest_folder, id_)
    stem, suffix = os.path.splitext(dest_path)
    dest_path_patched = f"{stem}_patched{suffix}"

    if os.path.isfile(dest_path):
        with open(dest_path, "rb") as fb:
            f_sha1 = hashlib.file_digest(fb, "sha1")
        if f_sha1 != sha1:
            log.warning(
                "Logging config %r has a mismatched SHA, redownloading", id_
            )
            os.unlink(dest_path)
            if os.path.isfile(dest_path_patched):
                log.debug(
                    "Also unlinking patch file for logging config %r", id_
                )
                os.unlink(dest_path_patched)
    else:
        log.info("Downloading logging config %r", id_)
    if not os.path.isfile(dest_path):
        try:
            resp = make_request("get", url)
        except Exception as err:
            log.error(
                "Failed to download logging config from %r:", url, exc_info=err
            )
            raise AssetDownloadError(url) from err
        else:
            with open(dest_path, "wb") as file:
                file.write(resp.data)

    if not os.path.isfile(dest_path_patched):
        final_logging_path = patch_logging_config(dest_path)
        return arg.replace("${path}", final_logging_path)
    else:
        return arg.replace("${path}", dest_path_patched)


def get_assets_download_list(
    asset_index: dict,
    progress_callback: Callable | None = None,
) -> list[RunnableDownloader]:
    objects: dict = asset_index.get("objects", {})
    dl_count = len(objects.keys())
    dl_list: list[RunnableDownloader] = []

    # def the callback function
    if progress_callback:
        processed = 0

        def add_number(i: int):
            nonlocal processed, dl_list, dl_count
            processed += i
            progress_callback(processed, dl_count)

        progress_callback(0, dl_count)

    else:

        def add_number(i: int):
            pass

    map_virtual_assets: bool = asset_index.get("map_to_resources", False)
    for virtual_path, info in objects.items():
        file_hash = info["hash"]
        prefix = file_hash[:2]
        dest_dir = os.path.join(paths.assets_objects, prefix)
        dest_path = os.path.join(dest_dir, file_hash)
        downloader = RunnableDownloader(
            url=f"{RESOURCES_URL}/{prefix}/{file_hash}",
            path=dest_path,
            vpath=(
                os.path.join(paths.assets_virtual, virtual_path)
                if map_virtual_assets
                else None
            ),
            sha1=file_hash,
            callback=add_number,
        )
        dl_list.append(downloader)
    # if progress_callback:
    #     final_dl_list = BulkDownloadWorker.auto_split(
    #         download_list,
    #         lambda i: processed.__setitem__("v", processed["v"] + i),
    #         lambda: progress_callback(processed["v"], total)
    #     )
    # else:
    #     final_dl_list = BulkDownloadWorker.auto_split(download_list)

    return dl_list


def download_assets(
    asset_index: AssetIndex,
    *,
    progress_callback: Callable | None = None,
    threaded: bool = True,
) -> int:
    # check pool before anything
    pool = QThreadPool.globalInstance()
    if not pool:
        log.warning(
            "Couldn't get thread pool, downloading single-threaded instead."
        )
        threaded = False
    dl_list = set()

    # start downloads
    if threaded:
        for worker in asset_index.iter_downloaders(progress_callback):
            dl_list.add(worker)
            pool.start(worker)
        timedout = not pool.waitForDone(900000)  # 15 min
        if timedout:
            raise AssetDownloadError("Downloads timed out completely")
        elif any(not a.success for a in dl_list):
            raise BulkDownloadError.from_runnable_list(dl_list)
    else:
        for worker in dl_list:
            worker.run()
    log.debug("Asset downloads complete")
    return len(dl_list)


def is_virtual_asset(asset_index: dict):
    """Returns `True` if the asset index uses the `virtual` layout."""
    return asset_index.get("virtual", False)


def is_resource_mapped(asset_index: dict):
    """Returns `True` if the asset index uses the legacy `resources` dir."""
    return asset_index.get("map_to_resources", False)
