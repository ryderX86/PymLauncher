"""
minecraftlauncher.back.asset_manager

Handles downloading the asset index and individual asset objects
for a given Minecraft version.
"""
from datetime import datetime, timedelta
from typing import Callable
from time import sleep
import hashlib
import json
import logging
import os

import requests
from PySide6.QtCore import QThreadPool, QDeadlineTimer

from minecraftlauncher.constants import RESOURCES_URL, MINECRAFT_DIR
from minecraftlauncher.back.download_manager import (
    download, BulkDownloadSingleFile, BulkDownloadWorker
)

log = logging.getLogger(__name__)

ASSETS_DIR = MINECRAFT_DIR / "assets"
ASSETS_INDEX_DIR = ASSETS_DIR / "indexes"
VIRTUAL_BASE = ASSETS_DIR / "virtual" / "legacy"

if (not ASSETS_DIR.exists()) or (not ASSETS_DIR.is_dir()):
    ASSETS_DIR.mkdir(parents=True)
if (not ASSETS_INDEX_DIR.exists()) or (not ASSETS_INDEX_DIR.is_dir()):
    ASSETS_INDEX_DIR.mkdir(parents=True)

def fetch_asset_index(version_json:dict) -> dict:
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

    index_path = ASSETS_INDEX_DIR / f"{index_id}.json"

    if index_path.exists() and index_path.is_file():
        if isinstance(expected_sha1, str):
            # using SHA1 to verify file
            file_sha = hashlib.sha1(index_path.read_bytes()).hexdigest()
            if file_sha == expected_sha1:
                log.debug("Using cached asset index '%s'" % str(index_id))
                return json.loads(index_path.read_text())
        else:
            # using file timestamp to verify
            file_time = index_path.stat().st_mtime
            compare_time = (datetime.now() - timedelta(days=1)).timestamp()
            if compare_time < file_time:
                log.debug("Using cached asset index '%s' (time-based)"
                          % str(index_id))
                return json.loads(index_path.read_text())
    
    # download the index and return it
    log.info("Downloading asset index '%s' from '%s'"
             % (str(index_id), index_url))
    resp = requests.get(index_url, timeout=30)
    resp.raise_for_status()

    index_path.touch()
    index_path.write_text(resp.text)

    return resp.json()

def check_or_download_logging_config(version_json:dict) -> str:
    """
    Check for the client logging info and if it doesn't exist, download it.
    
    Returns the complete argument to add to the JVM args if there's a logging
    config for the client, or a blank str otherwise.
    """
    p = ("<PatternLayout pattern=\"[%d{HH:mm:ss}] [%t/%level]: "
         "%msg{nolookups}%n\"/>")
    logging_info:dict = version_json.get("logging", {}).get("client", {})
    # older versions didn't have logging stuff:
    if not logging_info:
        return ""
    
    arg:str = logging_info.get("argument", "-Dlog4j.configurationFile=${path}")
    file_info:dict = logging_info.get("file", {})
    if not file_info:
        raise ValueError("Expected key 'file' in version_json['logging']")
    name:str = file_info["id"]
    sha1:str = file_info.get("sha1", "")
    size:int = file_info["size"]
    url:str = file_info["url"]

    dest_folder = ASSETS_DIR / "log_configs"
    if not (dest_folder.exists() and dest_folder.is_dir()):
        dest_folder.mkdir(parents=True, exist_ok=True)

    dest_path = dest_folder / name
    dest_path_patched = dest_folder / (name[:-4] + "_patched.xml")
    output = arg.replace("${path}", str(dest_path_patched))

    if dest_path.exists() and dest_path.is_file():
        f_sha1 = hashlib.sha1(dest_path.read_bytes()).hexdigest()
        if f_sha1 == sha1:
            if not dest_path_patched.exists():
                dest_path_patched.write_text(dest_path.read_text().replace(
                    "<LegacyXMLLayout />", p
                ))
            return output

    try:
        resp = download(url, hash=sha1)
    except Exception as err:
        raise

    dest_path.write_bytes(resp.content)
    dest_path_patched.write_text(resp.text.replace("<LegacyXMLLayout />", p))
    return output

