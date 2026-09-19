import hashlib
import os

from launcher import constants
from launcher.back.download_helpers import RunnableDownloader
from launcher.paths import paths


class GameAsset:
    __slots__ = ("name", "hash", "size")

    def __init__(self, name: str, hash_: str, size: int):
        self.name = name
        self.hash = hash_
        self.size = size

    @classmethod
    def parse(cls, key: str, value: dict):
        if "hash" not in value:
            raise ValueError("'hash' not in asset info")
        elif "size" not in value:
            raise ValueError("'size' not in asset info")
        hash_ = value["hash"]
        if not isinstance(hash_, str):
            raise TypeError(
                f"value['hash'] is not type str ({type(hash_).__name__!r})"
            )
        size = value["size"]
        if not isinstance(size, int):
            try:
                size = int(size)
            except ValueError as err:
                raise TypeError(
                    "value['size'] is not int and cannot be transformed "
                    f"into an integer ({size!r})",
                ) from err
        return cls(key, hash_, size)

    @property
    def path(self):
        return os.path.join(paths.assets_objects, self.hash[:2], self.hash)

    @property
    def virtual_path(self):
        split_path = self.name.split("/")
        return os.path.join(paths.assets_virtual, *split_path)

    @property
    def url(self):
        prefix = self.hash[:2]
        return f"{constants.RESOURCES_URL}/{prefix}/{self.hash}"

    def get_downloader(self, callback=None, virtual: bool = False):
        return RunnableDownloader(
            self.url,
            self.path,
            self.hash,
            callback=callback,
            check_hash=True,
            vpath=self.virtual_path if virtual else None,
        )

    def check_file(self, virtual: bool):
        if virtual:
            path = self.virtual_path
        else:
            path = self.path

        if not os.path.isfile(path):
            return False
        with open(path, "rb") as file:
            fb = file.read()

        file_hash = hashlib.sha1(fb).hexdigest()
        return file_hash == self.hash


class AssetIndex:
    __slots__ = ("assets", "virtual")

    def __init__(self, assets: list[GameAsset], virtual: bool):
        self.assets = assets
        self.virtual = virtual

    def get_downloaders(self, callback=None):
        return set(
            a.get_downloader(callback, self.virtual) for a in self.assets
        )

    @classmethod
    def parse_dict(cls, index: dict):
        virtual: bool = index.get("map_to_resources", False)
        assets = []
        for path, asset in index.get("objects", {}).items():
            assets.append(GameAsset.parse(path, asset))
        return cls(assets, virtual)
