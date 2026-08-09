"""
minecraftlauncher.back.library_manager

Handles downloading/filtering Minecraft libraries, extracting native
JARs, and building the classpath string.
"""

from collections.abc import Callable
import logging
import zipfile
import os

from PySide6.QtCore import QThreadPool
from packaging.version import Version, parse

from minecraftlauncher.functions import is_path_valid
from minecraftlauncher.paths import paths
from minecraftlauncher.constants import (
    OS,
    ARCH,
    CLASSPATH_SEPARATOR,
    OS_VER,
    LIBRARIES_URL,
    CPU_THREADS,
)
from minecraftlauncher.config import config
from .download_helpers import (
    download,
    should_download_file,
    _check_file_sha1,
    RunnableDownloader,
    BulkDownloadError,
)

log = logging.getLogger(__name__)

# Rule evaluation stuff


def evaluate_rules(rules: list[dict]) -> bool:
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
        action = rule.get("action") == "allow"
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
                    case "windows" | "linux":
                        ver = parse(OS_VER)
                        try:
                            min_ver: Version = parse(
                                os_constraint["versionRange"].get(
                                    "min", "0.0.0.0"
                                )
                            )
                        except Exception as err:
                            log.error(
                                "Error parsing version '%s' to "
                                "packaging.Version:",
                                os_constraint["versionRange"].get(
                                    "min", "0.0.0.0"
                                ),
                                exc_info=err,
                            )
                            log.info("Minimum version range set to 0.0.0.0")
                            min_ver = parse("0.0.0.0")
                        try:
                            max_ver: Version = parse(
                                os_constraint["versionRange"].get(
                                    "max", "999.9.9.9"
                                )
                            )
                        except Exception as err:
                            log.error(
                                "Error parsing version '%s' to "
                                "packaging.Version:",
                                os_constraint["versionRange"].get(
                                    "max", "999.9.9.9"
                                ),
                                exc_info=err,
                            )
                            log.info("Maximum version range set to 999.9.9.9")
                            max_ver = parse("999.9.9.9")
                        if "min" in os_constraint["versionRange"]:
                            mode = "min"
                        elif set(os_constraint["versionRange"].keys()) == {
                            "min",
                            "max",
                        }:
                            mode = "minmax"
                        elif "max" in os_constraint["versionRange"]:
                            mode = "max"
                        else:
                            log.warning(
                                "Can't determine version rule, downloading for safety."
                            )
                            mode = "skip"
                        match mode:
                            case "min":
                                ver_match = ver >= min_ver
                            case "max":
                                ver_match = ver <= max_ver
                            case "minmax":
                                ver_match = max_ver >= ver >= min_ver
                            case _:
                                ver_match = action
                    case _:
                        log.debug("Unknown version rule, skipping")
                        ver_match = True

            if name_match and arch_match and ver_match:
                result = action

    return result


def filter_libraries(version_json: dict) -> list[dict]:
    """
    Filter out libraries that don't need to be downloaded on the version,
    by rules.
    """
    libraries = version_json.get("libraries", [])
    return [lib for lib in libraries if evaluate_rules(lib.get("rules", []))]


def _download_file(
    url: str,
    dest: str | os.PathLike,
    expected_sha1: str | None = None,
    expected_size: int = 0,
):
    """Download a file with sha1 verification (if present)"""
    if not isinstance(dest, str):
        dest = str(dest)
    if not is_path_valid(dest):
        raise ValueError(f"Bad file path: {dest!r}")
    if not expected_sha1:
        expected_sha1 = None
    if os.path.isfile(dest) and expected_sha1:
        if _check_file_sha1(dest, expected_sha1):
            return False
    if should_download_file(dest, sha=expected_sha1, size=expected_size):
        parent = os.path.split(dest)[0]
        if not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        try:
            resp = download(url, sha=expected_sha1)
        except:
            return False

        with open(dest, "wb") as fb:
            fb.write(resp.content)
        return True
    return False


