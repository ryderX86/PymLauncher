"""
minecraftlauncher.back.library_manager

Handles downloading/filtering Minecraft libraries, extracting native
JARs, and building the classpath string.
"""
from pathlib import Path
from typing import Callable
import hashlib
import json
import logging
import os
import platform
import re
import zipfile

import requests
from PySide6.QtCore import QThreadPool

from minecraftlauncher.constants import (
    MINECRAFT_DIR,
    OS,
    ARCH,
    CLASSPATH_SEPARATOR,
    OS_VER,
    LIBRARIES_URL
)
from .download_manager import (
    download, should_download_file, _check_file_sha1, BulkDownloadSingleFile
)

log = logging.getLogger(__name__)

LIBRARIES_BASE = MINECRAFT_DIR / "libraries"

# Rule evaluation stuff

def _evaluate_rules(rules:list[dict]):
    """
    Evaluate a list of library rules.

    Rules are processed in order, last matching decides the outcome.
    If there's no rules, the library is included by default.

    If `True`, the lib is allowed, else don't download it.
    """
    if not rules:
        return True
    
    result = False

    for rule in rules:
        action = rule.get("action", "") == "allow"
        os_constraint = rule.get("os")

        if not os_constraint:
            # Rule matches
            result = action
        else:
            name_match = True
            arch_match = True
            ver_match = True

            if "name" in os_constraint:
                name_match = os_constraint["name"] == OS
            if "arch" in os_constraint:
                arch_match = os_constraint["arch"] == ARCH
            if "versionRange" in os_constraint:
                match OS:
                    case "windows":
                        ver = OS_VER.split('.')
                        comp_ver = os_constraint["versionRange"].get(
                            "min",
                            os_constraint["versionRange"].get("max", "120.0.0")
                        )
                        if "min" in os_constraint["versionRange"]:
                            mode = "min"
                        else:
                            mode = "max"
                        match = True
                        if ver[0] < comp_ver[0]:
                            match = False
                        elif ver[1] < comp_ver[1]:
                            match = False
                        elif ver[2] < comp_ver[2]:
                            match = False
                        if match and mode == "min":
                            ver_match = True
                        else:
                            ver_match = False
                    case _:
                        try:
                            ver_match = bool(
                                re.search(os_constraint["version"], OS_VER)
                            )
                        except re.error:
                            ver_match = False
            
            if name_match and arch_match and ver_match:
                result = action

    return result

def filter_libraries(version_json:dict):
    """
    Filter out libraries that don't need to be downloaded on the version,
    by rules.
    """
    libraries = version_json.get("libraries", [])
    return [lib for lib in libraries if _evaluate_rules(lib.get("rules", []))]

def _download_file(url:str, dest:str|Path, expected_sha1:str|None=None,
                   expected_size:int=0):
    """Download a file with sha1 verification (if present)"""
    if not expected_sha1:
        expected_sha1 = None
    if isinstance(dest, str):
        dest = Path(dest)
    if dest.exists() and dest.is_file() and expected_sha1:
        if _check_file_sha1(dest, expected_sha1):
            return False
    if should_download_file(dest, hash=expected_sha1, size=expected_size):
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = download(url, hash=expected_sha1)
        except:
            return False

        dest.touch()
        dest.write_bytes(resp.content)
        return True
    return False

def _get_lib_filepath(library:dict):
    """
    Returns a tuple of `str, str, str|None` or `None, None, None` depending on
    if the full name is present in the library's JSON.

    If present, the order will be `str(<lib_os_path>),
    <download url>, <sha1>|None`.
    """
    name:str = library.get("name", "")
    if not name:
        return None, None, None
    pkg, libname, ver = name.split(":")
    url = f"{LIBRARIES_URL}/{pkg}/{libname}/{libname}-{ver}.jar"
    if "natives" in library.keys():
        natives:dict = library.get("natives", {})
        native_str:str = natives.get(OS, "")
        match ARCH:
            case "x86_64" | "arm64":
                arch = "64"
            case "x86":
                arch = "32"
            case _:
                arch = ""
        native_str = native_str.replace("${arch}", arch)
        if native_str:
            ver = f"{ver}-{native_str}"
    sha1:str|None = None
    if "sha1" in library.keys():
        sha1 = library.get("sha1", "")
    if not sha1:
        sha1_url = url + ".sha1"
        try:
            sha1 = download(sha1_url).text
        except:
            log.warning("Failed to get SHA1 for library '%s'" % name)
            sha1 = None
        finally:
            del sha1_url

    folders = pkg.split(".")
    folderpath = Path(LIBRARIES_BASE, *folders, libname, ver)
    file_target = folderpath / f"{libname}-{ver}.jar"
    return str(file_target), url, sha1

