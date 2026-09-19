from typing import Literal, overload
import hashlib
import json
import logging
import os

from requests.exceptions import HTTPError as HTTPError_

from launcher import SESSION
from launcher.exceptions import InvalidAssetError
from launcher.offline import offline_man
from launcher.paths import paths

from .asset_index import AssetIndex

log = logging.getLogger(__name__)


class AssetIndexStub:
    _instances: dict[str, "AssetIndexStub"] = {}
    __slots__ = (
        "id",
        "sha1",
        "size",
        "total_size",
        "url",
        "file_path",
        "_initialized",
    )

    def __new__(
        cls, id_: str, sha1: str, size: int, total_size: int, url: str
    ):
        if sha1 in cls._instances:
            return cls._instances[sha1]
        obj = object.__new__(cls)
        obj._initialized = False
        return obj

    def __init__(
        self, id_: str, sha1: str, size: int, total_size: int, url: str
    ):
        if self._initialized:
            return
        self.id = id_
        self.sha1 = sha1
        self.size = size
        self.total_size = total_size
        self.url = url
        self.file_path = os.path.join(paths.assets_indexes, f"{self.id}.json")
        self._initialized = True
        self._instances[sha1] = self

    @classmethod
    def parse_dict(cls, assetindex: dict):
        sha1: str | None = assetindex.get("sha1")
        if not sha1:
            raise ValueError("'sha1' not in provided asset index info")
        if sha1 in cls._instances:
            return cls._instances[sha1]
        id_: str | None = assetindex.get("id")
        if not id_:
            raise ValueError("'id' not in provided asset index info")
        size: int | None = assetindex.get("size")
        if not size:
            raise ValueError("'size' not in provided asset index info")
        total_size: int | None = assetindex.get("totalSize")
        if not total_size:
            raise ValueError("'totalSize' not in provided asset index info")
        url: str | None = assetindex.get("url")
        if not url:
            raise ValueError("'url' not in provided asset index info")
        return cls(id_, sha1, size, total_size, url)

    def available(self):
        if not os.path.isfile(self.file_path):
            return False
        # past this point, file exists
        with open(self.file_path, "rb") as file:
            sha1 = hashlib.sha1(file.read()).hexdigest()
        if sha1 != self.sha1:
            return False
        # past this point, SHA1 matches
        return True

    @overload
    def download(self, *, return_dict: Literal[False]) -> AssetIndex: ...

    @overload
    def download(self, *, return_dict: Literal[True]) -> dict: ...

    @overload
    def download(self) -> AssetIndex: ...

    def download(self, *, return_dict=False) -> dict | AssetIndex:
        if offline_man.offline:
            self.get_json()
        if self.available():
            if return_dict:
                return self.get_json()
            else:
                return AssetIndex.parse_dict(self.get_json())

        log.info("Getting asset index %s from %r", self.id, self.url)
        try:
            resp = SESSION.get(self.url)
            resp.raise_for_status()
        except HTTPError_ as err:
            offline_man.check_requests_error(err)
            raise

        if not os.path.isdir(paths.assets_indexes):
            log.debug("Creating directories to %r", paths.assets_indexes)
            os.makedirs(paths.assets_indexes, exist_ok=True)

        try:
            index: dict = json.loads(resp.text)
        except json.JSONDecodeError as err:
            raise InvalidAssetError(
                f"Server returned invalid JSON from {self.url!r}",
                self.file_path,
                resp.text,
            ) from err

        with open(self.file_path, "w") as file:
            file.write(resp.text)

        if return_dict:
            return index
        return AssetIndex.parse_dict(index)

    def get_json(self):
        if not offline_man.offline and not self.available():
            err = FileNotFoundError("JSON file doesn't exist or is outdated!")
            err.filename = self.file_path
            raise err
        with open(self.file_path, "r") as file:
            text = file.read()
        try:
            asset_index_file = json.loads(text)
        except json.JSONDecodeError as err:
            raise InvalidAssetError(
                f"Failed to decode JSON in file at {self.file_path}",
                self.file_path,
                text,
            ) from err
        return asset_index_file
