"""
Common functions for downloading files.
"""

from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import (
    Callable,
    Generator,
    Iterable,
    Literal,
    TypeVar,
    assert_never,
)
import hashlib
import logging
import lzma
import os
import time

from PySide6.QtCore import QRunnable
from urllib3.response import BaseHTTPResponse

from launcher import get_exit_status
from launcher.config import config
from launcher.exceptions.back import LZMAEarlyQuitError
from launcher.exceptions.network import (
    HTTPStatusCodeError,
    WrappedUL3Exception,
)
from launcher.functions import is_path_valid
from launcher.networking import make_request
from launcher.offline import offline_man

log = logging.getLogger(__name__)
T = TypeVar("T")


def iter_lzma_stream(resp: BaseHTTPResponse) -> Generator[bytes]:
    decompressor = lzma.LZMADecompressor()
    try:
        for chunk in resp.stream(None):
            uncompressed_data = decompressor.decompress(chunk)

            if uncompressed_data:
                yield uncompressed_data
    finally:
        # pylint: disable-next=using-constant-test
        if decompressor.eof:
            resp.release_conn()
        else:
            resp.drain_conn()
    if not decompressor.eof:
        raise LZMAEarlyQuitError("EOF was never reached")


def _check_file_sha1(path: str | os.PathLike, sha1: str):
    """return `True` if the file exists & sha1 matches"""
    if not os.path.isfile(path):
        return False
    if not sha1:
        return True
    with open(path, "rb") as file:
        file_hash = hashlib.sha1(file.read()).hexdigest()
    return bool(file_hash == sha1)


def _check_file_size(path: str | os.PathLike, size: int):
    if not size:
        log.warning("check_file_size() called without a valid size!")
        return True
    if not os.path.isfile(path):
        return False
    return os.stat(path).st_size == size


def file_exists_or_age(
    path: str | Path, max_age: float | int | timedelta = 86400.0
):
    """
    Return `True` if the file exists and is under the age specified in
    `max_age` (seconds).
    """
    if not os.path.isfile(path):
        return False
    if isinstance(max_age, (int, float)):
        max_age = timedelta(seconds=max_age)
    real_max_age: float = time.time() - max_age.total_seconds()
    return os.stat(path).st_mtime > real_max_age


def should_download_file(
    path: str | os.PathLike,
    *,
    sha: str | None = None,
    size: int | None = None,
    hash_type: Literal["sha1", "sha256"] = "sha1",
):
    """
    Checks if a file should be downloaded based on either existance, hash,
    size, or some/all of the above.

    **WARNING:** SHA-256 not implemented yet.
    """
    if not os.path.isfile(path):
        return True
    if sha:
        match hash_type:
            case "sha1":
                hash_match = _check_file_sha1(path, sha)
            case "sha256":
                raise NotImplementedError()
            case _:
                raise ValueError("hash_type should be 'sha1' or 'sha256'")
    else:
        hash_match = True
    if size:
        size_match = _check_file_size(path, size)
    else:
        size_match = True
    return not bool(hash_match and size_match)  # pylint: disable=E0606


def filter_downloads(
    downloads: list[T], filters: Iterable[Callable[[list[T]], list[T]]]
):
    for f in filters:
        downloads = f(downloads)
    return downloads


class DownloadError(Exception):
    def __init__(
        self, url: str, path: os.PathLike | str, msg: str | None = None
    ):
        if isinstance(path, Path):
            path = str(path.resolve().absolute())
        else:
            path = os.path.abspath(path)
        if self.__context__ and not msg:
            msg = (
                f"Failed to download file from URL {url!r} to {path!r} "
                f"(original exception: {type(self.__context__).__name__})"
            )
        elif not msg:
            msg = f"Failed to download file from URL {url!r} to {path!r}"
        super().__init__(msg, url, path)
        if isinstance(self.__context__, Exception):
            self.__traceback__ = self.__context__.__traceback__
        self.destination = path
        self.url = url


