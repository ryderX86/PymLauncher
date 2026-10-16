from typing import assert_never

from PySide6.QtGui import QValidator

from launcher.back import version_manager
from launcher.constants import (
    LATEST_SNAPSHOT_TEXT,
    LATEST_SNAPSHOT_TEXT_UI,
    LATEST_VERSION_TEXT,
    LATEST_VERSION_TEXT_UI,
    LATEST_VERSIONS_SET,
)


class VersionTextValidator(QValidator):
    _last_good_val: str

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ver_list = []
        self.ver_ids = []
        self._last_good_val = ""

    def load(self):
        self.ver_list = version_manager.get_version_list()
        self.ver_ids = [v.id for v in self.ver_list]
        self._latest_release_text = LATEST_VERSION_TEXT_UI.format(
            version_manager.get_latest_release()
        )
        self._latest_snapshot_text = LATEST_SNAPSHOT_TEXT_UI.format(
            version_manager.get_latest_snapshot()
        )

        self._last_good_val = self._latest_release_text

    @property
    def latest_release_ui(self):
        return self._latest_release_text

    @property
    def latest_snapshot_ui(self):
        return self._latest_snapshot_text

    def iter_versions_combobox(self):
        yield (self._latest_release_text, LATEST_VERSION_TEXT)
        for ver in self.ver_list:
            yield (ver.id, ver.id)

    def reset_last_val(self, val: str):
        self._last_good_val = self._do_fixup(val)

    def validate(self, a0: str, a1: int) -> tuple[QValidator.State, str, int]:
        if not self.ver_ids:
            return self.State.Intermediate, a0, a1
        if not a0:
            return self.State.Intermediate, a0, -1
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

    def _do_fixup(self, arg__1: str):
        if not arg__1:
            return self._last_good_val
        if arg__1 in LATEST_VERSIONS_SET:
            return arg__1
        if arg__1 not in self.ver_ids:
            for v in self.ver_ids:
                if v.startswith(arg__1):
                    return v
            return self._last_good_val
        return arg__1

    def fixup(self, arg__1: str):
        self._last_good_val = self._do_fixup(arg__1)
        return self._last_good_val
