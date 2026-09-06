from dataclasses import InitVar, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
import json
import logging
import os

from launcher.back import version_manager
from launcher.paths import paths

log = logging.getLogger(__name__)


class GameVersionType(StrEnum):
    RELEASE = "release"
    SNAPSHOT = "snapshot"
    ALPHA = "old_alpha"
    BETA = "old_beta"


@dataclass(slots=True, eq=False, order=False)
class GameVersionStub:
    id: str
    """The ID of the game version (i.e. `1.7.10`, `26w31a`, or `26.1`)"""
    type: GameVersionType
    """Release type (`snapshot`, `release`, `old_beta` or `old_alpha`)"""
    url: str | None = field(init=False)
    """The URL to the manifest JSON file (if present)"""
    path: str | None = field(init=False)
    """The path to the manifest JSON file (if present)"""

    location: InitVar[str | Path]
    is_local: InitVar[bool]
    release_time: InitVar[str | None]
    time: InitVar[str | None]

    _release_ts: float = field(init=False)
    _build_ts: float = field(init=False)

    def __post_init__(
        self,
        location: str | Path,
        is_local: bool = False,
        release_time: str | None = None,
        time: str | None = None,
    ):
        if is_local:
            self.path = str(location)
        else:
            self.url = str(location)
        if release_time:
            try:
                self._release_ts = datetime.fromisoformat(
                    release_time
                ).timestamp()
            except Exception as err:
                log.error(
                    "%s occured whilst parsing datetime, setting to 0.",
                    type(err).__name__,
                    exc_info=err,
                )
                self._release_ts = 0.0
        else:
            self._release_ts = 0.0
        if time:
            try:
                self._build_ts = datetime.fromisoformat(time).timestamp()
            except Exception as err:
                log.error(
                    "%s occured whilst parsing datetime, falling back "
                    "to release time.",
                    type(err).__name__,
                    exc_info=err,
                )
                self._build_ts = 0.0
        else:
            self._build_ts = self._release_ts

    @property
    def local(self):
        """
        Returns `True` if this is based on a local JSON file, or `False` if
        this is a manifest from Mojang's API
        """
        return bool(getattr(self, "path", None))

    @property
    def jar_path(self):
        return os.path.join(paths.game, "versions", self.id, f"{self.id}.jar")

    def get_json(self) -> dict:
        if self.local:
            assert self.path
            with open(self.path, "r") as f:
                txt = f.read()
            try:
                return json.loads(txt)
            except json.JSONDecodeError as err:
                raise RuntimeError(
                    f"Failed to decode JSON from file at {self.path!r}"
                ) from err
        else:
            version_info = version_manager.fetch_version_json(self.id)
            if not version_info:
                raise RuntimeError(
                    f"Couldn't get version info for stub for {self.id!r}"
                )
            return version_info

    def __eq__(self, other):
        """Returns `True` if the IDs match."""
        if isinstance(other, GameVersionStub):
            return self.id == other.id
        elif isinstance(other, str):
            return self.id == other
        return NotImplemented

    def __ne__(self, other):
        """Returns `True` if the IDs don't match."""
        if isinstance(other, GameVersionStub):
            return self.id != other.id
        elif isinstance(other, str):
            return self.id != other
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, GameVersionStub):
            return self.timestamp < other.timestamp
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, GameVersionStub):
            return self.timestamp > other.timestamp
        return NotImplemented

    def __le__(self, other):
        if isinstance(other, GameVersionStub):
            return self.timestamp <= other.timestamp
        return NotImplemented

    def __ge__(self, other):
        if isinstance(other, GameVersionStub):
            return self.timestamp >= other.timestamp
        return NotImplemented

    @property
    def timestamp(self):
        return self._release_ts

    @property
    def build_timestamp(self):
        return self._build_ts
