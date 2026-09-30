from PySide6.QtCore import QChildEvent, QEvent, QSize, Qt, Slot
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher.back import profile_manager
from launcher.datatypes import LaunchProfile
from launcher.front import resources
from launcher.front.event_filters import (
    MiscEventFilter,
)
from launcher.front.qt.binding_mixin import BindingMixin
from launcher.functions import Suppressable

from .profile_ctx_menu import ProfileContextMenu

ROLE = 256
PROFILE = 257


class ProfileList(BindingMixin, QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._build()

    def bind(self):
        profile_manager.add_profile_refresh_handler(self._list_profiles)
        profile_manager.add_profile_switch_handler(self._switch_profile)
        self._list_profiles()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.setContentsMargins(0, 0, 0, 0)

        self.new_profile = QPushButton("New Profile")
        self.new_profile.clicked.connect(profile_manager.create_profile)
        root.addWidget(self.new_profile)

        self._view = QListWidget()
        self._view_filter = MiscEventFilter(QChildEvent)
        self._ctx_menu_filter = MiscEventFilter(QContextMenuEvent, True)
        self._view.installEventFilter(self._view_filter)
        self._view.installEventFilter(self._ctx_menu_filter)
        self._view_filter.event_filtered.connect(self._resort)
        self._ctx_menu_filter.event_filtered.connect(self._profile_ctx_menu)
        root.addWidget(self._view)
        self._view.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._view.setUniformItemSizes(True)
        self._view.setProperty("profiles", True)
        self._view.setIconSize(QSize(32, 32))
        self._view.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._view.setSelectionBehavior(
            QListWidget.SelectionBehavior.SelectItems
        )
        self._view.setDragEnabled(True)
        self._view.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._view.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._view.currentItemChanged.connect(self._on_select)
        self._right_click_list_filter = MiscEventFilter(
            QMouseEvent, return_true_on_catch=self._block_right_clicks
        )
        self._view.viewport().installEventFilter(self._right_click_list_filter)

    def _switch_profile(self, new: LaunchProfile):
        if new is None:
            return
        idx = profile_manager.get_row_from_profile(new)
        with self._on_select.suppressed():
            self._view.setCurrentRow(idx)

    def _list_profiles(self):
        sorting = profile_manager.get_profile_sorting()

        with self._on_select.suppressed():
            self._view.clear()

            for uid in sorting:
                profile = profile_manager.profiles[uid]
                item = QListWidgetItem()
                if profile.icon:
                    item.setIcon(resources.profile_icon(profile.icon))
                item.setData(ROLE, profile.uuid)
                item.setData(PROFILE, profile)
                item.setText(profile.name)
                item.setSizeHint(QSize(0, 48))
                self._view.addItem(item)

            self._view.setCurrentRow(
                profile_manager.get_row_from_profile(
                    profile_manager.get_current_profile()
                )
            )

        return

    @Slot(QListWidgetItem, QListWidgetItem)
    @Suppressable
    def _on_select(self, new: QListWidgetItem | None, _: QListWidgetItem):
        if new is None:
            self._view.setCurrentRow(
                profile_manager.get_row_from_profile(
                    profile_manager.get_current_profile()
                )
            )
            return
        profile_manager.set_current_profile(new.data(PROFILE))

    @Slot(QChildEvent)
    @Slot(QEvent)
    @Slot(object)
    def _resort(self, event: QChildEvent):
        if event.type() != QChildEvent.Type.ChildRemoved:
            return
        item = self._view.currentItem()
        idx = self._view.currentRow()

        profile: LaunchProfile = item.data(PROFILE)
        if profile_manager.get_row_from_profile(profile) != idx:
            profile_manager.reorder_single_profile(profile, idx)

    @Slot(QContextMenuEvent)
    def _profile_ctx_menu(self, event: QContextMenuEvent):
        if not event:
            return
        event.accept()
        show_debug_options = (
            Qt.KeyboardModifier.ShiftModifier in event.modifiers()
        )

        idx = self._view.indexAt(event.pos())
        profile: LaunchProfile | None = self._view.model().data(idx, PROFILE)
        ctx = ProfileContextMenu(profile, show_debug_options, self)

        ctx.popup(event.globalPos())

    @staticmethod
    def _block_right_clicks(event: QEvent):
        assert isinstance(event, QMouseEvent)
        if not event or event.type() != QEvent.Type.MouseButtonPress:
            return False
        if event.button() == Qt.MouseButton.RightButton:
            return True
        return False
