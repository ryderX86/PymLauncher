"""
Common functions for downloading files.
"""

from typing import Literal, Callable, TypeVar, Iterable
from datetime import timedelta, datetime
from collections import Counter
from types import FunctionType
from pathlib import Path
import logging
import hashlib
import time
import lzma
import os

import requests
from PySide6.QtCore import QRunnable

from minecraftlauncher import SESSION, offline_mode

log = logging.getLogger(__name__)
T = TypeVar("T")


def _offline_mode_warning(func: FunctionType):
    def wrapped_func(*args, **kwargs):
        if offline_mode:
            log.warning(
                "'%s()' shouldn't have been called during offline mode!",
                func.__name__,
            )
        return func(*args, **kwargs)

    wrapped_func.__annotations__ = func.__annotations__
    wrapped_func.__defaults__ = func.__defaults__
    wrapped_func.__kwdefaults__ = func.__kwdefaults__
    return wrapped_func


def _download(
    url: str,
    max_retries: int,
    timeout: int,
    _retries: int = 0,
    *,
    sha: str | None = None,
) -> requests.Response:
    if _retries > max_retries:
        raise RuntimeError(f"Repeatedly failed to download from {url!r}")
    resp = SESSION.get(url, timeout=timeout)
    resp.raise_for_status()
    if isinstance(sha, str):
        if hashlib.sha1(resp.content).hexdigest() == sha:
            return resp
        else:
            log.warning(
                "Download from '%s' gave an unexpected hash! "
                "Retrying for %d/%d",
                url,
                _retries + 1,
                max_retries,
            )
            time.sleep(0.2)
            return _download(url, max_retries, timeout, _retries + 1, sha=sha)
    else:
        return resp


@_offline_mode_warning
def download(
    url: str,
    max_retries: int = 2,
    timeout: int = 30,
    *,
    sha: str | None = None,
):
    """
    Attempts to download a file to memory using `requests.get()`, returning the
    object if successful, else retrying up to `max_retries:int` (default: `2`)
    times.

    If `hash` is `str`, then the SHA1 will be checked upon download completion.
    If it doesn't match, the download will be failed and will retry
    automatically, counting as a failed download and using a retry.
    """
    if isinstance(sha, str) and not sha:
        sha = None
    return _download(url, max_retries, timeout, sha=sha)


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
    real_max_age: float = (datetime.now() - max_age).timestamp()
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
    threads_quit = False
    sleep_time = 0.0

    _url: str
    """File download URL"""
    _path: str | os.PathLike
    """File final location"""
    _hash: str | None
    """File hash to check against"""
    _override: bool
    """Should we override the file? (default: `False`)"""
    _lzma: bool

    log = log.getChild("RunnableDownloader")

    @_offline_mode_warning
    def __init__(
        self,
        url: str,
        path: os.PathLike | str,
        sha1: str | None = None,
        override: bool = False,
        mkdir: bool = True,
        use_lzma: bool = False,
        callback: Callable[[int], None] | None = None,
        check_hash: bool = True,
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
        after the file has been downloaded and written to disk.
        """
        super().__init__()
        self._url = url
        self._path = path
        self._file_exists = os.path.isfile(path)
        if not self._file_exists:
            parent = os.path.dirname(path)
            if not os.path.isdir(parent):
                if not mkdir:
                    raise FileNotFoundError(self._path)
                try:
                    os.makedirs(parent, exist_ok=True)
                except Exception as err:
                    raise ValueError(
                        f"Invalid path given for download: {str(self._path)}"
                    ) from err
        self._hash = sha1
        self._override = override
        self._lzma = use_lzma
        self._callback = callback
        self._check_hash = check_hash
        self.last_exception: Exception | None = None
        self.success: bool | None = None

    def _check_sha1(self):
        if not self._hash:
            return True
        return _check_file_sha1(self._path, self._hash)

    @property
    def needs_download(self) -> bool:
        if self._hash and os.path.isfile(self._path):
            if self._check_sha1():
                return False
        return True

    def run(self):
        if self.threads_quit:
            self.log.debug("Quitting thread early")
            return
        if self._check_hash and self._file_exists:
            if self._check_sha1():
                self.success = True
                return
            self.log.debug("File exists but SHA1 doesn't match, deleting.")
            os.unlink(self._path)
        resp = None
        self.success = False
        try:
            resp = SESSION.get(self._url, timeout=30)
            resp.raise_for_status()
        except Exception as err:
            self.last_exception = err
            self.log.error(
                "Failed to get file from %r: %r", self._url, str(err)
            )
            raise err
        else:
            self.sleep_time = 0
            if self._lzma:
                content = lzma.decompress(resp.content)
            else:
                content = resp.content
            if self._hash:
                sha1 = hashlib.sha1(content).hexdigest()
                if sha1 != self._hash:
                    self.last_exception = RuntimeError(
                        "SHA mismatch occured after download"
                    )
                    self.log.error("Download failed, retrying (SHA-1 mismatch)")
                    resp = None
            else:
                log.warning(
                    "No SHA1 provided for file downloaded at '%s'",
                    self._path,
                )
            with open(self._path, "wb") as f:
                f.write(content)
            print("Download done")
            self.success = True
            if self._callback:
                self._callback(1)
            return

    @property
    def failed(self):
        return self.success is False

    @classmethod
    def kill_all(cls):
        cls.threads_quit = True

    @property
    def download_successful(self):
        """
        If this is `None`, the download either hasn't started or was aborted
        due to SHA matching
        """
        return self.success


class BulkDownloadError(Exception):
    primary_exception: Exception | None
    """Exception which occured most frequently in the list"""

    def __init__(self, *exceptions: Exception):
        super().__init__("Error(s) occured in bulk download")
        self.exception_list = [*exceptions]
        """All exceptions passed to this exception"""

        if self.exception_list:
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
        self._iter_idx_ = 0
        return self

    def __next__(self):
        i = self._iter_idx_
        if i >= len(self.exception_list):
            raise StopIteration
        self._iter_idx_ += 1
        return self.exception_list[i]

    @classmethod
    def from_runnable_list(cls, dl_list: list[RunnableDownloader]):
        exc_list = []
        for dl in dl_list:
            if not dl.success and dl.last_exception:
                exc_list.append(dl.last_exception)
        return cls(*exc_list)
