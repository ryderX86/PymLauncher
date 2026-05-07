from dataclasses import dataclass, field, InitVar
from datetime import datetime
from pathlib import Path
from enum import StrEnum
import logging
import json

from minecraftlauncher.back import version_manager
from minecraftlauncher.constants import MINECRAFT_DIR

log = logging.getLogger(__name__)


class GameVersionType(StrEnum):
    RELEASE = "release"
    SNAPSHOT = "snapshot"
    ALPHA = "old_alpha"
    BETA = "old_beta"


@dataclass(slots=True)
class GameVersionStub:
    id: str
    """The ID of the game version (i.e. `1.7.10`, `26w31a`, or `26.1`)"""
    type: GameVersionType
    """Release type (`snapshot`, `release`, `old_beta` or `old_alpha`)"""
    url: str | None = field(init=False)
    """The URL to the manifest JSON file (if present)"""
    path: Path | None = field(init=False)
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
        if isinstance(location, Path) and not (
            location.exists() or location.is_file()
        ):
            log.warning("Could not find JSON file for '%s'!", self.id)
        if is_local:
            self.path = Path(location)
        else:
            self.url = str(location)
        if release_time:
            try:
                self._release_ts = datetime.fromisoformat(
                    release_time
                ).timestamp()
            except Exception as err:
                log.error(
                    "%s() occured whilst parsing datetime, setting to 0.",
                    type(err).__name__,
                )
                self._release_ts = 0.0
        else:
            self._release_ts = 0.0
        if time:
            try:
                self._build_ts = datetime.fromisoformat(time).timestamp()
            except Exception as err:
                log.error(
                    "%s() occured whilst parsing datetime, falling back "
                    "to release time.",
                    type(err).__name__,
                )
                self._build_ts = 0.0
        else:
            self._build_ts = self._release_ts

    @property
    def local(self):
        """
        Returns `True` if this is based on a local manifest, or `False` if this
        is a manifest from Mojang's API
        """
        return bool(getattr(self, "path", None))

    @property
    def jar_path(self):
        return MINECRAFT_DIR / "versions" / self.id / f"{self.id}.jar"

    def get_json(self) -> dict:
        if self.local:
            assert self.path
            return json.loads(self.path.read_text())
        else:
            version_info = version_manager.fetch_version_json(self.id)
            if not version_info:
                raise RuntimeError(
                    f"Couldn't get version info for stub for '{self.id}'"
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

    @property
    def timestamp(self):
        return self._release_ts

    @property
    def build_timestamp(self):
        return self._build_ts
