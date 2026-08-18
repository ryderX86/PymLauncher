"""
minecraftlauncher.back.java_manager

Handles downloading/retrieving Java versions.
"""

from collections.abc import Callable
from datetime import timedelta
import hashlib
import logging
import json
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
from minecraftlauncher.exceptions.back import (
    JavaIndexError,
    MarkExecutableError,
)
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


def get_java_file_dowloads(
    name: str, jre_manifest: dict, *, progress_callback: Callable | None = None
) -> list[RunnableDownloader]:
    """
    Gets list of downloaders for the specified JRE version from Mojang.

    Raises `minecraftlauncher.exceptions.back.JavaIndexError` if any file in
    the index is missing download info
    """
    # filter index into files only (normally directories are present)
    path_list: dict[str, dict] = {
        k: v
        for k, v in jre_manifest.get("files", {}).items()
        if v["type"] == "file"
    }

    dl_count = len(path_list.keys())

    jre_path_default = os.path.join(paths.jre_path, name)

    if progress_callback:
        progress_callback(0, dl_count)
        completed = 0

        def callback(i: int):
            nonlocal completed
            completed += i
            progress_callback(completed, dl_count)

    else:

        def callback(i: int):
            pass

    dl_list: list[RunnableDownloader] = []

    for subpath, finfo in path_list.items():
        path = os.path.join(jre_path_default, *subpath.split("/"))
        sha1 = finfo["downloads"]["raw"].get("sha1")  # expected sha1

        # get download url
        url = finfo.get("downloads", {}).get("lzma", {}).get("url")
        use_lzma = True
        if not url:
            url = finfo.get("downloads", {}).get("raw", {}).get("url")
            if not url:
                raise JavaIndexError(subpath, jre_manifest)
            use_lzma = False

        if not isinstance(url, str):
            raise JavaIndexError(subpath, jre_manifest) from TypeError(url)

        # use the matching hash since we don't load the lzma yet
        dl_list.append(
            RunnableDownloader(
                url=url,
                path=path,
                sha1=sha1,
                use_lzma=use_lzma,
                callback=callback,
            )
        )

    return dl_list


def download_java_version(
    name: str,
    jre_manifest: dict,
    *,
    progress_callback: Callable | None = None,
    threaded: bool = True,
):
    pool = QThreadPool.globalInstance()
    if not pool:
        log.warning("Couldn't get QThreadPool, downloading single-threaded")
        threaded = False

    dl_list = get_java_file_dowloads(
        name, jre_manifest, progress_callback=progress_callback
    )

    jre_path_default = os.path.join(paths.jre_path, name)

    if threaded:
        pool.setMaxThreadCount(CPU_THREADS)
        for worker in dl_list:
            pool.start(worker)
        timed_out = not pool.waitForDone(900000)
        if timed_out:
            raise RuntimeError("Downloads completely timed out")
        elif any(not a.success for a in dl_list):
            raise BulkDownloadError.from_runnable_list(dl_list)
    else:
        log.warning("Running downloads unthreaded")
        for worker in dl_list:
            worker.run()
            if worker.failed:
                log.warning("Download worker failed, breaking early")
                break
        if any(not a.success for a in dl_list):
            raise BulkDownloadError.from_runnable_list(dl_list)

    log.info(
        "Download complete, %d/%d new files.",
        len({a.downloaded_file for a in dl_list}),
        len(dl_list),
    )

    match OS:
        case "windows":
            base_exc_path = ["bin", "javaw.exe"]
        case "osx":
            base_exc_path = ["jre.bundle", "Contents", "Home", "bin", "java"]
        case _:
            base_exc_path = ["bin", "java"]

    if OS == "windows":
        if "MinecraftJava.exe" in jre_manifest.get("files", {}).keys():
            return os.path.join(jre_path_default, "MinecraftJava.exe")
        else:
            return os.path.join(jre_path_default, *base_exc_path)
    else:
        exc_path = os.path.join(jre_path_default, *base_exc_path)
        try:
            mark_executable(exc_path)
        except PermissionError as err:
            log.error(
                "Unable to mark %r as executable:", exc_path, exc_info=err
            )
            raise
        return exc_path


def mark_executable(exe_path: str | os.PathLike) -> bool:
    if OS == "windows":
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
    except PermissionError as err:
        log.error(
            "Failed to mark file at %r as executable (no permissions)",
            exe_path,
            exc_info=err,
        )
        raise MarkExecutableError(exe_path) from err
    except Exception as err:
        log.error(
            "Failed to mark file at %r as executable (%s)",
            exe_path,
            type(err).__name__,
            exc_info=err,
        )
        raise MarkExecutableError(exe_path) from err
    return True
