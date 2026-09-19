from collections.abc import Iterable
from typing import Any, assert_never
import hashlib
import logging
import os

from launcher import constants
from launcher.back.download_helpers import RunnableDownloader
from launcher.config import config
from launcher.paths import paths

from .rules import OSRule

log = logging.getLogger(__name__)


def _get_native_download(lib: dict) -> dict | None:
    natives_map: dict = lib.get("natives", {})
    arch = constants.NATIVES_ARCH
    classifier = None
    if natives_map:
        classifier: str | None = natives_map.get(constants.OS)
        if classifier:
            assert isinstance(classifier, str)
            classifier = classifier.replace("${arch}", arch)
    classifiers: dict[str, Any] = lib.get("downloads", {}).get(
        "classifiers", {}
    )
    assert isinstance(classifiers, dict)
    if not classifiers:
        return None
    classifiers_keys = set(classifiers.keys())
    natives_noarch = f"natives-{constants.OS}"
    natives_arch = f"natives-{constants.OS}-{arch}"
    if classifier in classifiers_keys:
        return classifiers[classifier]
    elif natives_noarch in classifiers_keys:
        return classifiers[natives_noarch]
    elif natives_arch in classifiers_keys:
        return classifiers[natives_arch]
    return None


def _get_normal_download(lib: dict) -> dict:
    if "downloads" in lib and "artifact" in lib["downloads"]:
        return lib["downloads"]["artifact"]
    name: str = lib["name"]
    name_split = name.split(":")
    org_path = name_split[0].split(".")
    file_path = "/".join(
        (*org_path, *name_split[1:], f"{"-".join(name_split[1:])}.jar")
    )
    if "url" in lib:  # this format is always a base URL
        base_url = lib["url"].rstrip("/")
        url = "/".join((base_url, file_path))
    else:
        url = None
    sha1 = lib.get("sha1")
    if not sha1:
        # forge, for some genius reason beyond my understanding,
        # just has a blank string on some libs' SHA-1s
        sha1 = None
    size = lib.get("size")
    return {"path": file_path, "sha1": sha1, "size": size, "url": url}


class Library:
    __slots__ = (
        "name",
        "url",
        "sha1",
        "path",
        "rules",
        "size",
        "required",
        "is_native",
        "extract_rules",
    )

    # pylint: disable-next=dangerous-default-value
    def __init__(
        self,
        name: str,
        path: str,
        url: str | None,
        sha1: str | Iterable[str] | None = None,
        rules: list[OSRule] = [],
        size: int | None = None,
        client: bool = True,
        native: bool = False,
        extract_rules: dict[str, list] | None = None,
    ):
        self.name = name
        self.path = os.path.join(paths.libraries, *path.split("/"))
        self.url = url
        self.rules = rules
        match sha1:
            case str():
                self.sha1 = {sha1}
            case set():
                self.sha1 = sha1
            case list() | tuple() | Iterable():
                self.sha1 = set(sha1)
            case None:
                self.sha1 = None
            case _:
                assert_never(sha1)
        self.size = size
        self.required = client
        self.is_native = native
        self.extract_rules = extract_rules

    def allowed(self):
        if not self.rules:
            return True
        result = False
        for rule in self.rules:
            if rule.matches:
                result = rule.allow_on_match
        return result

    @property
    def has_download(self):
        return bool(self.url)

    def downloader(self, callback=None):
        if not self.has_download:
            raise RuntimeError(f"No download present for {self.name!r}")
        assert self.url
        return RunnableDownloader(
            self.url, self.path, self.sha1, False, callback, bool(self.sha1)
        )

    def available(self):
        if os.path.isfile(self.path):
            with open(self.path, "rb") as file:
                sha1 = hashlib.sha1(file.read()).hexdigest()
            if self.sha1:
                return sha1 in self.sha1
            else:
                return (
                    config.redownload_option
                    == config.JarRedownloadBehavior.NEVER
                )
        return False

    def directory(self):
        return os.path.dirname(self.path)

    @classmethod
    def parse(cls, library: dict):
        if "name" not in library:
            raise ValueError(f"Invalid library: {library!r}")

        artifact = None
        native = False
        if "natives" in library or "classifiers" in library.get(
            "downloads", {}
        ):
            artifact = _get_native_download(library)
            native = True
        if not artifact:
            native = False
            artifact = _get_normal_download(library)
        name: str = library["name"]
        client = library.get("clientreq", True)
        rules_raw: list[dict] = library.get("rules", [])
        if not isinstance(rules_raw, list):
            log.warning(
                "Ignoring unexpected rule type in library %r: %s",
                name,
                type(rules_raw).__name__,
            )
            rules_raw = []
        try:
            rules = [OSRule(**rule) for rule in rules_raw]
        except Exception as err:
            err.add_note(str(library))
            raise err
        sha1 = artifact.get("sha1")
        size = artifact.get("size")
        return cls(
            name,
            artifact["path"],
            artifact.get("url"),
            sha1,
            rules,
            size,
            client,
            native,
            library.get("extract"),
        )
