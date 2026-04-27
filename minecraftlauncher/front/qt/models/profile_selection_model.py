import logging

from PySide6.QtCore import Qt, QItemSelectionModel, QModelIndex, Signal

from minecraftlauncher.back import profile_manager
from minecraftlauncher.datatypes.launch_profile import GameProfile
from .profile_model import ProfileModel

_INSTANCE = None

log = logging.getLogger(__name__.replace("_", ""))


class ProfileSelectionModel(QItemSelectionModel):
    begin_change = Signal(GameProfile)

    def __init__(self, model=ProfileModel()):
        global _INSTANCE
        if _INSTANCE:
            raise RuntimeError(
                "ProfileSelectionModel is already initialized! "
                "Get the global instance instead: 'instance()'"
            )
        profile_manager.add_profile_switch_handler(self._profile_switch)
        profile_manager.add_profile_refresh_handler(self._handle_prof_refresh)
        super().__init__(model)
        _INSTANCE = self
        self._model_old = super().model
        self.currentChanged.connect(self._handle_idx_change)
        self.model().refresh()

    def _handle_prof_refresh(self):
        current_row = profile_manager.get_row_from_profile(
            profile_manager.get_current_profile()
        )
        idx = self.model().index(current_row, 0)
        self.setCurrentIndex(idx, self.SelectionFlag.ClearAndSelect)

    @classmethod
    def instance(cls):
        if _INSTANCE:
            return _INSTANCE
        return cls()

    def _handle_idx_change(self, index: QModelIndex):
        if not index.isValid():
            return
        profile = index.data(Qt.ItemDataRole.UserRole)
        self.begin_change.emit(profile)
        if profile_manager.get_current_profile() != profile:
            profile_manager.set_current_profile(profile)

    def _profile_switch(self, prof: GameProfile):
        prof_row = profile_manager.get_row_from_profile(prof)
        idx = self.model().index(prof_row, 0)
        if self.currentIndex().row() != idx.row():
            self.setCurrentIndex(idx, self.SelectionFlag.ClearAndSelect)

    @staticmethod
    def has_instance():
        return bool(_INSTANCE)

    def model(self) -> ProfileModel:
        m = self._model_old()
        assert m
        return m  # type: ignore
