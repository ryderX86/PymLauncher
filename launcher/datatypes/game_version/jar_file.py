import hashlib
import logging
import os

from launcher import get_qapp
from launcher.functions import display_file_size
from launcher.networking import make_request
from launcher.offline import offline_man
from launcher.paths import paths

log = logging.getLogger(__name__)


class JarFile:
    __slots__ = ("id", "url", "sha1", "size", "path", "_frozen")
    id: str
    url: str
    sha1: str
    size: int
    path: str

    def __init__(self, id_: str, url: str, sha1: str, size: int):
        self.url = url
        self.sha1 = sha1
        self.size = size
        self.id = id_
        self.path = os.path.join(paths.versions, id_, f"{id_}.jar")

    def available(self):
        if not os.path.isfile(self.path):
            return False

        with open(self.path, "rb") as file:
            file_bytes = file.read()
        file_hash = hashlib.sha1(file_bytes).hexdigest()
        return file_hash == self.sha1

    def download(self, callback=None):
        if self.available():
            return self.path
        log.info(
            "Downloading client JAR for %r (%s)",
            self.id,
            display_file_size(self.size),
        )

        try:
            resp = make_request("get", self.url, preload_response=False)
        except Exception as err:
            log.error(
                "Exception occured downloading %s.jar:", self.id, exc_info=err
            )
            offline_man.check_requests_error(err)
            raise

        downloaded = 0
        sha1 = hashlib.sha1()
        if callback:
            qapp = get_qapp()
        else:
            qapp = None
        with open(self.path, "wb") as fb:
            for chunk in resp.stream(None):
                fb.write(chunk)
                sha1.update(chunk)
                if callback:
                    downloaded += len(chunk)
                    callback(downloaded, self.size)
                    assert qapp is not None
                    qapp.processEvents()

        sha1_final = sha1.hexdigest()
        if self.sha1 != sha1_final:
            log.warning("SHA1 mismatch, deleting JAR")
            os.unlink(self.path)
            err = RuntimeError(
                "SHA1 mismatch for client JAR: "
                f"expected {self.sha1}, got {sha1_final}"
            )
            raise err

        return self.path
