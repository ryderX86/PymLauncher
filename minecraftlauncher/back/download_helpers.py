"""
Common functions for downloading files.
"""
from pathlib import Path
from typing import Literal, Callable, TypeVar, overload, Iterable
from datetime import timedelta, datetime
import logging
import hashlib
import time
import lzma

import requests
from PySide6.QtCore import QThread, QThreadPool, QRunnable

log = logging.getLogger(__name__)
T = TypeVar("T")

def _download(url: str, max_retries: int, timeout: int, _retries: int = 0, *,
              hash: str | None = None) -> requests.Response:
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        if _retries >= max_retries:
            log.error("Failed to download '%s' %d/%d times, giving up."
                      % (url, _retries, max_retries))
            raise
        else:
            log.warning("Downloading '%s' failed. Retrying for %d/%d"
                        % (url, _retries + 1, max_retries))
            time.sleep(0.2)
            # return the same exact thing but bump _retries by 1
            return _download(url, max_retries, timeout, _retries + 1,
                             hash=hash)
    else:
        if isinstance(hash, str):
            if hashlib.sha1(resp.content).hexdigest() == hash:
                return resp
            else:
                log.warning("Download from '%s' gave an unexpected hash! "
                            "Retrying for %d/%d"
                            % (url, _retries + 1, max_retries))
                time.sleep(0.2)
                return _download(url, max_retries, timeout, _retries + 1,
                                hash=hash)
        else:
            return resp

def download(url:str, max_retries:int=2, timeout:int=30, *,
             hash:str|None=None):
    """
    Attempts to download a file to memory using `requests.get()`, returning the
    object if successful, else retrying up to `max_retries:int` (default: `2`)
    times.

    If `hash` is `str`, then the SHA1 will be checked upon download completion.
    If it doesn't match, the download will be failed and will retry
    automatically, counting as a failed download and using a retry.
    """
    if isinstance(hash, str) and not hash:
        hash = None
    return _download(url, max_retries, timeout, hash=hash)

def _check_file_sha1(path:str|Path, sha1:str):
    """return `True` if the file exists & sha1 matches"""
    if isinstance(path, str):
        path = Path(path)
    if not sha1:
        return True
    if (not path.exists()) or (not path.is_file()):
        return False
    file_hash = hashlib.sha1(path.read_bytes()).hexdigest()
    return bool(file_hash == sha1)

def _check_file_size(path:str|Path, size:int):
    if not size:
        log.warning("check_file_size() called without a valid size!")
        return True
    if isinstance(path, str):
        path = Path(path)
    if (not path.exists()) or (not path.is_file()):
        return False
    return path.stat().st_size == size

def file_exists_or_age(
        path: str | Path, max_age: float | int | timedelta = 86400.0):
    """
    Return `True` if the file exists and is under the age specified in
    `max_age` (seconds).
    """
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        return False
    elif not path.is_file():
        return False
    if isinstance(max_age, (int, float)):
        max_age = timedelta(seconds=max_age)
    real_max_age:float = (datetime.now() - max_age).timestamp()
    return path.stat().st_mtime > real_max_age

def should_download_file(
        path: str | Path, *, hash: str | None = None, size: int | None = None,
        hash_type: Literal['sha1', 'sha256'] = "sha1"):
    """
    Checks if a file should be downloaded based on either existance, hash,
    size, or some/all of the above.

    **WARNING:** SHA-256 not implemented yet.
    """
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        return True
    elif not path.is_file():
        return True
    if hash:
        match hash_type:
            case "sha1":
                hash_match = _check_file_sha1(path, hash)
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
    return not bool(hash_match and size_match)

def filter_downloads(
    downloads: list[T], filters: Iterable[Callable[[list[T]], list[T]]]
    ):
    for filter in filters:
        downloads = filter(downloads)
    return downloads

class RunnableDownloader(QRunnable):
    threads_quit = False
    sleep_time = 0.0

    _url: str
    """File download URL"""
    _path: Path
    """File final location"""
    _hash: str | None
    """File hash to check against"""
    _override: bool
    """Should we override the file? (default: `False`)"""
    _lzma: bool

    log = log.getChild("BulkDownloadSingleFile")
    def __init__(
            self, url: str, path: Path | str, hash: str | None = None,
            override: bool = False, mkdir: bool = True, lzma: bool = False,
            callback_f: Callable[[int], None] | None = None,
            check_hash: bool = True):
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
        if isinstance(path, Path):
            self._path = path
        self._path = Path(path)
        if not self._path.parent.exists():
            if not mkdir:
                raise FileNotFoundError(self._path)
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as err:
                raise ValueError("Invalid path given for download: %s"
                                 % str(self._path)) from err
        self._hash = hash
        self._override = override
        self._lzma = lzma
        self._cb_f = callback_f
        self._check_hash = check_hash
            
    def _check_sha1(self):
        if not self._hash:
            self.log.warning("Called SHA check function without a present SHA")
            return True
        return _check_file_sha1(self._path, self._hash)
    
    @property
    def needs_download(self) -> bool:
        if self._hash and self._path.exists() and self._path.is_file():
            if self._check_sha1():
                return False
        return True
    
    def run(self):
        if self.threads_quit:
            self.log.debug("Quitting thread early")
            return
        self.download()
    
    def download(self):
        if self._check_hash and self._path.exists() and self._path.is_file():
            if self._check_sha1():
                return 0
            self.log.debug("File exists but SHA1 doesn't match, deleting.")
            self._path.unlink(True)
        attempts = 0
        resp = None
        while attempts < 3:
            try:
                resp = requests.get(self._url, timeout=30)
                resp.raise_for_status()
            except Exception as err:
                self.log.error("Failed to get file from '%s': %s"
                               % (self._url, str(err)))
                time.sleep(1)
                self.sleep_time = 2
                continue
            else:
                self.sleep_time = 0
                if self._lzma:
                    content = lzma.decompress(resp.content)
                else:
                    content = resp.content
                self._path.write_bytes(content)
                if self._hash:
                    if self._check_sha1():
                        break
                    else:
                        self.log.error("Download failed, retrying (SHA-1 " \
                                       "mismatch)")
                        resp = None
                else:
                    log.warning("SHA-1 doesn't exist for '%s'" % self._path)
            finally:
                attempts += 1
        if not resp:
            raise RuntimeError("Failed to download file from '%s' to '%s'"
                               % (self._url, str(self._path)))
        else:
            if self._cb_f:
                self._cb_f(1)
        return 1
    
    @classmethod
    def kill_all(cls):
        cls.threads_quit = True