"""
Common functions for downloading files.
"""

from typing import Literal, Callable, TypeVar, Iterable
from collections import Counter
from datetime import timedelta
from types import FunctionType
from pathlib import Path
import logging
import hashlib
import time
import lzma
import os

import requests
from PySide6.QtCore import QRunnable

from minecraftlauncher import SESSION, get_exit_status
from minecraftlauncher.offline import offline_man
from minecraftlauncher.config import config
from minecraftlauncher.functions import is_path_valid

log = logging.getLogger(__name__)
T = TypeVar("T")


def _offline_mode_warning(func: FunctionType):
    def wrapped_func(*args, **kwargs):
        if offline_man.offline:
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
    Attempts to download a file to memory using
    `minecraftlauncher.session.get()`, returning the object if successful, else
    retrying up to `max_retries:int` (default: `2`) times.

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
    _path: str | os.PathLike
    """File download URL for game versions using the legacy assets format"""
    _vpath: str | os.PathLike | None
    """File final location"""
    _hash: str | None
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
    _downloaded_file: bool

    log = log.getChild("RunnableDownloader")

    @_offline_mode_warning
    def __init__(
        self,
        url: str,
        path: os.PathLike | str,
        sha1: str | None = None,
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
        self._path = path
        self._vpath = vpath
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
        self._hash = sha1
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
        self._downloaded_file = False
        if self._should_check_hash and not self._hash:
            raise ValueError(
                "should_check_hash set to True but no hash was provided"
            )

    def _check_sha1(self):
        if not os.path.isfile(self._path):
            return False
        elif not self._should_check_hash:
            if not config.redownload_option:
                self.log.debug(
                    "Skipping download since redownloading without a hash "
                    "isn't enabled"
                )
                return True
            return False
        with open(self._path, "rb") as file:
            content = file.read()
        return self._hash == hashlib.sha1(content).hexdigest()

    def run(self):
        if get_exit_status():
            self.log.debug("Quitting thread early")
            return
        elif self.sleep_time:
            time.sleep(self.sleep_time)

        # check hash before trying to download the file
        if self._should_check_hash and self._file_exists:
            if self._check_sha1():
                self.success = True
                if self._callback:
                    self._callback(1)
                return
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
            resp = SESSION.get(self._url, timeout=30)
            resp.raise_for_status()
        except requests.HTTPError as err:
            offline_man.check_requests_error(err)
            self.last_exception = err
            if err.response and err.response.status_code == 429:
                self.log.error(
                    "HTTP 429: Too many requests; waiting for cooldown"
                )
                type(self).sleep_time += 5
                self.log.debug("Current wait time: %f", self.sleep_time)
                return self.download()
            else:
                self.log.error("HTTPError in download")
                type(self).sleep_time += 0.2
                if not offline_man.offline:
                    return self.download()
                raise
        except Exception as err:
            offline_man.check_requests_error(err)
            self.last_exception = err
            self.log.error(
                "Failed to get file from %r:", self._url, exc_info=err
            )
            type(self).sleep_time = 0.2
            raise err
        type(self).sleep_time = 0

        # check the download
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
                if self._invalid_download_count > 5:
                    err = RuntimeError(
                        f"Failed to download from {self._url!r}, "
                        "max retries exceeded. "
                        f"(SHA-1 mismatch, expected {self._hash!r}, got "
                        f"{sha1!r})"
                    )
                    self.last_exception = err
                    raise err from self.last_exception
                self._invalid_download_count += 1
                self.log.error("Download failed, retrying (SHA-1 mismatch)")
                resp = None
                return self.download()
        else:
            log.warning(
                "No SHA1 provided for file downloaded at '%s'",
                self._path,
            )

        # write the file
        with open(self._path, "wb") as f:
            f.write(content)
        if self._vpath:
            with open(self._vpath, "wb") as f:
                f.write(content)
        self.success = True
        self._downloaded_file = True
        if self._callback:
            self._callback(1)
        return

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
    def from_runnable_list(cls, dl_list: list[RunnableDownloader]):
        exc_list = []
        for dl in dl_list:
            if dl.success is not None and (
                dl.last_exception and not dl.success
            ):
                exc_list.append(dl.last_exception)
        return cls(*exc_list)
