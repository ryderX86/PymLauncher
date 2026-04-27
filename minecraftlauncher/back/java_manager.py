"""
minecraftlauncher.back.java_manager

Handles downloading/retrieving Java versions.
"""

from pathlib import Path
from typing import Callable
from datetime import datetime, timedelta
import hashlib
import json
import logging
import lzma

from PySide6.QtCore import QThreadPool

from minecraftlauncher.constants import (
    MINECRAFT_DIR,
    OS,
    ARCH,
    MOJANG_JAVA_BASE,
    JAVA_PATH,  # type: ignore
    JAVA_MANIFEST_URL,
    JAVA_OS,
)
from minecraftlauncher.functions.text import indent
from .download_helpers import download, RunnableDownloader

log = logging.getLogger(__name__)

JVM_MANIFEST_PATH = MINECRAFT_DIR / "versions" / "jre_manifest.json"

jvm_manifest = {}


def get_jvm_manifest(force_update: bool = False):
    """
    Fetches the jvm manifest either from disk or web.
    """
    global jvm_manifest

    if force_update:
        log.info("Manual JRE manifest download triggered.")
    elif jvm_manifest:
        return jvm_manifest
    elif JVM_MANIFEST_PATH.exists() and JVM_MANIFEST_PATH.is_file():
        log.debug("Checking cached jre_manifest.json...")
        cache_age = JVM_MANIFEST_PATH.stat().st_mtime
        max_age = (datetime.now() - timedelta(days=7)).timestamp()
        if max_age < cache_age:
            mf_text = JVM_MANIFEST_PATH.read_text()
            try:
                mf = json.loads(mf_text)
            except json.JSONDecodeError as err:
                log.error("Error reading 'jre_manifest.json':", exc_info=err)
                log.info("Have to re-download 'jre_manifest.json'.")
                JVM_MANIFEST_PATH.unlink()
                log.debug("Deleted '%s'", str(JVM_MANIFEST_PATH))
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
    JVM_MANIFEST_PATH.write_text(resp.text)
    log.info("Saved JRE manifest to disk.")
    return jvm_manifest


def get_jvm_version_manifest(version: str):
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

    manifest_path = MINECRAFT_DIR / "jre" / f"{version}.{JAVA_OS}.json"

    if manifest_path.exists() and manifest_path.is_file():
        max_age = (datetime.now() - timedelta(days=7)).timestamp()
        file_ts = manifest_path.stat().st_mtime
        if max_age < file_ts:
            log.info(
                "Found pre-existing file: '%s', checking SHA1",
                str(manifest_path),
            )
            if sha1:
                mf_sha1 = hashlib.sha1(manifest_path.read_bytes()).hexdigest()
                if mf_sha1 == sha1:
                    return json.loads(manifest_path.read_text())
                else:
                    log.warning(
                        "JRE manifest at '%s' is outdated or "
                        "corrupted, redownloading...",
                        str(manifest_path),
                    )
                    manifest_path.unlink()
            else:
                mf_text = manifest_path.read_text()
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
    elif not manifest_path.parent.exists():
        p = manifest_path.parent
        log.debug("Creating path: %s", p)
        p.mkdir(parents=True, exist_ok=True)

    log.info("Downloading manifest from '%s'", url)
    resp = download(url, sha=sha1)
    manifest_path.write_text(resp.text)
    return resp.json()


def java_base_path(name: str):
    jre_path_default = JAVA_PATH / name
    jre_path_mojang = MOJANG_JAVA_BASE / name

    match OS:  # TODO: cross-platform
        case "windows":
            exec_path_def = jre_path_default
            exec_path_moj = jre_path_mojang / JAVA_OS / name
        case "osx":
            exec_path_def = (
                jre_path_default / "jre.bundle" / "Contents" / "Home"
            )
            exec_path_moj = exec_path_def
        case _:
            exec_path_def = jre_path_default
            exec_path_moj = exec_path_def

    return exec_path_def, exec_path_moj


def java_exc_path(name: str):
    jre_path_default = JAVA_PATH / name
    jre_path_mojang = MOJANG_JAVA_BASE / name

    match OS:  # TODO: cross-platform
        case "windows":
            exec_path_def = jre_path_default / "bin" / "javaw.exe"
            exec_path_moj = (
                jre_path_mojang / JAVA_OS / name / "bin" / "javaw.exe"
            )
        case "osx":
            exec_path_def = (
                jre_path_default
                / "jre.bundle"
                / "Contents"
                / "Home"
                / "bin"
                / "java"
            )
            exec_path_moj = exec_path_def
        case _:
            exec_path_def = jre_path_default / "bin" / "java"
            exec_path_moj = exec_path_def

    return exec_path_def, exec_path_moj


