from collections.abc import Iterable
from enum import StrEnum
from io import BufferedReader, BytesIO
import hashlib
import logging
import os
import zipfile

from PySide6.QtCore import (
    QMutex,
    Qt,
    QThread,
    QWaitCondition,
    Signal,
)

from launcher import config, lifecycle
from launcher.back.download_helpers import iter_lzma_stream
from launcher.datatypes.game_version.jar_file import JarFile
from launcher.exceptions.back import LZMAEarlyQuitError
from launcher.networking import make_request
from launcher.offline import offline_man

log = logging.getLogger(__name__)


class HashType(StrEnum):
    # insecure-ish
    SHA1 = "SHA-1"
    MD5 = "MD5"
    # secure
    SHA224 = "SHA224"
    SHA256 = "SHA256"
    SHA384 = "SHA384"
    SHA512 = "SHA512"


def get_file_hash(file: str | BufferedReader, hash_type: HashType):
    close: bool
    if isinstance(file, str):
        file = open(file, "rb")
        close = True
    else:
        close = False
    file.seek(0)
    hash_ = hashlib.file_digest(file, hash_type).hexdigest()
    if close:
        file.close()
    return hash_


class GameJarDownloaderThread(QThread):
    progress = Signal(int)
    skipped = Signal()
    exception = Signal(Exception)

    def __init__(self, jar: JarFile):
        super().__init__()
        self.jar = jar
        self.was_skipped = None

    def run(self):
        try:
            self._download()
        except Exception as err:
            self.exception.emit(err)
            raise err

    def _download(self):
        fp = self.jar.path
        if os.path.isfile(fp):
            with open(fp, "rb") as file:
                sha1 = hashlib.file_digest(file, "sha1").hexdigest()
            if sha1 == self.jar.sha1:
                self.skipped.emit()
                self.was_skipped = True
                return
        elif not os.path.isdir((p := os.path.split(fp)[0])):
            os.makedirs(p, exist_ok=True)
        self.was_skipped = False

        try:
            resp = make_request("get", self.jar.url, preload_response=False)
        except Exception as err:
            offline_man.check_requests_error(err)
            self.exception.emit(err)
            raise err

        hash_obj = hashlib.sha1()
        buffer = BytesIO()

        try:
            for chunk in resp.stream(None):
                buffer.write(chunk)
                hash_obj.update(chunk)
                self.progress.emit(len(chunk))
        except Exception as err:
            offline_man.check_requests_error(err)
            resp.drain_conn()
            raise err

        if (nh := hash_obj.hexdigest()) != self.jar.sha1:
            err = RuntimeError(
                f"Game JAR failed SHA1 check: Expected {self.jar.sha1!r}, "
                f"got {nh!r}"
            )
            self.exception.emit(err)
            raise err

        with open(fp, "wb") as file:
            file.write(buffer.getvalue())


class Download:
    """
    Small, decently memory efficient dataclass-esque detail container for
    download information
    """

    __slots__ = (
        "url",
        "file_path",
        "hash_type",
        "hash_list",
        "lzma",
        "virtual",
        "size",
    )

    # instance attrs
    url: str
    file_path: str
    hash_type: HashType | None
    hash_list: set[str] | None
    lzma: bool
    virtual: str | None
    size: int
    native_library = False

    def __init__(
        self,
        url: str,
        file_path: str,
        hash_list: Iterable[str] | str | None = None,
        hash_type: HashType | None = None,
        lzma: bool = False,
        virtual: str | None = None,
        size: int = 1,
    ):
        match hash_list:
            case set():
                self.hash_list = hash_list
            case str():
                self.hash_list = {hash_list}
            case None:
                self.hash_list = None
            case _:
                self.hash_list = set(hash_list)

        self.hash_type = hash_type
        self.file_path = file_path
        self.url = url
        self.lzma = lzma
        self.virtual = virtual
        self.size = size


class NativeDownload(Download):
    __slots__ = ("excluded_patterns", "natives_path")
    native_library = True

    def __init__(
        self,
        url: str,
        file_path: str,
        natives_path: str,
        hash_list: Iterable[str] | str | None = None,
        hash_type: HashType | None = None,
        lzma: bool = False,
        virtual: str | None = None,
        size: int = 1,
        excluded_patterns: Iterable[str] | None = None,
    ):
        super().__init__(
            url, file_path, hash_list, hash_type, lzma, virtual, size
        )
        self.excluded_patterns = excluded_patterns or set()
        self.natives_path = natives_path


class DownloadQueue:
    """
    Thread-safe queue for multi-threaded downloads.
    """

    __slots__ = ("_downloads", "_mutex", "_still_adding", "_wait_condition")

    _downloads: set[Download]
    _mutex: QMutex
    _still_adding: bool
    _wait_condition: QWaitCondition

    def __init__(self):
        self._downloads = set()
        self._still_adding = False
        self._mutex = QMutex()
        self._wait_condition = QWaitCondition()

    def begin_append(self):
        self._mutex.lock()
        self._still_adding = True
        self._mutex.unlock()

    def end_append(self):
        self._mutex.lock()
        self._still_adding = False
        if not self._downloads:
            log.debug("No downloads left after append, releasing all threads")
            self._wait_condition.wakeAll()
        self._mutex.unlock()

    def append(self, dl: Download):
        self._mutex.lock()
        try:
            self._downloads.add(dl)
            self._wait_condition.wakeOne()
        finally:
            self._mutex.unlock()

    def get_download(self) -> Download:
        self._mutex.lock()
        try:
            if self._still_adding and not self._downloads:
                self._wait_condition.wait(self._mutex)
            elif self._downloads:
                return self._downloads.pop()
            raise StopIteration
        finally:
            self._mutex.unlock()


