"""
Common functions for downloading files.
"""
from pathlib import Path
from typing import Literal, Callable
from datetime import timedelta, datetime
import logging
import hashlib
import time
import lzma

import requests
from PySide6.QtCore import QThread, QThreadPool, QRunnable

log = logging.getLogger(__name__)

def _download(url:str, max_retries:int, timeout:int, _retries:int=0, *,
              hash:str|None=None):
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
            time.sleep(1)
            # return the same exact thing but bump _retries by 1
            return _download(url, max_retries, timeout, _retries + 1,
                             hash=hash)
    else:
        if (isinstance(hash, str)
            and hashlib.sha1(resp.content).hexdigest() == hash):
            return resp
        elif isinstance(hash, str):
            # checking again because that'd mean the first "if" failed, but
            # if we go to this and we actually have a hash, that means it
            # didn't match the expected hash since that was the second
            # part of the initial if statement
            log.warning("Download '%s' gave an unexpected hash!\
                        Retrying for %d/%d" % (url, _retries + 1, max_retries))
            time.sleep(1)
            return _download(url, max_retries, timeout, _retries + 1,
                             hash=hash)
        else:
            # we just didn't have a hash lol!!!
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

def file_exists_or_age(path:str|Path, max_age:float|int|timedelta=86400.0):
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

def should_download_file(path:str|Path, *,
                         hash:str|None=None, size:int|None=None,
                         hash_type:Literal['sha1', 'sha256']="sha1"):
    """
    Checks if a file should be downloaded based on either existance, hash,
    size, or all of the above.

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

_threads_quit = False

def kill_threads():
    global _threads_quit
    _threads_quit = True

_global_bulk_sleep_time = 0.0

def _bulk_set_sleep(new_time:float):
    global _global_bulk_sleep_time
    _global_bulk_sleep_time = new_time

class BulkDownloadSingleFile(QRunnable):
    _url:str
    """File download URL"""
    _path:Path
    """File final location"""
    _hash:str|None
    """File hash to check against"""
    _override:bool
    """Should we override the file? (default: `False`)"""
    _lzma:bool

    log = log.getChild("BulkDownloadSingleFile")
    def __init__(self, url:str, path:Path|str, hash:str|None=None,
                 override:bool=False, mkdir:bool=True, lzma:bool=False,
                 callback_f:Callable[[int], None]|None=None,
                 callback_s:Callable|None=None, check_hash:bool=True):
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
        self._cb_s = callback_s
        self._check_hash = check_hash
            
    def _check_sha1(self):
        assert self._hash
        return _check_file_sha1(self._path, self._hash)
    
    @property
    def needs_download(self) -> bool:
        if self._path.exists() and self._path.is_file():
            if self._check_sha1():
                return False
        return True
    
    def run(self):
        if _threads_quit:
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
                _bulk_set_sleep(2)
                continue
            else:
                _bulk_set_sleep(0.0)
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
            if self._cb_s:
                self._cb_s()
        return 1
        

class BulkDownloadWorker(QRunnable):
    log = log.getChild("BulkDownloadWorker")

    def __init__(self, downloads:list[BulkDownloadSingleFile],
                 first_callback:Callable[[int], None]|None=None,
                 second_callback:Callable|None=None):
        """
        QThreadPool worker for bulk downloads. Don't call this directly.
        Use `auto_split()` instead and start each one in the resulting list.
        """
        super().__init__()
        self._download_list = downloads
        self._fcallback = first_callback
        self._scallback = second_callback
        self._download_total = 0

    def run(self):
        total = len(self._download_list)
        downloaded = 0
        processed = 0
        self.log.info("Starting bulk download.")
        for download in self._download_list:
            if _threads_quit:
                self.log.info("Shutting down thread early.")
                return
            download_increase = download.download()
            downloaded += download_increase
            processed += 0
            if self._fcallback:
                self._fcallback(1)
            if self._scallback:
                self._scallback()
            if download_increase > 0:
                time.sleep(_global_bulk_sleep_time)
                
        self.log.info("Done. Downloaded %d new files out of %d."
                      % (downloaded, total))
        self._download_total = downloaded
    
    @classmethod
    def auto_split(cls, downloads:list[BulkDownloadSingleFile],
                   first_callback:Callable[[int], None]|None=None,
                   second_callback:Callable|None=None):
        master_list:list[BulkDownloadWorker] = []
        current_list:list[BulkDownloadSingleFile] = []
        max_per_wrkr = len(downloads) // 12
        cls.log.debug("max per worker: %d" % max_per_wrkr)
        for download in downloads:
            if len(current_list) >= max_per_wrkr:
                master_list.append(cls(
                    [*current_list],
                    first_callback,
                    second_callback
                ))
                del current_list
                current_list = []
            current_list.append(download)
        if len(current_list) > 0:
            master_list.append(cls(
                current_list,
                first_callback,
                second_callback
            ))
        return master_list