class RunnableDownloader(QRunnable):
    sleep_time = 0.0

    _url: str
    """File download URL"""
    _path: str
    """File final path"""
    _vpath: str | None
    """File final location for legacy assets"""
    _hash: set[str] | None
    """File hash to check against"""
    _override: bool
    """Should we override the file? (default: `False`)"""
    _lzma: bool
    """Is the download coming in compressed with LZMA?"""
    _callback: Callable[[int], None] | None
    """Post-download function to run"""
    _should_check_hash: bool
    """Do we check hash? (SHA1)"""
    last_exception: BaseException | None
    success: bool | None
    _invalid_download_count: int
    _failed_downloads: int
    """How many times the download generically failed."""
    _downloaded_file: bool

    log = log.getChild("RunnableDownloader")

    def __init__(
        self,
        url: str,
        path: os.PathLike | str,
        sha1: str | Iterable[str] | None = None,
        use_lzma: bool = False,
        callback: Callable[[int], None] | None = None,
        check_hash: bool | None = None,
        *,
        vpath: str | os.PathLike | None = None,
    ):
        """
        Class for a single file to download in a bulk.

        If checking a non-SHA1 hash, override the `hash_check()`
        variable with another hash check function.

        If the parent folder doesn't exist yet, and `mkdir` is `True`,
        the folder will be created upon class init. Otherwise, `__init__()`
        will raise `FileNotFoundError`.

        If `check_hash` is `True`, the file hash will be checked before
        attempting to download it; otherwise the hash will only be checked
        after the file has been downloaded and written to disk (defaults to
        `True` if a hash is provided)
        """
        super().__init__()
        self._url = url
        self._path = str(path).rstrip("\\/")
        self._vpath = str(vpath).rstrip("\\/") if vpath else None
        if not is_path_valid(self._path):
            raise ValueError(f"Invalid path: {self._path!r}")
        if self._vpath:
            if not is_path_valid(self._vpath):
                raise ValueError(f"Invalid path: {self._vpath!r}")
            self._file_exists = os.path.isfile(path) and os.path.isfile(
                self._vpath
            )
        else:
            self._file_exists = os.path.isfile(path)
        match sha1:
            case str():
                self._hash = {sha1}
            case set():
                self._hash = sha1
            case None:
                self._hash = None
            case _ if isinstance(sha1, Iterable):
                self._hash = set(sha1)
            case _:
                assert_never(sha1)
        if sha1 and check_hash is None:
            check_hash = True
        elif check_hash is None:
            check_hash = False
        self._lzma = use_lzma
        self._callback = callback
        self._should_check_hash = check_hash
        self.last_exception = None
        self.success = None
        self._invalid_download_count = 0
        self._failed_downloads = 0
        self._downloaded_file = False
        if self._should_check_hash and not self._hash:
            raise ValueError(
                "should_check_hash set to True but no hash was provided"
            )

    def _check_sha1(self):
        if not os.path.isfile(self._path):
            return False
        elif not self._should_check_hash or not self._hash:
            if not config.redownload_option:
                self.log.debug(
                    "Skipping download since redownloading without a hash "
                    "isn't enabled"
                )
                return True
            return False
        with open(self._path, "rb") as f:
            filehash = hashlib.file_digest(f, "sha1").hexdigest()
        return filehash in self._hash

    def run(self):
        if get_exit_status():
            self.log.debug("Quitting thread early")
            return
        elif self.sleep_time:
            self.log.debug("Waiting for sleep timer")
            time.sleep(self.sleep_time)

        # check hash before trying to download the file
        if self._should_check_hash:
            if self._check_sha1():
                self.success = True
                if self._callback:
                    self._callback(1)
                return
            if self._file_exists:
                self.log.debug("File exists but SHA1 doesn't match, deleting.")
                os.unlink(self._path)

        # check/make directories
        if not os.path.isdir(os.path.dirname(self._path)):
            try:
                log.debug(
                    "Creating directory (plus non-existant parent "
                    "directories) at %r",
                    os.path.dirname(self._path),
                )
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
            except Exception as err:
                self.log.error(
                    "Failed to create directory at %r",
                    os.path.dirname(self._path),
                    exc_info=err,
                )
                self.last_exception = err
                self.success = False
                raise
        if self._vpath and not os.path.isdir(os.path.dirname(self._vpath)):
            try:
                log.debug(
                    "Creating directory (plus non-existant parent "
                    "directories) at %r",
                    os.path.dirname(self._vpath),
                )
                os.makedirs(os.path.dirname(self._vpath), exist_ok=True)
            except Exception as err:
                self.log.error(
                    "Failed to create directory at %r",
                    os.path.dirname(self._path),
                    exc_info=err,
                )
                self.last_exception = err
                self.success = False
                raise

        self.download()
        return

    def download(self):
        if get_exit_status():
            log.debug("Quitting download early")
            return
        elif self.sleep_time:
            time.sleep(self.sleep_time)

        # download the file
        self.success = False
        try:
            resp = make_request("get", self._url, preload_response=False)
        except HTTPStatusCodeError as err:
            log.error(
                "HTTP %d - %r returned by %r:",
                err.code,
                err.desc,
                self._url,
                exc_info=err,
            )
            if err.code == 404:
                if self._file_exists:
                    log.info("File exists, have to assume it works.")
                    self.success = True
                    return
            raise
        except WrappedUL3Exception as err:
            # check if we need to raise before anything
            if not err.should_retry:
                self.last_exception = err
                log.error(
                    "Error in response from %r:", self._url, exc_info=err
                )
                raise err

            self._failed_downloads += 1
            log.info("Retrying after 5s.")
            type(self).sleep_time = 5
            return self.download()
        except Exception as err:
            offline_man.check_requests_error(err)
            self.last_exception = err
            self.log.error(
                "Failed to get file from %r:", self._url, exc_info=err
            )
            type(self).sleep_time = 0.2
            raise err
        type(self).sleep_time = 0

        files = {open(self._path, "wb")}
        if self._vpath:
            files.add(open(self._vpath, "wb"))
        sha1 = hashlib.sha1()
        try:
            if not self._lzma:
                for chunk in resp.stream(None):
                    for f in files:
                        f.write(chunk)
                    sha1.update(chunk)
            else:
                for chunk in iter_lzma_stream(resp):
                    for f in files:
                        f.write(chunk)
                    sha1.update(chunk)
        except LZMAEarlyQuitError as err:
            log.error("Download failed, EOF never reached by LZMA module.")
            self._failed_downloads += 1
            if self._failed_downloads > 2:
                raise err
            else:
                return self.download()
        except Exception as err:
            log.debug("Error occured, releasing connection")
            resp.release_conn()
            offline_man.check_requests_error(err)
            self.last_exception = err
            self.log.error(
                "Failed to get file from %r:", self._url, exc_info=err
            )
            self._failed_downloads += 1
            type(self).sleep_time = 0.2
            if not offline_man.offline and self._failed_downloads <= 2:
                time.sleep(self.sleep_time)
                return self.download()
            else:
                raise err
        finally:
            for f in files:
                f.close()

        # check the download
        if self._hash:
            if sha1.hexdigest() not in self._hash:
                self.last_exception = RuntimeError(
                    "SHA mismatch occured after download"
                )
                if self._invalid_download_count > 5:
                    err = RuntimeError(
                        f"Failed to download from {self._url!r}, "
                        "max retries exceeded. "
                        "(SHA-1 mismatch, expected any of "
                        f"{tuple(self._hash)!r}, got "
                        f"{sha1.hexdigest()!r})"
                    )
                    self.last_exception = err
                    raise err from self.last_exception
                self._invalid_download_count += 1
                self.log.error("Download failed, retrying (SHA-1 mismatch)")
                resp = None
                return self.download()
        else:
            log.debug(
                "No SHA1 provided for file downloaded at '%s'",
                self._path,
            )
        self.success = True
        self._downloaded_file = True
        if self._callback:
            self._callback(1)
        return

    @property
    def hash(self) -> set[str] | None:
        return self._hash

    @property
    def failed(self):
        return self.success is False

    @property
    def download_successful(self):
        """
        If this is `None`, the download either hasn't started or was aborted
        due to SHA matching
        """
        return self.success

    @property
    def downloaded_file(self) -> bool:
        """
        Whether or not the file was downloaded or not.

        Used for debugging to determine file count vs. actual downloaded,
        since SHA-1 matches won't be overridden.
        """
        return self._downloaded_file