def parse_lib_path(url:str, name:str):
    """Returns a tuple of `("<lib url>", "<lib fp>")`"""
    if (not url) or (not name):
        return ("", "")
    if url.endswith("/"):
        url = url[:-1]
    lib_info = name.split(":")
    org = lib_info[0].replace(".", "/")
    libname = lib_info[1]
    ver = lib_info[2]
    return (f"{url}/{org}/{libname}/{ver}/{libname}-{ver}.jar",
            f"{org}/{libname}/{ver}/{libname}-{ver}.jar")

def download_libraries(libraries:list[dict], *,
                       progress_callback:Callable[[int, int], None]|None=None):
    total = len(libraries)
    downloaded = 0
    processed_libs:list[str] = []

    for idx, lib in enumerate(libraries, 1):
        downloads:dict = lib.get("downloads", {})
        artifact:dict = downloads.get("artifact", {})

        if artifact:
            path:str = artifact.get("path", "")
            url = artifact.get("url", "")
            sha1 = artifact.get("sha1", "")
            size = artifact.get("size", 0)
        else:
            name:str|None = lib.get("name")
            url:str|None = lib.get("url")
            if (not name) or (not url):
                log.warning("No artifact, name, or URL in library, skipping.")
                if progress_callback:
                    progress_callback(idx, total)
                continue
            sha1:str|None = lib.get("sha1")
            size:int = lib.get("size", 0)
            url, path = parse_lib_path(url, name)

        if sha1 and sha1 in processed_libs:
            log.warning("Duplicate libary %s; continuing."
                        % lib.get("name", "--Unknown Library--"))
            continue

        if (not url) and (not path):
            log.warning("Manually retrieving URL and path for %s"
                        % lib.get("name", "--Unknown Library--"))
            path_, url_, sha1_ = _get_lib_filepath(lib)
            if (not path_) or (not url_) or (not sha1_):
                pass
            else:
                path = path_
                url = url_
                sha1 = sha1_
            del path_, url_, sha1_

        if url and path:
            destination = Path(LIBRARIES_BASE, *path.split("/"))
            if _download_file(url, destination, sha1, size):
                downloaded += 1
                log.info("Downloaded library %s to '%s'" %
                         (lib.get("name", "--Unknown Library"),
                          str(destination)))
        
        if progress_callback:
            progress_callback(idx, total)

        if sha1:
            processed_libs.append(sha1)
    
    log.debug("Finished downloading libraries: %d new / %d total"
              % (downloaded, total))
    return downloaded

def download_libraries_threaded(libraries:list[dict], *,
                       progress_callback:Callable[[int, int], None]|None=None):
    total = len(libraries)
    downloaded = 0
    download_list:list = []

    if progress_callback:
        def passed_callback(i:int):
            nonlocal downloaded, total
            downloaded += i
            progress_callback(downloaded, total)
    else:
        def passed_callback(i:int):
            pass

    pool = QThreadPool.globalInstance()
    if not pool:
        log.warning("Couldn't get QThreadPool, downloading single-threaded")
        return download_libraries(libraries,
                                  progress_callback=progress_callback)

    for idx, lib in enumerate(libraries, 1):
        downloads:dict = lib.get("downloads", {})
        artifact:dict = downloads.get("artifact", {})

        if artifact:
            path:str = artifact.get("path", "")
            url = artifact.get("url", "")
            sha1 = artifact.get("sha1", "")
            size = artifact.get("size", 0)
        else:
            name:str|None = lib.get("name")
            url:str|None = lib.get("url")
            if (not name) or (not url):
                log.warning("No artifact, name, or URL in library, skipping.")
                if progress_callback:
                    progress_callback(idx, total)
                continue
            sha1:str|None = lib.get("sha1")
            size:int = lib.get("size", 0)
            url, path = parse_lib_path(url, name)

        if sha1 and sha1 in download_list:
            log.warning("Duplicate libary %s; continuing."
                        % lib.get("name", "--Unknown Library--"))
            continue

        if (not url) and (not path):
            log.warning("Manually retrieving URL and path for %s"
                        % lib.get("name", "--Unknown Library--"))
            path_, url_, sha1_ = _get_lib_filepath(lib)
            if (not path_) or (not url_) or (not sha1_):
                pass
            else:
                path = path_
                url = url_
                sha1 = sha1_
            del path_, url_, sha1_

        if url and path:
            destination = Path(LIBRARIES_BASE, *path.split("/"))
            download_list.append(BulkDownloadSingleFile(
                url, destination, sha1 or None, callback_f=passed_callback
            ))

    pool.setMaxThreadCount(75)
    for dl in download_list:
        pool.start(dl)
    pool.waitForDone(-1)
    
    log.debug("Finished downloading libraries: %d new / %d total"
              % (downloaded, total))
    return downloaded

