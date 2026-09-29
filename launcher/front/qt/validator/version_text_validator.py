from typing import assert_never

from PySide6.QtGui import QValidator

from launcher import config
from launcher.back import version_manager
from launcher.constants import (
    LATEST_SNAPSHOT_TEXT,
    LATEST_SNAPSHOT_TEXT_UI,
    LATEST_VERSION_TEXT,
    LATEST_VERSION_TEXT_UI,
    LATEST_VERSIONS_SET,
)

from .store_results import QValidatorWithStoredResults, store_results


class VersionTextValidator(QValidatorWithStoredResults):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ver_list = []
        self.ver_ids = []
        self._last_good_val: str | None = None

    def load(self):
        self.ver_list = version_manager.get_version_list()
        self.ver_ids = [v.id for v in self.ver_list]
        self._latest_release_text = LATEST_VERSION_TEXT_UI.format(
            version_manager.get_latest_release()
        )
        self._latest_snapshot_text = LATEST_SNAPSHOT_TEXT_UI.format(
            version_manager.get_latest_snapshot()
        )

    @property
    def latest_release_ui(self):
        return self._latest_release_text

    @property
    def latest_snapshot_ui(self):
        return self._latest_snapshot_text

    def iter_versions_combobox(self):
        yield (self._latest_release_text, LATEST_VERSION_TEXT)
        if config.show_snapshots:
            yield (self._latest_snapshot_text, LATEST_SNAPSHOT_TEXT)
        for ver in self.ver_list:
            if config.show_snapshots and config.show_old_releases:
                yield (ver.id, ver.id)
            elif ver.type == "release":
                yield (ver.id, ver.id)
            elif ver.type == "snapshot" and config.show_snapshots:
                yield (ver.id, ver.id)
            elif (
                ver.type in {"old_alpha", "old_beta"}
                and config.show_old_releases
            ):
                yield (ver.id, ver.id)

    @store_results
    def validate(self, a0: str, a1: int) -> tuple[QValidator.State, str, int]:
        if not self.ver_ids:
            return self.State.Intermediate, a0, a1
        if not a0:
            return self.State.Intermediate, self.ver_ids[0], 0
        if a0 in {self._latest_release_text, self._latest_snapshot_text}:
            self._last_good_val = a0
            return self.State.Acceptable, a0, a1
        if a0 == LATEST_VERSION_TEXT or a0 == LATEST_SNAPSHOT_TEXT:
            if a0 == LATEST_SNAPSHOT_TEXT:
                a0 = self._latest_snapshot_text
            elif a0 == LATEST_VERSION_TEXT:
                a0 = self._latest_release_text
            else:
                assert_never(a0)

            self._last_good_val = a0
            return self.State.Acceptable, a0, a1
        if a0 in self.ver_ids:
            return self.State.Acceptable, a0, a1
        for id_ in self.ver_ids:
            if id_.startswith(a0):
                return self.State.Intermediate, a0, a1
        return self.State.Invalid, LATEST_VERSION_TEXT, 0

    def fixup(self, arg__1: str):
        if arg__1 not in self.ver_ids or LATEST_VERSIONS_SET:
            for v in self.ver_ids:
                if v.startswith(arg__1):
                    return v
            return LATEST_VERSION_TEXT
        return arg__1
