"""
minecraftlauncher.back.java_manager

Handles downloading/retrieving Java versions.
"""

from collections.abc import Callable
from datetime import timedelta
import hashlib
import logging
import json
import lzma
import stat
import time
import os

from PySide6.QtCore import QThreadPool

from minecraftlauncher.constants import (
    OS,
    ARCH,
    JAVA_MANIFEST_URL,
    JAVA_OS,
    CPU_THREADS,
)
from minecraftlauncher.paths import paths
from minecraftlauncher.functions.text import indent
from .download_helpers import download, RunnableDownloader, BulkDownloadError

log = logging.getLogger(__name__)

jvm_manifest = {}


def get_jvm_manifest(force_update: bool = False) -> dict:
    """
    Fetches the jvm manifest either from disk or web.
    """
    global jvm_manifest

    if force_update:
        log.info("Manual JRE manifest download triggered.")
    elif jvm_manifest:
        return jvm_manifest
    elif os.path.isfile(paths.jvm_manifest):
        log.debug("Checking cached jre_manifest.json...")
        cache_age = os.stat(paths.jvm_manifest).st_mtime
        max_age = time.time() - timedelta(days=7).total_seconds()
        if max_age < cache_age:
            with open(paths.jvm_manifest, "r") as f:
                mf_text = f.read()
            try:
                mf = json.loads(mf_text)
            except json.JSONDecodeError as err:
                log.error("Error reading 'jre_manifest.json':", exc_info=err)
                log.info("Have to re-download 'jre_manifest.json'.")
                os.unlink(paths.jvm_manifest)
                log.debug("Deleted '%s'", paths.jvm_manifest)
            else:
                log.info("Using cached jre_manifest.json")
                jvm_manifest = mf
                return mf
        else:
            log.info("'jre_manifest.json' is too old, re-downloading it.")

    log.info("Getting JRE manifest from '%s'", JAVA_MANIFEST_URL)
    resp = download(JAVA_MANIFEST_URL)
    mf_raw = resp.json()
    jvm_manifest = mf_raw
    with open(paths.jvm_manifest, "w") as f:
        f.write(resp.text)
    log.info("Saved JRE manifest to disk.")
    return jvm_manifest


def get_jvm_version_manifest(version: str) -> dict:
    """
    Fetches the JVM manifest for a specific version (i.e.
    `java-runtime-epsilon`)
    """
    get_jvm_manifest()
    mf: dict = jvm_manifest.get(JAVA_OS, {})
    if not mf:
        mf = jvm_manifest.get("manifest", {}).get(JAVA_OS, {})
    if not mf:
        err = ValueError("No manifest found")
        err.add_note(f"OS: '{OS}'; ARCH: '{ARCH}'")
        vers = ", ".join(jvm_manifest.keys())
        err.add_note(f"Versions found: {vers}")
        raise err

    jvm_versions: list = mf.get(version, [])
    if not jvm_versions:
        raise ValueError(
            f"Couldn't find JVM version '{version}' in "
            # seeing this string would kill a victorian child:
            f"[\"{'", "'.join(mf.keys())}\"]"
        )

    if len(jvm_versions) > 1:
        log.warning(
            "Multiple JVM versions within '%s.%s', full JSON:\n%s",
            JAVA_OS,
            version,
            indent(json.dumps(mf, indent=2)),
        )

    jvm_version: dict = jvm_versions[0]

    java_version_info: dict = jvm_version.get("version", {})
    if java_version_info:
        ver = java_version_info.get("name", "unidentified")
        release = java_version_info.get("released", "unknown")
        log.info("Found Java %s (released: %s) in manifest", ver, release)
        del ver, release

    java_version_manifest = jvm_version.get("manifest", {})
    if not java_version_manifest:
        err = ValueError("Unexpectedly missing 'manifest' from version JSON")
        err.add_note(json.dumps(jvm_version, indent=2))
        raise err

    url = java_version_manifest.get("url")
    if not url:
        err = ValueError(
            "Unexpectedly missing 'url' in version JSON key 'manifest'"
        )
        err.add_note(json.dumps(jvm_version, indent=2))
        raise err

    sha1: str | None = java_version_manifest.get("sha1")
    if not sha1:
        log.warning("SHA1 is missing from JRE version keys.")

    manifest_path = os.path.join(paths.game, "jre", f"{version}.{JAVA_OS}.json")

    if os.path.isfile(manifest_path):
        max_age = time.time() - timedelta(days=7).total_seconds()
        file_ts = os.stat(manifest_path).st_mtime
        if max_age < file_ts:
            log.info(
                "Found pre-existing file: '%s', checking SHA1",
                str(manifest_path),
            )
            if sha1:
                with open(manifest_path, "rb") as file:
                    mf_bytes = file.read()
                mf_sha1 = hashlib.sha1(mf_bytes).hexdigest()
                if mf_sha1 == sha1:
                    return json.loads(mf_bytes.decode("utf-8"))
                else:
                    log.warning(
                        "JRE manifest at '%s' is outdated or "
                        "corrupted, redownloading...",
                        str(manifest_path),
                    )
                    os.unlink(manifest_path)
            else:
                with open(manifest_path, "r") as file:
                    mf_text = file.read()
                try:
                    return json.loads(mf_text)
                except json.JSONDecodeError as err:
                    log.error(
                        "Failed to read JSON at '%s', redownloading.",
                        str(manifest_path),
                        exc_info=err,
                    )
        else:
            log.info("Found pre-existing file but it's too old.")
    elif not os.path.isdir(os.path.split(manifest_path)[0]):
        parent_dir = os.path.split(manifest_path)[0]
        log.debug("Creating path: %s", parent_dir)
        os.makedirs(parent_dir, exist_ok=True)

    log.info("Downloading manifest from '%s'", url)
    resp = download(url, sha=sha1)
    with open(manifest_path, "w") as file:
        file.write(resp.text)
    return resp.json()