def _get_lib_filepath(
    library: dict,
) -> tuple[str, str, str | None] | tuple[None, None, None]:
    """
    Returns a tuple of `str, str, str|None` or `None, None, None` depending on
    if the full name is present in the library's JSON.

    If present, the order will be `str(<lib_os_path>),
    <download url>, <sha1>|None`.
    """
    name: str = library.get("name", "")
    if not name:
        return None, None, None
    pkg, libname, ver = name.split(":")
    url = f"{LIBRARIES_URL}/{pkg}/{libname}/{libname}-{ver}.jar"
    if "natives" in library.keys():
        natives: dict = library.get("natives", {})
        native_str: str = natives.get(OS, "")
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
    sha1: str | None = None
    if "sha1" in library.keys():
        sha1 = library.get("sha1", "")
    if not sha1:
        sha1_url = url + ".sha1"
        try:
            resp = download(sha1_url)
            resp.raise_for_status()
            sha1 = resp.text
        except Exception as err:
            log.warning(
                "Failed to get SHA1 for library '%s'", name, exc_info=err
            )
            sha1 = None
        finally:
            del sha1_url

    folders = pkg.split(".")
    folderpath = os.path.join(paths.libraries, *folders, libname, ver)
    file_target = os.path.join(folderpath, f"{libname}-{ver}.jar")
    return file_target, url, sha1


def parse_lib_path(url: str, name: str) -> tuple[str, str]:
    """Returns a tuple of `("<lib url>", "<lib fp>")`"""
    if not url:
        url = "https://libraries.minecraft.net/"
    if not name:
        return ("", "")
    if url.endswith("/"):
        url = url[:-1]
    lib_info = name.split(":")
    org = lib_info[0].replace(".", "/")
    libname = lib_info[1]
    ver = lib_info[2]
    return (
        f"{url}/{org}/{libname}/{ver}/{libname}-{ver}.jar",
        f"{org}/{libname}/{ver}/{libname}-{ver}.jar",
    )


def download_libraries(
    libraries: list[dict],
    *,
    progress_callback: Callable[[int, int], None] | None = None,
):
    total = len(libraries)
    downloaded = 0
    processed_libs: list[str] = []

    for idx, lib in enumerate(libraries, 1):
        downloads: dict = lib.get("downloads", {})
        artifact: dict = downloads.get("artifact", {})

        if artifact:
            path: str = artifact.get("path", "")
            url = artifact.get("url", "")
            sha1 = artifact.get("sha1", "")
            size = artifact.get("size", 0)
        else:
            name: str | None = lib.get("name")
            url: str | None = lib.get("url")
            if (not name) or (not url):
                log.warning("No artifact, name, or URL in library, skipping.")
                if progress_callback:
                    progress_callback(idx, total)
                continue
            sha1: str | None = lib.get("sha1")
            size: int = lib.get("size", 0)
            url, path = parse_lib_path(url, name)

        if sha1 and sha1 in processed_libs:
            log.warning(
                "Duplicate libary %s; continuing.",
                lib.get("name", "<unidentified>"),
            )
            continue

        if (not url) and (not path):
            log.warning(
                "Manually retrieving URL and path for %s",
                lib.get("name", "<unidentified>"),
            )
            path_, url_, sha1_ = _get_lib_filepath(lib)
            if (not path_) or (not url_) or (not sha1_):
                pass
            else:
                path = path_
                url = url_
                sha1 = sha1_
            del path_, url_, sha1_

        if url and path:
            destination = os.path.join(paths.libraries, *path.split("/"))
            if _download_file(url, destination, sha1, size):
                downloaded += 1
                log.info(
                    "Downloaded library %s to '%s'",
                    lib.get("name", "<unidentified>"),
                    str(destination),
                )

        if progress_callback:
            progress_callback(idx, total)

        if sha1:
            processed_libs.append(sha1)

    log.debug(
        "Finished downloading libraries: %d new / %d total", downloaded, total
    )
    return downloaded


