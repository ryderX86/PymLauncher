"""
All the (3D) code in here is genuinely horrifying and should probably be either
rewritten from scratch or deleted permenantly and replaced with a generic
QImage thumbnail
"""

from pathlib import Path
from string import ascii_letters
import logging
import hashlib
import json
import os

from PySide6.QtCore import QSize, Qt, Signal, QTimer, QUrl, QObject
from PySide6.QtGui import QCloseEvent, QPixmap, QSurfaceFormat, QImage
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QDialog,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
)
from PySide6.QtQuickWidgets import QQuickWidget
import requests

from minecraftlauncher.front import resources
from minecraftlauncher.auth import LauncherAccount, SkinModel
from minecraftlauncher.back import account_manager
from minecraftlauncher.functions.error_box import error_box
from minecraftlauncher.constants import (
    SKIN_CHANGE_URL,
    OS_PATH_DELIM,
    CAPE_URL,
)
from minecraftlauncher import SESSION, config

log = logging.getLogger(__name__)


class SkinChange(QDialog):
    skin_changed = Signal()

    # instance attributes
    current_cape: str | None
    current_cape_cloud_idx: int
    current_cape_cloud: str | None

    def __init__(self, account: LauncherAccount, parent=None):
        super().__init__(parent)
        self.current_cape = None
        self.current_cape_cloud = None

        self._current_win_environment = (
            QSurfaceFormat.defaultFormat().__copy__()
        )
        self.account = account
        if account.profile:
            if account.profile.current_cape:
                self.current_cape = account.profile.current_cape["id"]
                self.current_cape_cloud = account.profile.current_cape["id"]
        if account.profile_needs_update():
            log.debug("Account has old profile info, updating")
            account.get_profile_info()

        self._build_ui()
        self.current_cloud_hash = hashlib.sha256(
            account.skin_bytes()
        ).hexdigest()
        self.current_hash = self.current_cloud_hash
        self.setWindowTitle("Change skin")
        self.current_texture_path = account.skin_path()
        self.current_cape_path = account.cape_path()
        self.variant = "classic"

    def _build_ui(self):
        self._root_lo = QVBoxLayout(self)

        top_w = QWidget()
        top = QHBoxLayout(top_w)
        mid_w = QWidget()
        mid = QVBoxLayout(mid_w)
        bottom_w = QWidget()
        bottom = QHBoxLayout(bottom_w)
        self._root_lo.addWidget(top_w)
        self._root_lo.addWidget(mid_w)
        self._root_lo.addWidget(bottom_w)

        reset_ico = resources.symbol("circle-counter-clockwise")
        self.reset_button = QPushButton(reset_ico, "")
        self.reset_button.setDisabled(True)
        self.reset_button.setProperty("large", True)
        self.reset_button.setFixedHeight(33)
        self.reset_button.clicked.connect(self.set_skin_initial)

        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("(use current)")
        self.file_input.setDisabled(True)
        self.file_input.textChanged.connect(self._change_preview)

        browse_button = QPushButton(resources.symbol("folder-plus"), "Browse")
        browse_button.setProperty("large", True)
        browse_button.clicked.connect(self._open_file_picker)

        top.addWidget(self.reset_button)
        top.addWidget(self.file_input, 1)
        top.addWidget(browse_button)

        cape_label = QLabel("Cape")

        self.cape_list = QListWidget()
        self.cape_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.cape_list.setIconSize(QSize(64, 64))
        cape_list_none = QListWidgetItem()
        cape_list_none.setText("None")
        cape_list_none.setData(256, None)
        cape_list_none.setData(257, None)
        cape_list_none.setSizeHint(QSize(54, 80))
        self.cape_list.addItem(cape_list_none)
        self.cape_list.setProperty("icons", True)
        self.cape_list.setMovement(QListWidget.Movement.Static)
        if self.account.profile:
            not_found_cape = True
            if self.account.profile.capes:
                for cape in self.account.profile.get_all_cape_thumbs():
                    if (
                        "alias" not in cape
                        or "thumb" not in cape
                        or "id" not in cape
                    ):
                        log.warning("Skipping cape with invalid data")
                        continue
                    alias: str = cape["alias"]  # type: ignore
                    thumb: QPixmap = cape["thumb"]  # type: ignore
                    id_: str = cape["id"]  # type: ignore
                    p: Path = cape["path"]  # type: ignore
                    item = QListWidgetItem()
                    item.setToolTip(alias)
                    item.setData(256, id_)
                    item.setData(257, p)
                    item.setIcon(thumb)
                    item.setSizeHint(QSize(54, 80))
                    self.cape_list.addItem(item)
                    if not_found_cape:
                        if cape.get("state", "INACTIVE") == "ACTIVE":
                            not_found_cape = False
                            self.cape_list.setCurrentItem(item)
                            self.current_cape_cloud_idx = (
                                self.cape_list.currentRow()
                            )
                if not_found_cape:
                    self.cape_list.setCurrentRow(0)
                    self.current_cape_cloud_idx = 0
        self.cape_list.setMaximumHeight(94)
        self.cape_list.setMinimumHeight(94)
        self.cape_list.setAutoScroll(False)
        self.cape_list.setFlow(QListWidget.Flow.LeftToRight)
        self.cape_list.setWrapping(False)
        self.cape_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        if self.cape_list.count() > 1:
            mid.addWidget(cape_label)
            mid.addWidget(self.cape_list, 0)
        self.cape_list.currentItemChanged.connect(self._cape_changed)

        preview_row_w = QWidget()
        preview_row = QHBoxLayout(preview_row_w)
        preview_row_w.setContentsMargins(0, 0, 0, 0)
        preview_row.setContentsMargins(0, 0, 0, 0)
        preview_row.setSpacing(10)

        preview_label = QLabel("Preview")
        preview_row.addWidget(preview_label)

        self.show_anim_sel = QCheckBox("Animate")
        self.show_anim_sel.setChecked(config.show_animation_on_skin_dialog)
        self.show_anim_sel.checkStateChanged.connect(self._show_anim)
        preview_row.addWidget(self.show_anim_sel)

        preview_row.addStretch()

        self.__bg = QButtonGroup(self)
        self.classic_sel = QRadioButton("Classic")
        self.classic_sel.clicked.connect(self._classic_selected)
        self.slim_sel = QRadioButton("Slim")
        self.slim_sel.clicked.connect(self._slim_selected)
        self.__bg.addButton(self.classic_sel)
        self.__bg.addButton(self.slim_sel)
        preview_row.addWidget(self.classic_sel)
        preview_row.addWidget(self.slim_sel)

        mid.addWidget(preview_row_w)

        self.skin_preview = QQuickWidget()
        surface_format = QSurfaceFormat()
        self.skin_preview.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop)
        self.skin_preview.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.skin_preview.setResizeMode(
            QQuickWidget.ResizeMode.SizeRootObjectToView
        )
        self.skin_preview.setClearColor(Qt.GlobalColor.transparent)
        self.skin_preview.setFormat(surface_format)
        self.engine = self.skin_preview.engine()
        self.skin_preview.setSource(QUrl("qrc:/3d/steve/scene.qml"))
        self.sp_root = self.skin_preview.rootObject()
        self.player_model = self.sp_root.findChild(QObject, "steveModel")
        self.skin_preview.setMinimumHeight(300)
        self.skin_preview.setMinimumWidth(300)
        mid.addWidget(self.skin_preview, 1)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        self.submit_button = QPushButton("Confirm")
        self.submit_button.setDisabled(True)
        self.submit_button.clicked.connect(self._upload)

        bottom.addWidget(cancel_button)
        bottom.addWidget(self.submit_button)

    def exec(self) -> int:
        self.set_skin_initial()
        return super().exec()

    def _slim_selected(self):
        self.skin_preview.setSource(QUrl("qrc:/3d/alex/scene.qml"))
        self.sp_root = self.skin_preview.rootObject()
        self.player_model = self.sp_root.findChild(QObject, "steveModel")
        if self.player_model:
            self.player_model.setProperty(
                "skin", QUrl.fromLocalFile(self.current_texture_path)
            )
            self.player_model.setProperty(
                "cape", QUrl.fromLocalFile(self.current_cape_path or "")
            )
        self.variant = "slim"
        self._show_anim(self.show_anim_sel.checkState())

    def _classic_selected(self):
        self.skin_preview.setSource(QUrl("qrc:/3d/steve/scene.qml"))
        self.sp_root = self.skin_preview.rootObject()
        self.player_model = self.sp_root.findChild(QObject, "steveModel")
        if self.player_model:
            self.player_model.setProperty(
                "skin", QUrl.fromLocalFile(self.current_texture_path)
            )
            self.player_model.setProperty(
                "cape", QUrl.fromLocalFile(self.current_cape_path or "")
            )
        self.variant = "classic"
        self._show_anim(self.show_anim_sel.checkState())

    def set_skin_initial(self):
        self.reset_button.setDisabled(True)
        self.file_input.setText(None)
        self.submit_button.setDisabled(True)
        if self.player_model:
            if self.account.profile:
                match self.account.profile.current_skin_model():
                    case SkinModel.CLASSIC:
                        self.classic_sel.click()
                    case SkinModel.SLIM:
                        self.slim_sel.click()
            p = self.account.skin_path()
            self.current_texture_path = p
            c = self.account.cape_path() or ""
            self.current_cape_path = c
            self.player_model.setProperty("skin", QUrl.fromLocalFile(p))
            self.player_model.setProperty("cape", QUrl.fromLocalFile(c))
            self.cape_list.setCurrentRow(self.current_cape_cloud_idx)
        else:
            log.warning("No player model instance!")

    def closeEvent(self, arg__1: QCloseEvent) -> None:
        f = self.skin_preview.format()
        f.setProfile(f.OpenGLContextProfile.NoProfile)
        f.setRenderableType(f.RenderableType.DefaultRenderableType)
        del f
        self.engine.collectGarbage()
        self.engine.clearComponentCache()
        self.engine.clearSingletons()
        self.sp_root.deleteLater()
        self.engine.deleteLater()
        self.skin_preview.deleteLater()
        QSurfaceFormat.setDefaultFormat(self._current_win_environment)
        super().closeEvent(arg__1)
        return self.deleteLater()

    def _change_preview(self, fp: str):
        if not os.path.isfile(fp):
            return
        if fp.split(".")[-1] != "png":
            log.warning("Not a PNG: '%s'", fp)
            self.file_input.setText(None)
            return
        self.current_texture_path = fp
        with open(fp, "rb") as file:
            sha = hashlib.sha256(file.read()).hexdigest()
            self.current_hash = sha
        if (
            sha == self.current_cloud_hash
            and self.current_cape == self.current_cape_cloud
        ):
            self.reset_button.setDisabled(True)
            self.submit_button.setDisabled(True)
        else:
            self.reset_button.setDisabled(False)
            self.submit_button.setDisabled(False)
        if self.player_model:
            self.player_model.setProperty("skin", QUrl.fromLocalFile(fp))

    def _open_file_picker(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Select skin",
            str(Path("~").expanduser().resolve()),
            "PNG image (*.png);",
        )
        if not file:
            return
        if not os.path.isfile(file):
            log.warning("Invaild file path: '%s'", file)
            return
        img = QImage()
        img.load(file)
        if img.width() != 64 or img.height() not in (64, 32):
            self.set_skin_initial()
            error_box("Invalid skin! Must be 64x64 or 64x32!")
            return
        del img
        self.file_input.setText(file)

    def _upload(self):
        if self.current_hash != self.current_cloud_hash:
            skin_success = self._upload_skin()
        else:
            skin_success = True
        if self.current_cape != self.current_cape_cloud:
            cape_success = self._set_cape()
        else:
            cape_success = True

        if self.account.profile:
            self.account.profile.refresh_profile_info()
            account_manager.save_accounts()
        if skin_success and cape_success:
            self.accept()

    def _set_cape(self):
        if not self.account.token:
            self.account.refresh()
        assert self.account.token
        headers = {"Authorization": f"Bearer {self.account.token.access_token}"}
        if self.current_cape:
            try:
                payload = {"capeId": self.current_cape}
                resp = SESSION.put(CAPE_URL, headers=headers, json=payload)
                resp.raise_for_status()
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ConnectTimeout,
            ) as err:
                log.warning(
                    "Cape PUT request failed to open connection:", exc_info=err
                )
                error_box(
                    "Failed to connect to server. "
                    "Check that you are not offline and try again. "
                    "If the error persists and you are definitely online, "
                    "please create a bug report."
                )
            except requests.exceptions.HTTPError as err:
                log.warning(
                    "Cape PUT request returned HTTP %d:\nDetails: %s",
                    err.response.status_code,
                    err.response.text,
                )
                c = self.cape_list.currentItem().text()
                if "profile does not own cape" in err.response.text:
                    error_box(
                        f'Failed to set cape to "{c}": You do not own it.'
                    )
                else:
                    error_box(
                        f'Failed to set cape to "{c}": An unknown error '
                        "occured."
                    )
            else:
                return True
        else:
            try:
                resp = SESSION.delete(CAPE_URL, headers=headers)
                resp.raise_for_status()
            except Exception as err:
                log.error("Failed to remove cape from player:", exc_info=err)
                raise
            else:
                return True
        return False

    def _upload_skin(self):
        if not self.account.profile:
            self.account.get_profile_info()
        assert self.account.profile
        current_skin_hash = self.account.profile.current_skin["url"].split("/")[
            -1
        ]
        if current_skin_hash == self.current_hash:
            error_box("Skin is already set to this!")
            return False
        if not self.account.token:
            error_box("Invalid access token")
            return False
        headers = {"Authorization": f"Bearer {self.account.token.access_token}"}

        fp = self.file_input.text()
        name = "img_"

        for char in fp.split(OS_PATH_DELIM)[-1]:
            if char not in [*ascii_letters, "."]:
                continue
            name = "".join([*name, char])

        try:
            resp = SESSION.post(
                SKIN_CHANGE_URL,
                headers=headers,
                files={
                    "variant": ("", self.variant),
                    "file": (name, open(fp, "rb"), "image/png"),
                },
            )
            resp.raise_for_status()
        except Exception as err:
            log.error("Failed to upload skin:", exc_info=err)
            raise
        else:
            return True

    def _show_anim(self, s: Qt.CheckState):
        if s == Qt.CheckState.Checked:
            config.show_animation_on_skin_dialog = True
            if self.player_model:
                self.player_model.metaObject().invokeMethod(
                    self.player_model, "enableAnimation"  # type: ignore
                )
            return
        else:
            config.show_animation_on_skin_dialog = False
            if self.player_model:
                self.player_model.metaObject().invokeMethod(
                    self.player_model, "disableAnimation"  # type: ignore
                )

    def _cape_changed(self, item: QListWidgetItem):
        id_: str | None = item.data(256)
        path: Path | None = item.data(257)

        self.current_cape = id_
        self.current_cape_path = path

        if self.player_model:
            self.player_model.setProperty(
                "cape", QUrl.fromLocalFile(path or "")
            )

        if (
            self.current_cape == self.current_cape_cloud
            and self.current_hash == self.current_cloud_hash
        ):
            self.reset_button.setDisabled(True)
            self.submit_button.setDisabled(True)
        else:
            self.reset_button.setEnabled(True)
            self.submit_button.setEnabled(True)