class BulkDownloadError(Exception):
    primary_exception: Exception | None
    """Exception which occured most frequently in the list"""

    def __init__(self, *exceptions: Exception):
        super().__init__("Error(s) occured in bulk download")
        self.exception_list = [*exceptions]
        """All exceptions passed to this exception"""

        if self.exception_list:
            # pylint: disable-next=unsubscriptable-object
            self.primary_exception = Counter(
                self.exception_list
            ).most_common()[0][0] # fmt: skip
        else:
            self.primary_exception = None
        self._iter_idx_ = 0
        for i in self.all_messages():
            self.add_note(i)

    def all_messages(self):
        texts = ["List of exceptions and their messages:"]
        for err in self.exception_list:
            texts.append(f"    {type(err).__name__}{err.args!r}: {err!r}")
        if not self.exception_list:
            texts = ["<no exceptions were passed>"]
        return texts

    def __iter__(self):
        """Return an iterator of exceptions contained in the class"""
        self._iter_idx_ = 0
        return self

    def __next__(self):
        i = self._iter_idx_
        if i >= len(self.exception_list):
            raise StopIteration
        self._iter_idx_ += 1
        return self.exception_list[i]

    @classmethod
    def from_runnable_list(cls, dl_list: Iterable[RunnableDownloader]):
        exc_list = []
        for dl in dl_list:
            if dl.success is not None and (
                dl.last_exception and not dl.success
            ):
                exc_list.append(dl.last_exception)
        return cls(*exc_list)