def download_libraries_threaded(
    libraries: list[dict],
    *,
    progress_callback: Callable[[int, int], None] | None = None,
):
    total = len(libraries)
    downloaded = 0
    download_list: list[RunnableDownloader] = []

    if progress_callback:

        def passed_callback(i: int):
            nonlocal downloaded, total
            downloaded += i
            progress_callback(downloaded, total)

        progress_callback(0, total)
    else:

        def passed_callback(i: int):
            pass

    pool = QThreadPool.globalInstance()
    if not pool:
        log.warning("Couldn't get QThreadPool, downloading single-threaded")
        return download_libraries(
            libraries, progress_callback=progress_callback
        )

    for idx, lib in enumerate(libraries, 1):
        downloads: dict = lib.get("downloads", {})
        artifact: dict = downloads.get("artifact", {})

        if artifact:
            path: str = artifact.get("path", "")
            url = artifact.get("url", "")
            sha1 = artifact.get("sha1", "")
            # size = artifact.get("size", 0)
        else:
            name: str | None = lib.get("name")
            url: str | None = lib.get("url")
            if (not name) or (not url):
                log.warning("No artifact, name, or URL in library, skipping.")
                if progress_callback:
                    progress_callback(idx, total)
                continue
            sha1: str | None = lib.get("sha1")
            # size: int = lib.get("size", 0)
            url, path = parse_lib_path(url, name)

        if sha1 and sha1 in download_list:
            log.warning(
                "Duplicate libary %s; continuing.",
                lib.get("name", "<unidentified>"),
            )
            continue

        if (not url) and (not path):
            log.warning(
                "Manually retrieving URL and path for %s",
                lib.get("name", "<unidentified>"),
            )
            path_, url_, sha1_ = _get_lib_filepath(lib)
            if (not path_) or (not url_) or (not sha1_):
                pass
            else:
                path = path_
                url = url_
                sha1 = sha1_
            del path_, url_, sha1_

        if url and path:
            destination = os.path.join(paths.libraries, *path.split("/"))
            if os.path.isfile(destination):
                if not config.redownload_option:
                    log.info(
                        "Skipping download of library at '%s' "
                        "regardless of hash according to options.",
                        str(destination),
                    )
                    continue
            download_list.append(
                RunnableDownloader(
                    url, destination, sha1 or None, callback=passed_callback
                )
            )

    pool.setMaxThreadCount(CPU_THREADS)
    for dl in download_list:
        pool.start(dl)
    pool.waitForDone()
    if any(not a.success for a in download_list):
        raise BulkDownloadError.from_runnable_list(download_list)

    log.info(
        "Finished downloading libraries: %d new / %d total", downloaded, total
    )
    return downloaded


def _get_natives_classifier(lib: dict) -> str | None:
    """
    Determine the classifier for the platform-specific native JAR.

    Handles both `downloads.classifiers` and `natives` styles.
    """
    natives_map: dict = lib.get("natives", {})
    arch_bits = "64" if ARCH in ("x86_64", "arm64") else "32"
    if natives_map:
        classifier = natives_map.get(OS)
        if classifier:
            return classifier.replace("${arch}", arch_bits)
    classifiers = lib.get("downloads", {}).get("classifiers", {})
    if not classifiers:
        return None
    classifiers_keys = [*classifiers.keys()]
    if f"natives-{OS}" in classifiers_keys:
        return f"natives-{OS}"
    elif f"natives-{OS}-{arch_bits}" in classifiers_keys:
        return f"natives-{OS}-{arch_bits}"
    else:
        return None


