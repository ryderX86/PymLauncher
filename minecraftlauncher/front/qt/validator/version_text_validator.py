from minecraftlauncher.back import version_manager
from minecraftlauncher.constants import (
    LATEST_VERSIONS_SET,
    LATEST_VERSION_TEXT,
)

from PySide6.QtGui import QValidator

from .store_results import store_results, QValidatorWithStoredResults


class VersionTextValidator(QValidatorWithStoredResults):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ver_list = []
        self.ver_ids = []
        self._last_good_val: str | None = None

    def load(self):
        self.ver_list = version_manager.get_version_list()
        self.ver_ids = [v.id for v in self.ver_list]

    @store_results
    def validate(self, a0: str, a1: int) -> tuple[QValidator.State, str, int]:
        if not self.ver_ids:
            return self.State.Intermediate, a0, a1
        if not a0:
            return self.State.Intermediate, self.ver_ids[0], 0
        if a0 in LATEST_VERSIONS_SET:
            self._last_good_val = a0
            return self.State.Acceptable, a0, a1
        for id_ in self.ver_ids:
            if id_ == a0:
                self._last_good_val = a0
                return self.State.Acceptable, a0, a1
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
