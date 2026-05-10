"""
minecraftlauncher.back.asset_manager

Handles downloading the asset index and individual asset objects
for a given Minecraft version.
"""

from datetime import datetime, timedelta
from collections.abc import Callable
from xml.etree import ElementTree
import logging
import hashlib
import json
import os

import requests
from PySide6.QtCore import QThreadPool

from minecraftlauncher.constants import (
    RESOURCES_URL,
    MINECRAFT_DIR,
    CPU_THREADS,
)
from minecraftlauncher.back.download_helpers import (
    download,
    RunnableDownloader,
    BulkDownloadError,
)
from minecraftlauncher import session

log = logging.getLogger(__name__)

ASSETS_DIR = os.path.join(MINECRAFT_DIR, "assets")
ASSETS_INDEX_DIR = os.path.join(ASSETS_DIR, "indexes")
VIRTUAL_BASE = os.path.join(ASSETS_DIR, "virtual", "legacy")
OBJECTS_DIR = os.path.join(ASSETS_DIR, "objects")

if not os.path.isdir(ASSETS_DIR):
    os.makedirs(ASSETS_DIR, exist_ok=True)
if not os.path.isdir(ASSETS_INDEX_DIR):
    os.makedirs(ASSETS_INDEX_DIR, exist_ok=True)
if not os.path.isdir(VIRTUAL_BASE):
    os.makedirs(VIRTUAL_BASE, exist_ok=True)
if not os.path.isdir(OBJECTS_DIR):
    os.makedirs(OBJECTS_DIR, exist_ok=True)


def fetch_asset_index(version_json: dict) -> dict:
    """
    Download (or load cached) the asset index for the given version.

    Returns the parsed asset index dict, which has an ``objects`` key
    mapping virtual paths to ``{hash, size}`` dicts.
    """
    asset_index_info = version_json.get("assetIndex")
    if asset_index_info is None:
        raise ValueError("Version JSON has no 'assetIndex' field")

    index_id = asset_index_info["id"]
    index_url = asset_index_info["url"]
    expected_sha1 = asset_index_info.get("sha1")

    index_path = os.path.join(ASSETS_INDEX_DIR, f"{index_id}.json")

    if os.path.isfile(index_path):
        if isinstance(expected_sha1, str):
            # using SHA1 to verify file
            with open(index_path, "rb") as fb:
                file_sha = hashlib.sha1(fb.read()).hexdigest()
            if file_sha == expected_sha1:
                log.debug("Using cached asset index '%s'", str(index_id))
                with open(index_path, "r") as f:
                    try:
                        return json.loads(f.read())
                    except json.JSONDecodeError as err:
                        log.error(
                            "Failed reading invalid JSON at %r:",
                            index_path,
                            exc_info=err,
                        )
        else:
            # using file timestamp to verify
            file_time = os.stat(index_path).st_mtime
            compare_time = (datetime.now() - timedelta(days=1)).timestamp()
            if compare_time < file_time:
                log.debug(
                    "Using cached asset index '%s' (time-based)", str(index_id)
                )
                with open(index_path, "r") as f:
                    txt = f.read()
                try:
                    return json.loads(txt)
                except json.JSONDecodeError as err:
                    log.error(
                        "Failed reading invalid JSON at %r:",
                        index_path,
                        exc_info=err,
                    )

    # download the index and return it
    log.info("Downloading asset index '%s' from '%s'", str(index_id), index_url)
    resp = session.get(index_url, timeout=30)
    resp.raise_for_status()

    with open(index_path, "w") as f:
        f.write(resp.text)

    return resp.json()


def patch_logging_config(path: str | os.PathLike):
    if not isinstance(path, str):
        path = str(path)
    PATTERN = r"[%d{HH:mm:ss}] [%t/%level]: %msg{nolookups}%n"
    with open(path, "r") as f:
        txt = f.read()
    xml = ElementTree.fromstring(txt)
    patched = False
    elements = [*xml.iter("XMLLayout"), *xml.iter("LegacyXMLLayout")]
    for c in elements:
        c.clear()
        c.tag = "PatternLayout"
        c.set("pattern", PATTERN)
        patched = True
    if patched:
        log.debug("Patched '%r' with non-XML config", os.path.split(path)[1])
        stem, suffix = os.path.splitext(path)
        new_path = f"{stem}_patched{suffix}"
        with open(new_path, "wb") as fb:
            fb.write(ElementTree.tostring(xml))
        return new_path
    else:
        log.warning("Couldn't patch logging config")
    return path