def download_natives(libraries: list[dict]):
    """Download native libs for platform."""
    downloaded = 0

    for lib in libraries:
        classifier = _get_natives_classifier(lib)
        if not classifier:
            continue

        classifiers: dict = lib.get("downloads", {}).get("classifiers", {})
        native_info: dict = classifiers.get(classifier, {})
        if not native_info:
            continue

        path: str = native_info.get("path", "")
        url: str = native_info.get("url", "")
        sha1: str = native_info.get("sha1", "")
        size: int = native_info.get("size", 0)

        if url and path:
            destination = os.path.join(paths.libraries, *path.split("/"))
            if _download_file(url, destination, sha1, size):
                downloaded += 1

    return downloaded


def extract_natives(libraries: list[dict], natives_dir: str | os.PathLike):
    """
    Extract native libraries into the provided natives directory.

    If there's no real path, just give `LIBRARIES_DIR / <version_id>`

    Returns the natives directory.
    """
    if not isinstance(natives_dir, str):
        natives_dir = str(natives_dir)
    if not is_path_valid(natives_dir):
        raise ValueError(f"Bad directory path: {natives_dir!r}")
    if not os.path.isdir(natives_dir):
        os.makedirs(natives_dir, exist_ok=True)

    for lib in libraries:
        classifier = _get_natives_classifier(lib)
        if not classifier:
            continue

        classifiers: dict = lib.get("downloads", {}).get("classifiers", {})
        native_info: dict | None = classifiers.get(classifier)
        if not native_info:
            continue

        path: str = native_info.get("path", "")
        if not path:
            continue

        jar_path = os.path.join(paths.libraries, *path.split("/"))
        if not os.path.isfile(jar_path):
            log.warning("Couldn't find native at '%s'", jar_path)
            continue

        extract_rules: dict = lib.get("extract", {})
        exclude: list = extract_rules.get("exclude", [])

        try:
            with zipfile.ZipFile(jar_path, "r") as zip_file:
                for entry in zip_file.namelist():
                    skip = False
                    for pattern in exclude:
                        if entry.startswith(pattern):
                            skip = True
                            break
                    if skip:
                        continue
                    zip_file.extract(entry, natives_dir)
        except zipfile.BadZipFile:
            log.warning("Native at '%s' is bad archive", str(jar_path))

    return natives_dir


def build_classpath(libraries: list[dict], client_jar_path: str | os.PathLike):
    """
    Returns the entire JVM classpath string from the libraries and client JAR.
    """
    entries: list[str] = []
    if not isinstance(client_jar_path, str):
        client_jar_path = str(client_jar_path)
    if not is_path_valid(client_jar_path):
        raise ValueError(f"Bad file path: {client_jar_path!r}")

    for lib in libraries:
        artifact: dict = lib.get("downloads", {}).get("artifact")
        if artifact and artifact.get("path"):
            jar_path = os.path.join(
                paths.libraries, *artifact["path"].split("/")
            )
            if os.path.isfile(jar_path):
                if jar_path not in entries:
                    entries.append(jar_path)
                    continue
                else:
                    log.warning(
                        "Skipping duplicate library: '%s'",
                        lib.get("name", "<unidentified>"),
                    )
                    continue
        classifiers: dict = lib.get("downloads", {}).get("classifiers", {})
        if classifiers:
            native_name = _get_natives_classifier(lib)
            native_info = classifiers.get(native_name, {})
            if native_info:
                path = native_info.get("path", "")
                # name = native_info.get("name", "")
                if path:
                    jar_path = os.path.join(paths.libraries, *path.split("/"))
                    if os.path.isfile(jar_path):
                        entries.append(jar_path)
                        continue
        url, path = parse_lib_path(  # pylint: disable=W0612
            lib.get("url", ""), lib.get("name", "")
        )
        jar_path = os.path.join(paths.libraries, *path.split("/"))
        if os.path.isfile(jar_path):
            entries.append(str(jar_path))
        else:
            log.warning(
                "Couldn't find library '%s', skipping... (tried path '%s')",
                lib.get("name", "<unidentified>"),
                str(jar_path),
            )

    entries.append(client_jar_path)
    cp_string = CLASSPATH_SEPARATOR.join(entries)
    return cp_string