def find_java_exc(name: str):
    """
    Check for a Java installation and executable.

    The check is *very* simple, and *can* return a broken Java install.

    Returns java exec path if possible. If not, raises RuntimeError.
    """
    exec_path_def, exec_path_moj = java_exc_path(name)

    if exec_path_def.exists() and exec_path_def.is_file():
        return exec_path_def
    elif exec_path_moj.exists() and exec_path_moj.is_file():
        return exec_path_moj
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

    jre_path_default, jre_path_mojang = java_base_path(name)

    match OS:
        case "windows":
            exc_path = ["bin", "javaw.exe"]
        case "osx":
            exc_path = ["jre.bundle", "Contents", "Home", "bin", "java"]
        case _:
            exc_path = ["bin", "java"]

    if jre_path_mojang.exists():
        # Check mojang launcher's java install
        valid = True
        completed = 0
        for subpath in dirs:
            dir_ = Path(jre_path_mojang, *subpath.split("/"))
            if not (dir_.exists() and dir_.is_dir()):
                valid = False
                break
        for subpath, finfo in files.items():
            path = Path(jre_path_mojang * subpath.split("/"))
            if path.exists() and path.is_file():
                f_sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
                e_sha1 = finfo["downloads"]["raw"].get("sha1")
                if e_sha1 and f_sha1 != e_sha1:
                    valid = False
                    break
            else:
                valid = False
                break
            completed += 1
            if progress_callback:
                progress_callback(completed, total_size)
        if valid:
            log.info("Found vanilla Java install that matches.")
            if "MinecraftJava.exe" in files.keys():
                # this might be horrible but idk yet, YOLO
                final_path = jre_path_mojang / name / "MinecraftJava.exe"
            else:
                final_path = Path(jre_path_mojang, *exc_path)
            log.info("JRE executable path: '%s'", str(final_path))
            return final_path
        else:
            log.info("Didn't find matching vanilla Java install.")
            if progress_callback:
                progress_callback(0, total_size)

    jre_path_default.mkdir(exist_ok=True, parents=True)
    completed = 0
    downloaded = 0

    for subpath in dirs:
        dir_ = jre_path_default / subpath
        dir_.mkdir(parents=True, exist_ok=True)
    for subpath, finfo in files.items():
        path = Path(jre_path_default, *subpath.split("/"))
        e_sha1 = finfo["downloads"]["raw"].get("sha1")  # expected sha1
        if path.exists() and path.is_file():
            f_sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
            if e_sha1 and e_sha1 == f_sha1:
                completed += 1
                continue
            elif e_sha1:
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

        if use_lzma:
            path.write_bytes(lzma.decompress(resp.content))
            f_sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
            # this should be removed after verifying that the lzma
            # decompression is actually working
            if f_sha1 != e_sha1:
                raise RuntimeError(
                    f"Failed downloading {str(path)} - SHA1 mismatch"
                    f" (expected value: '{e_sha1}', got '{f_sha1}')"
                )
        else:
            path.write_bytes(resp.content)

        log.debug("Downloaded '%s'->'%s'", url, subpath)
        completed += 1
        downloaded += 1
        if progress_callback:
            progress_callback(completed, total_size)
        continue

    log.info("Download complete, %d/%d new files.", downloaded, total_size)

    if "MinecraftJava.exe" in files.keys():
        return jre_path_default / "MinecraftJava.exe"
    else:
        return Path(jre_path_default, *exc_path)


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

    total_size = len(files.keys()) - len(dirs)
    if progress_callback:
        progress_callback(0, total_size)

    jre_path_default = JAVA_PATH / name
    jre_path_mojang = MOJANG_JAVA_BASE / name

    match OS:
        case "windows":
            exc_path = ["bin", "javaw.exe"]
        case "osx":
            exc_path = ["jre.bundle", "Contents", "Home", "bin", "java"]
        case _:
            exc_path = ["bin", "java"]

    if jre_path_mojang.exists():
        # Check mojang launcher's java install
        log.debug("Found Mojang launcher's Java installation, checking it...")
        valid = True
        completed = 0
        for subpath in dirs:
            dir_ = Path(jre_path_mojang, *subpath.split("/"))
            if not (dir_.exists() and dir_.is_dir()):
                valid = False
                break
        for subpath, finfo in files.items():
            path = Path(jre_path_mojang * subpath.split("/"))
            if path.exists() and path.is_file():
                f_sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
                sha1 = finfo["downloads"]["raw"].get("sha1")
                if sha1 and f_sha1 != sha1:
                    log.debug("File failed SHA1 check: %s", str(path))
                    valid = False
                    break
            else:
                log.debug("File failed existance check: %s", str(path))
                valid = False
                break
            completed += 1
            if progress_callback:
                progress_callback(completed, total_size)
        if valid:
            log.info("Found Mojang launcher's Java install that matches.")
            if "MinecraftJava.exe" in files.keys():
                # this might be horrible but idk yet, YOLO
                final_path = jre_path_mojang / name / "MinecraftJava.exe"
            else:
                final_path = Path(jre_path_mojang, *exc_path)
            log.info("JRE executable path: '%s'", str(final_path))
            return final_path
        else:
            log.info("Didn't find matching vanilla Java install.")
            if progress_callback:
                progress_callback(0, total_size)

    jre_path_default.mkdir(exist_ok=True, parents=True)
    completed = 0
    downloaded = 0

    def file_downloaded(i: int):
        nonlocal completed, total_size, progress_callback
        completed += 1
        if progress_callback:
            progress_callback(completed, total_size)

    download_workers: list[RunnableDownloader] = []

    for subpath in dirs:
        dir_ = jre_path_default / subpath
        dir_.mkdir(parents=True, exist_ok=True)
    for subpath, finfo in files.items():
        path = Path(jre_path_default, *subpath.split("/"))
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
                mkdir=True,
                use_lzma=use_lzma,
                callback=file_downloaded,
            )
        )

    # if progress_callback:
    #     progress_callback(completed, total_size)
    #     dl_list = BulkDownloadWorker.auto_split(
    #         download_workers,
    #         lambda i: file_downloaded(i),
    #         lambda: progress_callback(completed, total_size)
    #     )
    # else:
    #     dl_list = BulkDownloadWorker.auto_split(download_workers)

    pool.setMaxThreadCount(75)
    for dl in download_workers:
        pool.start(dl)
    pool.waitForDone(-1)

    log.info("Download complete, %d/%d new files.", downloaded, total_size)

    if "MinecraftJava.exe" in files.keys():
        return jre_path_default / "MinecraftJava.exe"
    else:
        return Path(jre_path_default, *exc_path)