def java_base_path(name: str):
    jre_path_default = os.path.join(paths.jre_path, name)

    match OS:  # TODO: cross-platform
        case "windows":
            exec_path_def = jre_path_default
        case "osx":
            exec_path_def = os.path.join(
                jre_path_default, "jre.bundle", "Contents", "Home"
            )
        case _:
            exec_path_def = jre_path_default

    return exec_path_def


def java_exc_path(name: str):
    jre_path_default = os.path.join(paths.jre_path, name)

    match OS:  # TODO: cross-platform
        case "windows":
            exec_path_def = os.path.join(jre_path_default, "bin", "javaw.exe")
        case "osx":
            exec_path_def = os.path.join(
                jre_path_default,
                "jre.bundle",
                "Contents",
                "Home",
                "bin",
                "java",
            )
        case _:
            exec_path_def = os.path.join(jre_path_default, "bin", "java")

    return exec_path_def


def find_java_exc(name: str):
    """
    Check for a Java installation and executable.

    The check is *very* simple, and *can* return a broken Java install.

    Returns java exec path if possible. If not, raises RuntimeError.
    """
    exec_path_def = java_exc_path(name)

    if os.path.isfile(exec_path_def):
        return exec_path_def
    raise RuntimeError("No working java executable found")


def install_java_version(
    name: str, jre_manifest: dict, *, progress_callback: Callable | None = None
):
    """Installs specified JRE version from Mojang. Returns javaw.exe path"""
    path_list = jre_manifest.get("files", {})
    files = {k: v for k, v in path_list.items() if v["type"] == "file"}
    dirs: list[str] = [
        k for k, v in path_list.items() if v["type"] == "directory"
    ]

    total_size = len(files.keys()) - len(dirs)

    jre_path_default = java_base_path(name)

    match OS:
        case "windows":
            exc_path = ["bin", "javaw.exe"]
        case "osx":
            exc_path = ["jre.bundle", "Contents", "Home", "bin", "java"]
        case _:
            exc_path = ["bin", "java"]

    if not os.path.isdir(jre_path_default):
        os.makedirs(jre_path_default, exist_ok=True)
    completed = 0
    downloaded = 0

    for subpath in dirs:
        dir_ = os.path.join(jre_path_default, subpath)
        if not os.path.isdir(dir_):
            os.makedirs(dir_, exist_ok=True)
    for subpath, finfo in files.items():
        path = os.path.join(jre_path_default, *subpath.split("/"))
        e_sha1 = finfo["downloads"]["raw"].get("sha1")  # expected sha1
        if os.path.isfile(path):
            with open(path, "rb") as f:
                f_sha1 = hashlib.sha1(f.read()).hexdigest()
            if e_sha1 and e_sha1 == f_sha1:
                completed += 1
                continue
            if e_sha1:
                log.warning(
                    "File at '%s' has SHA1 ('%s') that doesn't match "
                    "expected value '%s'",
                    subpath,
                    f_sha1,
                    e_sha1,
                )

        # prioritize lower internet reliance first, then fallback to raw file
        url = str(finfo.get("downloads", {}).get("lzma", {}).get("url", ""))
        sha1 = str(finfo.get("downloads", {}).get("lzma", {}).get("sha1", ""))
        use_lzma = True
        if not url:
            url = str(finfo.get("downloads", {}).get("raw", {})["url"])
            sha1 = str(finfo.get("downloads", {}).get("raw", {})["sha1"])
            use_lzma = False

        log.info("Downloading '%s' from '%s'", subpath, url)

        # use the matching hash since we don't load the lzma yet
        resp = download(url, sha=sha1)

        with open(path, "wb") as fb:
            if use_lzma:
                fb.write(lzma.decompress(resp.content))
            else:
                fb.write(resp.content)

        log.debug("Downloaded '%s'->'%s'", url, subpath)
        completed += 1
        downloaded += 1
        if progress_callback:
            progress_callback(completed, total_size)
        continue

    log.info("Download complete, %d/%d new files.", downloaded, total_size)

    if "MinecraftJava.exe" in files.keys():
        return os.path.join(jre_path_default, "MinecraftJava.exe")
    else:
        return os.path.join(jre_path_default, *exc_path)


