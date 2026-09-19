from xml.etree import ElementTree
from xml.parsers import expat
import hashlib
import logging
import os

from launcher import SESSION
from launcher.back.download_helpers import RunnableDownloader
from launcher.paths import paths

log = logging.getLogger(__name__)

_LOG_STR_PATTERN = r"[%d{HH:mm:ss}] [%t/%level]: %msg{nolookups}%n"


class Log4JConfig:
    __slots__ = (
        "launch_arg",
        "file_name",
        "sha1",
        "size",
        "url",
        "type",
        "file_name_patched",
    )

    def __init__(
        self,
        launch_arg: str,
        file_name: str,
        sha1: str,
        size: int,
        url: str,
        type_: str,
    ):
        self.launch_arg = launch_arg
        self.file_name = file_name
        self.sha1 = sha1
        self.size = size
        self.url = url
        self.type = type_
        stem, suffix = os.path.splitext(self.path)
        self.file_name_patched = f"{stem}_patched{suffix}"

    @property
    def path(self):
        return os.path.join(paths.assets_log_configs, self.file_name)

    @property
    def path_patched(self):
        return os.path.join(paths.assets_log_configs, self.file_name_patched)

    def available(self):
        if os.path.isfile(self.path):
            with open(self.path, "rb") as file:
                sha1 = hashlib.sha1(file.read()).hexdigest()
            return sha1 == self.sha1
        return False

    def needs_patch(self):
        """
        Check if the logging config needs a patch or not.

        Raises a FileNotFoundError if called while the file doesn't exist.
        Always make sure `available()` returns `True` first, or download it.
        """
        if not self.available():
            err = FileNotFoundError(
                "Log4J config was not downloaded prior to running "
                "Log4JConfig().needs_patch() function"
            )
            err.filename = self.path
        with open(self.path, "r") as file:
            txt = file.read()
        # cheap-ish way to check, still iterates but i expect it to be
        # faster than parsing the XML
        return "XMLLayout" in txt

    def available_patched(self):
        if not self.available():
            return False
        if os.path.isfile(self.path_patched):
            with open(self.path_patched, "r") as file:
                txt = file.read()
            return "XMLLayout" not in txt
        return False

    def download(self):
        if self.available():
            log.debug("Skipping Log4J config download, up to date already.")
            return
        resp = SESSION.get(self.url)
        with open(self.path, "wb") as file:
            file.write(resp.content)
        log.info("Downloaded Log4J config at %r", self.path)
        return

    def downloader(self, callback=None):
        return RunnableDownloader(
            self.url, self.path, self.sha1, callback=callback
        )

    def patch(self):
        if not self.available():
            err = FileNotFoundError(
                f"Log config at {self.path!r} does not exist."
            )
            err.filename = self.path
            raise err

        with open(self.path, "r") as file:
            txt = file.read()

        if "XMLLayout" not in txt:
            log.debug(
                "'XMLLayout' not present in file text at all, skipping patch"
            )
            return self.path

        try:
            xml = ElementTree.fromstring(txt)
        except expat.error as err:
            log.error("Failed to read Log4J XML config:", exc_info=err)
            raise err

        layout_elements = [
            *xml.iter("XMLLayout"),
            *xml.iter("LegacyXMLLayout"),
        ]
        if not layout_elements:
            log.debug("No XMLLayout elements, skipping patch")
            return self.path

        for e in layout_elements:
            e.clear()

            e.tag = "PatternLayout"
            e.set("pattern", _LOG_STR_PATTERN)
        log.debug(
            "Patched Log4J config at %r with pattern layout, "
            "replacing %d tags",
            self.path,
            len(layout_elements),
        )
        stem, suffix = os.path.splitext(self.path)
        new_path = f"{stem}_patched{suffix}"
        with open(new_path, "wb") as fb:
            fb.write(ElementTree.tostring(xml))
        return new_path