def filter_assets_downloads(asset_index:dict, *,
                            progress_callback:Callable[[int, int], None]|None=None):
    """
    Filters the given asset index by removing files that are already
    downloaded.
    """
    objects:dict = asset_index.get("objects", {})
    asset_index_out = {**asset_index}
    asset_index_out["objects"] = {}
    total = len(objects.keys())
    map_virtual_assets:bool = asset_index.get("map_to_resources", False)
    if map_virtual_assets:
        total *= 2
    
    objects_dir = ASSETS_DIR / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(0, total)

    processed = 0
    for virtual_path, info in objects.items():
        file_hash = info["hash"]
        prefix = file_hash[:2]
        dest_dir = objects_dir / prefix
        dest_path = dest_dir / file_hash
        
        dest_path_v = VIRTUAL_BASE / virtual_path
        if dest_path.exists() and dest_path.is_file():
            file_bytes = dest_path.read_bytes()
            file_sha1 = hashlib.sha1(file_bytes).hexdigest()
            if file_sha1 != file_hash:
                asset_index_out["objects"][virtual_path] = info
        else:
            asset_index_out["objects"][virtual_path] = info
        processed += 1
        if progress_callback:
            progress_callback(processed, total)
        
        if map_virtual_assets:
            if dest_path_v.exists() and dest_path_v.is_file():
                file_bytes = dest_path_v.read_bytes()
                file_sha1 = hashlib.sha1(file_bytes).hexdigest()
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

def download_assets(asset_index:dict, *,
                    progress_callback:Callable|None=None):
    objects:dict = asset_index.get("objects", {})
    total = len(objects.keys())

    objects_dir = ASSETS_DIR / "objects"
    if (not objects_dir.exists()) or (not objects_dir.is_dir()):
        objects_dir.mkdir(parents=True)
    
    downloaded_count = 0
    processed = 0

    for virtual_path, info in objects.items():
        file_hash:str = info["hash"]
        file_size = info.get("size", 0)
        prefix = file_hash[:2]

        dest_dir = objects_dir / "prefix"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / file_hash

        if dest_path.exists() and dest_path.is_file():
            existing_hash = hashlib.sha1(dest_path.read_bytes()).hexdigest()
            if existing_hash == file_hash:
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)
                continue
            else:
                log.debug("Overriding asset '%s' (SHA1 didn't match)"
                          % file_hash)

        url = f"{RESOURCES_URL}/{prefix}/{file_hash}"
        try:
            resp = download(url, hash=file_hash)
        except requests.RequestException as err:
            log.warning("Failed to download asset %s:" % virtual_path,
                        exc_info=err)
            processed += 1
            if progress_callback:
                progress_callback(processed, total)
            continue

        dest_path.write_bytes(resp.content)
        log.debug("Downloaded '%s' successfully." % virtual_path)
        processed += 1
        downloaded_count += 1
        if progress_callback:
            progress_callback(processed, total)
        continue

    log.debug("Asset download complete: %d new / %d total"
              % (downloaded_count, total))
    return downloaded_count

def download_assets_threaded(asset_index:dict, *,
                             progress_callback:Callable|None=None):
    # check pool before anything
    pool = QThreadPool.globalInstance()
    if not pool:
        log.warning("Couldn't get thread pool, downloading single-threaded "
                    "instead.")
        return download_assets(asset_index,
                               progress_callback=progress_callback)
    
    objects:dict = asset_index.get("objects", {})
    total = len(objects.keys())

    objects_dir = ASSETS_DIR / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)

    download_list:list[BulkDownloadSingleFile] = []
    # dumb stupid workaround lmfao
    processed = {"v": 0}

    map_virtual_assets:bool = asset_index.get("map_to_resources", False)
    if map_virtual_assets:
        total *= 2
    for virtual_path, info in objects.items():
        file_hash = info["hash"]
        prefix = file_hash[:2]
        dest_dir = objects_dir / prefix
        dest_path = dest_dir / file_hash
        downloader = BulkDownloadSingleFile(
            f"{RESOURCES_URL}/{prefix}/{file_hash}",
            dest_path,
            file_hash
        )
        if map_virtual_assets:
            v_downloader = BulkDownloadSingleFile(
                f"{RESOURCES_URL}/{prefix}/{file_hash}",
                VIRTUAL_BASE / virtual_path,
                file_hash
            )
            if v_downloader.needs_download:
                download_list.append(v_downloader)
            else:
                processed["v"] += 1
        if downloader.needs_download:
            download_list.append(downloader)
        else:
            processed["v"] += 1
    if not download_list:
        return 0
    if progress_callback:
        final_dl_list = BulkDownloadWorker.auto_split(
            download_list,
            lambda i: processed.__setitem__("v", processed["v"] + i),
            lambda: progress_callback(processed["v"], total)
        )
    else:
        final_dl_list = BulkDownloadWorker.auto_split(download_list)

    pool.setMaxThreadCount(75)
    for worker in final_dl_list:
        pool.start(worker)
        sleep(0.1)
    pool.waitForDone(-1)
    return len(download_list)

def is_virtual_asset(asset_index:dict):
    """Returns `True` if the asset index uses the `virtual` layout."""
    return asset_index.get("virtual", False)

def is_resource_mapped(asset_index:dict):
    """Returns `True` if the asset index uses the legacy `resources` dir."""
    return asset_index.get("map_to_resources", False)