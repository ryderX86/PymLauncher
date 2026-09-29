from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

from launcher import config, constants
from launcher.back import profile_manager
from launcher.datatypes import LaunchProfile
from launcher.front import resources
from launcher.ostools import set_jump_list


class ProfileContextMenu(QMenu):
    _profile: LaunchProfile | None
    _debug: bool

    def __init__(
        self, profile: LaunchProfile | None, debug: bool = False, parent=None
    ):
        super().__init__(parent=parent)
        self._profile = profile
        self._debug = debug
        self._build_actions()

    def _build_debug_actions(self):
        copy_id = QAction(self)
        copy_id.setText("Copy Profile ID")
        copy_id.setIcon(resources.symbol("clipboard"))
        copy_id.triggered.connect(self._copy_id)
        self.addAction(copy_id)

    def _build_actions_no_prof(self):
        new = QAction(self)
        new.setIcon(resources.symbol("journal-plus"))
        new.setText("Create New Profile")
        new.triggered.connect(profile_manager.create_profile)
        self.addAction(new)

    def _build_actions(self):
        if not self._profile:
            self._build_actions_no_prof()
            return
        assert self._profile
        if constants.FLAG_ENABLE_JUMP_LISTS:
            add_to_jump = QAction(
                self,
                checkable=True,
                checked=self._profile.uuid in config.jump_list_items,
                text="Show in jump-list",
                icon=(
                    resources.symbol("checkbox-checked")
                    if self._profile.uuid in config.jump_list_items
                    else resources.symbol("square")
                ),
            )
            add_to_jump.toggled.connect(self._add_to_jump_list)
            self.addAction(add_to_jump)

        clone = QAction(self)
        clone.setIcon(resources.symbol("copy"))
        clone.setText(f'Duplicate "{self._profile.name}"')
        clone.triggered.connect(self._clone_profile)
        self.addAction(clone)

        if self._debug:
            self._build_debug_actions()

        delete = QAction(self)
        delete.setObjectName("delete")
        delete.setData("delete")
        delete.setProperty("danger", True)
        delete.setText(f'Delete "{self._profile.name}"')
        delete.setIcon(resources.symbol("trash"))
        if self._profile.is_default_profile:
            delete.setDisabled(True)
        else:
            delete.triggered.connect(self._delete_profile)
        self.addAction(delete)

    def _clone_profile(self):
        assert self._profile
        new = self._profile.copy()
        profile_manager.save_single_profile(new)

    def _delete_profile(self):
        assert self._profile
        result = QMessageBox.warning(
            self.parentWidget(),
            "Delete Profile",
            f'Are you sure you want to delete "{self._profile.name}"?\n'
            "It will be lost forever. (A long time!)",
            buttons=QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Yes:
            profile_manager.delete_single_profile(self._profile)
        else:
            return

    def _add_to_jump_list(self):
        assert self._profile
        if self._profile.uuid in config.jump_list_items:
            # remove from jump-list
            config.jump_list_items.remove(self._profile.uuid)
        else:
            # add to
            config.jump_list_items.append(self._profile.uuid)
        set_jump_list()

    def _copy_id(self):
        assert self._profile
        QApplication.clipboard().setText(self._profile.uuid)