def check_or_download_logging_config(version_json: dict) -> str:
    """
    Check for the client logging info and if it doesn't exist, download it.

    Returns the complete argument to add to the JVM args if there's a logging
    config for the client, or a blank str otherwise.

    Also tries to patch the config to not use XML layouts
    """
    logging_info: dict = version_json.get("logging", {}).get("client", {})
    # older versions didn't have logging stuff:
    if not logging_info:
        return ""

    arg: str = logging_info.get("argument", "-Dlog4j.configurationFile=${path}")
    file_info: dict = logging_info.get("file", {})
    if not file_info:
        raise ValueError("Expected key 'file' in version_json['logging']")
    name: str = file_info["id"]
    sha1: str = file_info.get("sha1", "")
    url: str = file_info["url"]

    dest_folder = os.path.join(ASSETS_DIR, "log_configs")
    if not os.path.isdir(dest_folder):
        os.makedirs(dest_folder, exist_ok=True)

    dest_path = os.path.join(dest_folder, name)
    stem, suffix = os.path.splitext(dest_path)
    dest_path_patched = f"{stem}_patched{suffix}"

    if os.path.isfile(dest_path):
        with open(dest_path, "rb") as fb:
            f_sha1 = hashlib.sha1(fb.read()).hexdigest()
        if f_sha1 != sha1:
            os.unlink(dest_path)
    if not os.path.isfile(dest_path):
        try:
            resp = download(url, sha=sha1)
            with open(dest_path, "wb") as fb:
                fb.write(resp.content)
        except Exception as err:
            log.error("Failed to download logging config:", exc_info=err)
            raise

    if not os.path.isfile(dest_path_patched):
        path = patch_logging_config(dest_path)
        return arg.replace("${path}", path)
    else:
        return arg.replace("${path}", dest_path_patched)


def filter_assets_downloads(
    asset_index: dict,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
):
    """
    Filters the given asset index by removing files that are already
    downloaded.
    """
    objects: dict = asset_index.get("objects", {})
    asset_index_out = {**asset_index}
    asset_index_out["objects"] = {}
    total = len(objects.keys())
    map_virtual_assets: bool = asset_index.get("map_to_resources", False)
    if map_virtual_assets:
        total *= 2

    if progress_callback:
        progress_callback(0, total)

    processed = 0
    for virtual_path, info in objects.items():
        file_hash = info["hash"]
        prefix = file_hash[:2]
        dest_dir = os.path.join(OBJECTS_DIR, prefix)
        dest_path = os.path.join(dest_dir, file_hash)

        dest_path_v = os.path.join(VIRTUAL_BASE, virtual_path)
        if os.path.isfile(dest_path):
            with open(dest_path, "rb") as fb:
                file_sha1 = hashlib.sha1(fb.read()).hexdigest()
            if file_sha1 != file_hash:
                asset_index_out["objects"][virtual_path] = info
        else:
            asset_index_out["objects"][virtual_path] = info
        processed += 1
        if progress_callback:
            progress_callback(processed, total)

        if map_virtual_assets:
            if os.path.isfile(dest_path_v):
                with open(dest_path_v, "rb") as fb:
                    file_sha1 = hashlib.sha1(fb.read()).hexdigest()
                if file_sha1 != file_hash:
                    if virtual_path not in asset_index_out["objects"]:
                        asset_index_out["objects"][virtual_path] = info
            else:
                if virtual_path not in asset_index_out["objects"]:
                    asset_index_out["objects"][virtual_path] = info
            processed += 1
            if progress_callback:
                progress_callback(processed, total)

    return asset_index_out


