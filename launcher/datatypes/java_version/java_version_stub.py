from datetime import datetime
import hashlib
import os

from launcher import constants
from launcher.paths import paths


class JavaVersionStub:
    __slots__ = (
        "manifest_sha1",
        "size",
        "manifest_url",
        "manifest_path",
        "version_id",
        "version_name",
        "release_date",
    )

    def __init__(
        self,
        manifest_sha1: str,
        size: int,
        manifest_url: str,
        version_id: str,
        version_name: str,
        release_date: str,
    ):
        self.manifest_sha1 = manifest_sha1
        self.size = size
        self.manifest_url = manifest_url
        self.version_id = version_id
        self.version_name = version_name
        self.release_date = release_date
        self.manifest_path = os.path.join(
            paths.jre_path,
            f"{self.version_name}.{constants.OS}-{constants.ARCH}.json",
        )

    def available(self):
        if not os.path.isfile(self.manifest_path):
            return False
        with open(self.manifest_path, "rb") as file:
            file_bytes = file.read()
        file_sha1 = hashlib.sha1(file_bytes).hexdigest()
        return file_sha1 == self.manifest_sha1

    @staticmethod
    def choose_stub(stubs: list[dict]):
        if len(stubs) == 1:
            return stubs[0]
        latest_release = datetime.fromisoformat("1969-12-31T23:59:59Z")
        latest_idx = -1
        for idx, stub in enumerate(stubs):
            release_date = stub.get("version", {}).get(
                "released", "1970-01-01T00:00:00Z"
            )
            if latest_idx < 0:
                latest_idx = idx
                latest_release = release_date
            release_dt = datetime.fromisoformat(release_date)
            if release_dt > latest_release:
                latest_idx = idx
                latest_release = release_dt
        return stubs[latest_idx]

    @classmethod
    def parse(cls, name: str, stub: dict | list):
        if isinstance(stub, list):
            stub = cls.choose_stub(stub)

        manifest_info = stub.get("manifest", {})
        if not manifest_info or not {"sha1", "size", "url"}.issubset(
            manifest_info.keys()
        ):
            raise RuntimeError("Missing manifest info in provided dict")
        version_info = stub.get("version", {})
        if not version_info or not {"name", "released"}.issubset(
            version_info.keys()
        ):
            raise RuntimeError("Missing version info in provided dict")

        mf_sha1 = manifest_info["sha1"]
        size = manifest_info["size"]
        mf_url = manifest_info["url"]
        ver_id = version_info["name"]
        ver_release = version_info["released"]

        return cls(mf_sha1, size, mf_url, ver_id, name, ver_release)