def install_java_version_threaded(
    name: str, jre_manifest: dict, *, progress_callback: Callable | None = None
):
    """Installs specified JRE version from Mojang. Returns javaw.exe path"""
    pool = QThreadPool.globalInstance()
    if not pool:
        log.warning("Couldn't get QThreadPool, downloading single-threaded")
        return install_java_version(
            name, jre_manifest, progress_callback=progress_callback
        )
    path_list = jre_manifest.get("files", {})
    files = {k: v for k, v in path_list.items() if v["type"] == "file"}
    dirs: list[str] = [
        k for k, v in path_list.items() if v["type"] == "directory"
    ]

    total_size = len(files.keys())
    if progress_callback:
        progress_callback(0, total_size)

    jre_path_default = os.path.join(paths.jre_path, name)

    match OS:
        case "windows":
            exc_path = ["bin", "javaw.exe"]
        case "osx":
            exc_path = ["jre.bundle", "Contents", "Home", "bin", "java"]
        case _:
            exc_path = ["bin", "java"]

    os.makedirs(jre_path_default, exist_ok=True)
    completed = 0
    downloaded = 0

    def file_downloaded(i: int):
        nonlocal completed, total_size, progress_callback
        completed += 1
        if progress_callback:
            progress_callback(completed, total_size)

    download_workers: list[RunnableDownloader] = []

    for subpath in dirs:
        dir_ = os.path.join(jre_path_default, subpath)
        os.makedirs(dir_, exist_ok=True)
    for subpath, finfo in files.items():
        path = os.path.join(jre_path_default, *subpath.split("/"))
        sha1 = finfo["downloads"]["raw"].get("sha1")  # expected sha1

        # prioritize lower internet reliance first, then fallback to raw file
        url = str(finfo.get("downloads", {}).get("lzma", {}).get("url", ""))
        use_lzma = True
        if not url:
            url = str(finfo.get("downloads", {}).get("raw", {})["url"])
            use_lzma = False

        # use the matching hash since we don't load the lzma yet
        download_workers.append(
            RunnableDownloader(
                url,
                path,
                sha1,
                use_lzma=use_lzma,
                callback=file_downloaded,
            )
        )

    pool.setMaxThreadCount(CPU_THREADS)
    for dl in download_workers:
        pool.start(dl)
    timed_out = not pool.waitForDone(900000)
    if timed_out:
        raise RuntimeError("Downloads completely timed out")
    elif any(not a.success for a in download_workers):
        raise BulkDownloadError.from_runnable_list(download_workers)

    log.info("Download complete, %d/%d new files.", downloaded, total_size)

    if "MinecraftJava.exe" in files.keys():
        return os.path.join(jre_path_default, "MinecraftJava.exe")
    else:
        return os.path.join(jre_path_default, *exc_path)


def mark_executable(exe_path: str | os.PathLike) -> bool:
    match OS:
        case "windows":
            log.warning("mark_executable() called from Windows")
            return os.path.splitext(exe_path)[1] == ".exe"
    if not os.path.isfile(exe_path):
        raise ValueError(f"File at '{exe_path}' doesn't exist")
    perms = stat.S_IXUSR | stat.S_IXOTH | stat.S_IXGRP
    if os.stat(exe_path).st_mode & perms:
        return True
    log.debug("Attempting to mark file at '%s' as executable", exe_path)
    try:
        os.chmod(exe_path, os.stat(exe_path).st_mode | perms)
    except Exception as err:
        log.error(
            "Failed to mark file at '%s' as executable:", exe_path, exc_info=err
        )
        return False
    return True