def download_assets(
    asset_index: dict, *, progress_callback: Callable | None = None
):
    objects: dict = asset_index.get("objects", {})
    total = len(objects.keys())

    downloaded_count = 0
    processed = 0

    for virtual_path, info in objects.items():
        file_hash: str = info["hash"]
        prefix = file_hash[:2]

        dest_dir = os.path.join(OBJECTS_DIR, "prefix")
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, file_hash)

        if os.path.isfile(dest_path):
            with open(dest_path, "rb") as fb:
                existing_hash = hashlib.sha1(fb.read()).hexdigest()
            if existing_hash == file_hash:
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)
                continue
            else:
                log.debug(
                    "Overriding asset '%s' (SHA1 didn't match)", file_hash
                )

        url = f"{RESOURCES_URL}/{prefix}/{file_hash}"
        try:
            resp = download(url, sha=file_hash)
        except requests.RequestException as err:
            log.warning(
                "Failed to download asset %s:", virtual_path, exc_info=err
            )
            processed += 1
            if progress_callback:
                progress_callback(processed, total)
            continue

        with open(dest_path, "wb") as fb:
            fb.write(resp.content)
        log.debug("Downloaded '%s' successfully.", virtual_path)
        processed += 1
        downloaded_count += 1
        if progress_callback:
            progress_callback(processed, total)
        continue

    log.debug(
        "Asset download complete: %d new / %d total", downloaded_count, total
    )
    return downloaded_count


def download_assets_threaded(
    asset_index: dict, *, progress_callback: Callable | None = None
):
    # check pool before anything
    pool = QThreadPool.globalInstance()
    if not pool:
        log.warning(
            "Couldn't get thread pool, downloading single-threaded instead."
        )
        return download_assets(asset_index, progress_callback=progress_callback)

    objects: dict = asset_index.get("objects", {})
    total = len(objects.keys())

    if progress_callback:

        def add_number(i: int):
            nonlocal processed, download_list, total
            processed += i
            progress_callback(processed, total)

    else:

        def add_number(i: int):
            pass

    download_list: list[RunnableDownloader] = []
    processed = 0

    map_virtual_assets: bool = asset_index.get("map_to_resources", False)
    if map_virtual_assets:
        total *= 2
    for virtual_path, info in objects.items():
        file_hash = info["hash"]
        prefix = file_hash[:2]
        dest_dir = os.path.join(OBJECTS_DIR, prefix)
        dest_path = os.path.join(dest_dir, file_hash)
        downloader = RunnableDownloader(
            f"{RESOURCES_URL}/{prefix}/{file_hash}",
            dest_path,
            file_hash,
            callback=add_number,
        )
        if map_virtual_assets:
            v_downloader = RunnableDownloader(
                f"{RESOURCES_URL}/{prefix}/{file_hash}",
                os.path.join(VIRTUAL_BASE, virtual_path),
                file_hash,
                callback=add_number,
            )
            download_list.append(v_downloader)
        download_list.append(downloader)
    if not download_list:
        return 0
    # if progress_callback:
    #     final_dl_list = BulkDownloadWorker.auto_split(
    #         download_list,
    #         lambda i: processed.__setitem__("v", processed["v"] + i),
    #         lambda: progress_callback(processed["v"], total)
    #     )
    # else:
    #     final_dl_list = BulkDownloadWorker.auto_split(download_list)
    if progress_callback:
        progress_callback(0, total)
    pool.setMaxThreadCount(CPU_THREADS)
    for worker in download_list:
        pool.start(worker)
    timedout = not pool.waitForDone(900000)  # 15 min
    if timedout:
        raise RuntimeError("Downloads timed out completely")
    elif any(not a.success for a in download_list):
        raise BulkDownloadError.from_runnable_list(download_list)
    log.debug("Asset downloads complete")
    return len(download_list)


def is_virtual_asset(asset_index: dict):
    """Returns `True` if the asset index uses the `virtual` layout."""
    return asset_index.get("virtual", False)


def is_resource_mapped(asset_index: dict):
    """Returns `True` if the asset index uses the legacy `resources` dir."""
    return asset_index.get("map_to_resources", False)
