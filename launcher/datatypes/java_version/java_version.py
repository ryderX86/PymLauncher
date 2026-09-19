from collections.abc import Callable
import logging
import os

from launcher.back.download_helpers import RunnableDownloader
from launcher.paths import paths

from .java_file import JavaFile

log = logging.getLogger(__name__)


class JavaVersion:
    __slots__ = (
        "name",
        "version_id",
        "files",
        "directories",
    )

    def __init__(
        self,
        name: str,
        version_id: str,
        files: list[JavaFile],
        directories: list[str],
    ):
        self.name = name
        self.version_id = version_id
        self.files = files
        self.directories = directories

    @classmethod
    def parse(cls, version: str, version_id: str, files: dict[str, dict]):
        if "files" in files and "type" not in files["files"]:
            files = files["files"]
        file_list: list[JavaFile] = [
            JavaFile.parse(version, name, file)
            for name, file in files.items()
            if file.get("type") == "file"
        ]
        directories = [
            os.path.join(paths.jre_path, name, *name.split("/"))
            for name, file in files.items()
            if file.get("type") == "directory"
        ]
        return cls(version, version_id, file_list, directories)

    @property
    def executables(self) -> set[JavaFile]:
        """All files that need to be marked as exeuctable on POSIX systems."""
        return set(f for f in self.files if f.executable)

    def get_downloads(
        self, callback: Callable[[int, int], None] | None = None
    ) -> set[RunnableDownloader]:
        """Returns a list of runnable downloaders for all files."""
        dls = set()
        lzma_count = 0
        raw_count = 0
        file_count = len(self.files)
        for file in self.files:
            file_path = file.path
            if file.lzma:
                lzma_count += 1
                url = file.lzma.url
                sha1 = file.raw.sha1
                use_lzma = True
            else:
                raw_count += 1
                url = file.raw.url
                sha1 = file.raw.sha1
                use_lzma = False

            check_hash = bool(sha1)
            dls.add(
                RunnableDownloader(
                    url,
                    file_path,
                    sha1,
                    use_lzma,
                    (
                        (lambda c, t=file_count: callback(c, t))
                        if callback
                        else None
                    ),
                    check_hash,
                )
            )
        log.debug(
            "Java %s: Files using LZMA: %d; Files without compression: %d",
            self.version_id,
            lzma_count,
            raw_count,
        )
        return dls

    def create_directories(self):
        for dir_ in self.directories:
            if os.path.isdir(dir_):
                continue
            os.makedirs(dir_, exist_ok=True)