class DownloaderThread(QThread):
    exception = Signal(Exception)
    downloaded_file = Signal(str, int)  # file name, size
    skipped_file = Signal(str, int)
    logger = log.getChild("DownloaderThread")

    def __init_subclass__(cls) -> None:
        cls.logger = log.getChild(cls.__name__)
        return super().__init_subclass__()

    def __init__(self, queue: DownloadQueue | None = None, parent=None):
        super().__init__(parent)
        self._queue = queue
        lifecycle.shutting_down.connect(
            self.requestInterruption, Qt.ConnectionType.DirectConnection
        )

    def run(self):
        try:
            self._do_downloads()
        except Exception as err:
            self.exception.emit(err)
            raise err

    def start(
        self, priority: QThread.Priority = QThread.Priority.NormalPriority
    ) -> None:
        if not self._queue:
            raise RuntimeError("Cannot start thread without a queue")
        return super().start(priority)

    def set_queue(self, queue: DownloadQueue | None):
        self._queue = queue

    def _do_downloads(self):
        assert self._queue
        while True:
            if self.isInterruptionRequested():
                self.logger.debug("Interruption requested, stopping")
                break
            try:
                self.download(self._queue.get_download())
            except StopIteration:
                break

    def download(self, inf: Download):
        # first check if we even need to download
        if os.path.exists(inf.file_path):
            if inf.hash_list:
                # we really won't have one without the other
                assert inf.hash_type
                if (
                    h := get_file_hash(inf.file_path, inf.hash_type)
                ) in inf.hash_list:
                    self.skipped_file.emit(inf.file_path, inf.size)
                    return
                else:
                    log.warning(
                        "%s mismatch: Expected any of %s, got %r.",
                        inf.hash_type,
                        ", ".join((repr(a) for a in inf.hash_list)),
                        h,
                    )
            # check the config option
            elif config.redownload_option <= 0:
                # no redownloads, we leave
                self.skipped_file.emit(inf.file_path, inf.size)
                return
        elif not os.path.isdir((d := os.path.split(inf.file_path)[0])):
            os.makedirs(d, exist_ok=True)

        try:
            resp = make_request("get", inf.url, preload_response=False)
        except Exception as err:
            offline_man.check_requests_error(err)
            raise err

        if inf.hash_list:
            assert inf.hash_type
            hash_obj = hashlib.new(inf.hash_type)
        else:
            hash_obj = hashlib.new("md5")
        buffer = BytesIO()

        if inf.lzma:
            try:
                for chunk in iter_lzma_stream(resp):
                    buffer.write(chunk)
                    if hash_obj:
                        hash_obj.update(chunk)
            except LZMAEarlyQuitError as err:
                self.logger.error("Download failed, EOF never reached.")
                raise err
            except Exception as err:
                offline_man.check_requests_error(err)
                raise err
        else:
            try:
                for chunk in resp.stream(None):
                    buffer.write(chunk)
                    if hash_obj:
                        hash_obj.update(chunk)
            except Exception as err:
                offline_man.check_requests_error(err)
                raise err

        # now that we're done by this point in code, check the hash:
        if inf.hash_list and (
            (h := hash_obj.hexdigest()) not in inf.hash_list  # type: ignore
        ):
            assert inf.hash_list
            error = RuntimeError(
                f"Non-matching {inf.hash_type}: "
                f"Expected any of {', '.join((repr(a) for a in inf.hash_list))}, "
                f"got {h}"
            )
            raise error

        # success! rewrite the file and maybe copy to the virtual path
        with open(inf.file_path, "wb") as file:
            file.write(buffer.getvalue())

        if isinstance(inf, NativeDownload):
            self.extract_native(inf)

        self.downloaded_file.emit(inf.file_path, inf.size)
        return

    def extract_native(self, inf: NativeDownload):
        if not os.path.isfile(inf.file_path):
            self.logger.warning(
                "Could not find native library at path %r. "
                "The game may not be able to launch.",
                inf.file_path,
            )
            return

        try:
            with zipfile.ZipFile(inf.file_path, "r") as zf:
                for entry in zf.namelist():
                    skip = False
                    for p in inf.excluded_patterns:
                        if entry.startswith(p):
                            skip = True
                            break
                    if skip:
                        continue
                    zf.extract(entry, inf.natives_path)
        except zipfile.BadZipFile as err:
            log.warning(
                "JAR file at %r couldn't be opened as a ZIP",
                inf.file_path,
                exc_info=err,
            )
            return
        except Exception as err:
            log.error(
                "Failed to extract natives from %r:",
                inf.file_path,
                exc_info=err,
            )
            log.warning(
                "Skipping natives extraction for this library. "
                "Game may not be able to start."
            )
            return