def _get_natives_classifier(lib:dict) -> str|None:
    """
    Determine the classifier for the platform-specific native JAR.

    Handles both `downloads.classifiers` and `natives` styles.
    """
    natives_map:dict = lib.get("natives", {})
    if not natives_map:
        return None
    
    classifier = natives_map.get(OS)
    if not classifier:
        return None
    
    arch_bits = "64" if ARCH in ("x86_64", "arm64") else "32"
    return classifier.replace("${arch}", arch_bits)

def download_natives(libraries: list[dict]):
    """Download native libs for platform."""
    downloaded = 0

    for lib in libraries:
        classifier = _get_natives_classifier(lib)
        if not classifier:
            continue

        classifiers:dict = lib.get("downloads", {}).get("classifiers", {})
        native_info:dict = classifiers.get(classifier, {})
        if not native_info:
            continue

        path:str = native_info.get("path", "")
        url:str = native_info.get("url", "")
        sha1:str = native_info.get("sha1", "")
        size:int = native_info.get("size", 0)

        if url and path:
            destination = Path(LIBRARIES_BASE, *path.split("/"))
            if _download_file(url, destination, sha1, size):
                downloaded += 1
            
    return downloaded

def extract_natives(libraries:list[dict], dir:str|Path):
    """
    Extract native libraries into the provided natives directory.

    If there's no real path, just give `LIBRARIES_DIR / <version_id>`
    
    Returns the natives directory.
    """
    if isinstance(dir, str):
        dir = Path(dir)
    dir.mkdir(parents=True, exist_ok=True)

    for lib in libraries:
        classifier = _get_natives_classifier(lib)
        if not classifier:
            continue

        classifiers:dict = lib.get("downloads", {}).get("classifiers", {})
        native_info:dict|None = classifiers.get(classifier)
        if not native_info:
            continue

        path:str = native_info.get("path", "")
        if not path:
            continue
        
        jar_path = Path(LIBRARIES_BASE, *path.split("/"))
        if (not jar_path.exists()) or (not jar_path.is_file()):
            log.warning("Couldn't find native at '%s'" % jar_path)
            continue

        extract_rules:dict = lib.get("extract", {})
        exclude:list = extract_rules.get("exclude", [])

        try:
            with zipfile.ZipFile(jar_path, "r") as zip:
                for entry in zip.namelist():
                    skip = False
                    for pattern in exclude:
                        if entry.startswith(pattern):
                            skip = True
                            break
                    if skip:
                        continue
                    zip.extract(entry, dir)
        except zipfile.BadZipFile:
            log.warning("Native at '%s' is bad archive" % str(jar_path))
        
    return dir

def build_classpath(libraries:list[dict], client_jar_path:str|Path):
    """
    Returns the entire JVM classpath string from the libraries and client JAR.
    """
    entries:list[str] = []
    if isinstance(client_jar_path, Path):
        client_jar_path = str(client_jar_path)
    
    for lib in libraries:
        artifact:dict = lib.get("downloads", {}).get("artifact")
        if artifact and artifact.get("path"):
            jar = Path(LIBRARIES_BASE, *artifact["path"].split("/"))
            if jar.exists() and jar.is_file():
                jar_str = str(jar)
                if jar_str not in entries:
                    entries.append(jar_str)
                    continue
                else:
                    log.warning("Skipping duplicate library: '%s'"
                                % lib.get("name", "--Unknown Library--"))
                    continue
        url, path = parse_lib_path(lib.get("url", ""), lib.get("name", ""))
        jar = Path(LIBRARIES_BASE, *path.split("/"))
        if jar.exists() and jar.is_file():
            entries.append(str(jar))
        else:
            log.warning("Couldn't find library '%s', skipping"
                        % lib.get("name", "--Unknown Library--"))
    
    entries.append(client_jar_path)
    cp_string = CLASSPATH_SEPARATOR.join(entries)
    return cp_string