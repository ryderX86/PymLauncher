import hashlib
import logging
import os

from launcher.paths import paths

log = logging.getLogger(__name__)


class JavaFileDownload:
    __slots__ = ("jre_version", "is_lzma", "sha1", "size", "url", "file_path")

    def __init__(
        self,
        jre_version: str,
        file_path: str,
        is_lzma: bool,
        sha1: str,
        size: int,
        url: str,
    ):
        self.jre_version = jre_version
        self.is_lzma = is_lzma
        self.sha1 = sha1
        self.size = size
        self.url = url
        self.file_path = file_path

    def available(self):
        if self.is_lzma:
            raise RuntimeError(
                "LZMA will never return available. Check the raw download."
            )
        if not os.path.isfile(self.file_path):
            return False
        with open(self.file_path, "rb") as file:
            file_bytes = file.read()
        existing_sha1 = hashlib.sha1(file_bytes).hexdigest()
        return self.sha1 == existing_sha1


class JavaFile:
    __slots__ = ("jre_version", "lzma", "raw", "executable", "path")

    def __init__(
        self,
        jre_version: str,
        raw: JavaFileDownload,
        lzma: JavaFileDownload | None = None,
        executable: bool = False,
    ):
        self.jre_version = jre_version
        self.raw = raw
        self.path = self.raw.file_path
        self.lzma = lzma
        self.executable = executable

    def available(self):
        return self.raw.available()

    @classmethod
    def parse(cls, jre_version: str, file_name: str, file: dict):
        if file.get("type") != "file":
            raise ValueError(
                f"Non-file type provided for {file_name!r} "
                f"(expected {{'type': 'file'}}, got "
                f"{{'type': {file.get("type")!r}}})"
            )
        if "downloads" not in file:
            raise ValueError(f"Bad file info for {file_name!r}")
        file_path = os.path.join(
            paths.jre_path, jre_version, *file_name.split("/")
        )
        raw_download = file.get("downloads", {}).get("raw")
        try:
            raw = JavaFileDownload(
                jre_version,
                file_path,
                False,
                raw_download["sha1"],
                raw_download.get("size", 0),
                raw_download["url"],
            )
        except KeyError as err:
            raise ValueError(
                f"Raw download information for {file_name!r} "
                "missing raw download info"
            ) from err
        if not raw_download:
            raise RuntimeError(f"No raw download provided for {file_name!r}")
        lzma_download = file.get("downloads", {}).get("lzma")
        lzma = None
        if lzma_download:
            if {"sha1", "size", "url"}.issubset(lzma_download.keys()):
                lzma = JavaFileDownload(
                    jre_version,
                    file_path,
                    True,
                    lzma_download["sha1"],
                    lzma_download["size"],
                    lzma_download["url"],
                )
            else:
                log.warning(
                    "LZMA download is missing info (present keys: %r, "
                    "expected 'sha1', 'size', 'url')",
                    lzma_download.keys(),
                )
        return cls(jre_version, raw, lzma, file.get("executable", False))
