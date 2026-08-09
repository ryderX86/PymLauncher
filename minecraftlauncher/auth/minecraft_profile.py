from functools import lru_cache
from datetime import timedelta
from pathlib import Path
from enum import StrEnum
import logging
import hashlib
import uuid
import time
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QIcon, QPixmap, QPainter
import requests
import requests.exceptions

from minecraftlauncher.auth.minecraft_token import MinecraftToken
from minecraftlauncher.constants import (
    MOJ_PROF_URL,
    STEVE_SKIN_URL,
)
from minecraftlauncher.back.download_helpers import download as try_request
from minecraftlauncher import SESSION
from minecraftlauncher.offline import offline_man
from minecraftlauncher.front import resources
from minecraftlauncher.paths import paths

log = logging.getLogger(__name__)

KNOWN_DICT_KEYS = ["id", "name", "skins", "capes", "last_updated"]

_STEVE_UUID = str(uuid.UUID(int=0))

_cached_skins: dict[str, QIcon] = {}
_cached_capes: dict[str, QPixmap] = {}


class TextureState(StrEnum):
    """Enums for skin/cape "state\"."""

    ACTIVE = "ACTIVE"
    """Skin/cape is in use and will show in-game"""
    INACTIVE = "INACTIVE"
    """Skin/cape is not in use and will not show in-game"""


class SkinModel(StrEnum):
    CLASSIC = "CLASSIC"
    """Classic/Steve skin model"""
    SLIM = "SLIM"
    """Slim/Alex skin model"""

    # aliases
    STEVE = CLASSIC
    """Alias for `CLASSIC`"""
    ALEX = SLIM
    """Alias for `SLIM`"""


@lru_cache(maxsize=48)
def check_redownload_skin(
    p: str, url: str, sha: str | None = None, name: str | None = None
):
    if not sha:
        sha = url.split("/")[-1]
    name = name or "".join([sha[:10], "..."])
    if os.path.isfile(p):
        with open(p, "rb") as b:
            file_sha = hashlib.sha256(b.read()).hexdigest()
        if file_sha == sha:
            return
        else:
            log.warning("Cached texture %r has mismatched SHA", name)
    if name:
        log.debug("Downloading player texture for %r", name)
    resp = try_request(url)
    with open(p, "wb") as b:
        b.write(resp.content)
    return


class MinecraftProfile:
    default_skin_inf = {
        "id": _STEVE_UUID,
        "state": "ACTIVE",
        "url": STEVE_SKIN_URL,
        "textureKey": STEVE_SKIN_URL.rsplit("/", maxsplit=1)[-1],
        "variant": "CLASSIC",
    }
    __slots__ = (
        "uuid",
        "name",
        "skins",
        "capes",
        "last_updated",
        "_other_info",
        "_token",
        "_cape_list_cache",
        "_cape_thumbnails",
        "current_cape",
        "current_skin",
    )
    # included by API
    uuid: str
    name: str
    skins: list[dict[str, str]]
    capes: list[dict[str, str]]

    # saved variables
    last_updated: float
    """
    Last time we retrieved/updated this profile
    """
    _other_info: dict
    """
    Other dict entries that we don't know what to do with
    """

    # cached variables
    _token: MinecraftToken | None
    _cape_list_cache: list[tuple[str, str, str, QImage]] | None
    """
    QImage cache
    """
    _cape_thumbnails: list[tuple[str, str, str, QImage]] | None
    """
    QImage cache
    """
    current_cape: dict[str, str] | None
    current_skin: dict[str, str]

    def __init__(
        self, profile_info: dict, mc_token: MinecraftToken | None = None
    ):
        """Don't use this for new profiles. Use `cls.from_token()` instead."""
        self._token = mc_token
        self.uuid = profile_info["id"]
        self.name = profile_info.get("name", "Steve")
        self.skins = profile_info.get("skins", [])
        self.capes = profile_info.get("capes", [])
        self.last_updated: float = profile_info.get("last_updated", 0.0)
        self._other_info = {
            k: v for k, v in profile_info.items() if k not in KNOWN_DICT_KEYS
        }
        self._cape_list_cache = None
        self._cape_thumbnails = None

        self.current_skin = self.default_skin_inf

        self.current_cape = None
        self._check_current_skin()

    def _check_current_skin(self) -> None:
        self.current_skin = self.default_skin_inf
        if self.skins:
            current: dict | None = None
            for skin in self.skins:
                state = skin["state"]
                if state != TextureState.ACTIVE:
                    continue
                current = skin
                break
            if current:
                self.current_skin = current
            del current

        self.current_cape = None
        if self.capes:
            current: dict | None = None
            for cape in self.capes:
                if cape["state"] != TextureState.ACTIVE:
                    continue
                current = cape
                break
            if current:
                self.current_cape = current
            del current

    @staticmethod
    def steve_skin_bytes():
        skin_path = os.path.join(
            os.path.join(paths.textures_cache, "skins"), f"{_STEVE_UUID}.png"
        )
        check_redownload_skin(skin_path, STEVE_SKIN_URL)
        with open(skin_path, "rb") as file:
            b = file.read()
        return b

    @staticmethod
    def steve_skin_path():
        skin_path = os.path.join(
            os.path.join(paths.textures_cache, "skins"), f"{_STEVE_UUID}.png"
        )
        check_redownload_skin(skin_path, STEVE_SKIN_URL)
        return skin_path

    @staticmethod
    def steve_skin_icon():
        uid = _STEVE_UUID + "_thumb"
        if uid in _cached_skins:
            return _cached_skins[uid]
        img_bytes = MinecraftProfile.steve_skin_bytes()
        img = QImage()
        img.loadFromData(img_bytes)
        img.setText("id", uid)
        ico = resources.icon_from_qimg(img.copy(8, 8, 8, 8), True)
        _cached_skins[uid] = ico
        return _cached_skins[uid]

    @classmethod
    def from_token(cls, mc_token: MinecraftToken):
        headers = {"Authorization": f"Bearer {mc_token.access_token}"}

        response = None
        try:
            response = SESSION.get(MOJ_PROF_URL, headers=headers)
            response.raise_for_status()
        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ConnectionError,
        ) as err:
            log.error("Failed to connect to %s:", MOJ_PROF_URL, exc_info=err)
            offline_man.check_requests_error(err)
            raise RuntimeError(
                f"Failed to connect to {MOJ_PROF_URL!r}"
            ) from err
        except requests.HTTPError as err:
            log.error("Failed to fetch profile info!:", exc_info=err)
            raise
        except Exception as err:
            log.error(
                "Unknown error occured while fetching profile info:",
                exc_info=err,
            )
            raise

        if response is None:
            raise ValueError("Repsonse shouldn't be none!")
        prof_info_json = response.json()
        prof_info_json["last_updated"] = time.time()

        return cls(prof_info_json, mc_token)

    @property
    def should_refresh(self):
        if not self.token:
            return False
        elif not self.last_updated:
            return True
        elif (
            self.last_updated
            < time.time() - timedelta(minutes=5).total_seconds()
        ):
            return True
        return False

    @property
    def token(self):
        return self._token.access_token if self._token else None

    @token.setter
    def token(self, token: MinecraftToken):
        self._token = token

    @property
    def _req_header(self):
        return {"Authorization": f"Bearer {self.token}"}

    def refresh_profile_info(self):
        if not self._token:
            raise RuntimeError("No Minecraft token present")
        headers = {"Authorization": f"Bearer {self.token}"}

        response = None
        try:
            response = SESSION.get(MOJ_PROF_URL, headers=headers)
            response.raise_for_status()
        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ConnectionError,
        ) as err:
            log.warning(
                "Failed to connect to %s: %s",
                MOJ_PROF_URL,
                err.__qualname__,
            )
            offline_man.check_requests_error(err)
            raise RuntimeError(
                f"Failed to connect to {MOJ_PROF_URL!r}"
            ) from err
        except requests.HTTPError as err:
            log.error(
                "Failed to fetch profile info: HTTP %s",
                err.response.status_code,
            )
            raise err
        except Exception as err:
            log.error(
                "Unknown error occured fetching profile info:",
                exc_info=True,
            )
            raise err

        if response is None:
            raise ValueError("Response shouldn't be none!")
        prof_info_json: dict = response.json()

        # dummy data in case of demo account
        self.uuid = prof_info_json.get("id", "UNKNOWN")
        self.name = prof_info_json.get("name", "Steve")
        self.skins = prof_info_json.get("skins", [])
        self.capes = prof_info_json.get("capes", [])

        self.last_updated = time.time()
        self._check_current_skin()
        return self

    def serialize(self):
        """
        Convert this into a dict
        """
        return {
            k: v
            for k, v in {
                "id": self.uuid,
                "name": self.name,
                "skins": self.skins,
                "capes": self.capes,
                "last_updated": self.last_updated,
                **self._other_info,
            }.items()
            if v
        }

    def current_skin_bytes(self):
        p = os.path.join(
            os.path.join(paths.textures_cache, "skins"),
            f"{self.current_skin["textureKey"]}.png",
        )
        check_redownload_skin(
            p,
            self.current_skin["url"],
            name=str(self.current_skin["textureKey"]),
        )
        with open(p, "rb") as file:
            b = file.read()
        return b

    def current_skin_path(self):
        p = os.path.join(
            os.path.join(paths.textures_cache, "skins"),
            f"{self.current_skin["textureKey"]}.png",
        )
        check_redownload_skin(
            p,
            self.current_skin["url"],
            name=str(self.current_skin["textureKey"]),
        )
        return p

    def current_skin_model(self) -> str:
        return self.current_skin["variant"]

    def current_skin_icon(self):
        uid = self.current_skin["textureKey"] + "_thumb"
        if uid in _cached_skins:
            return _cached_skins[uid]
        img_bytes = self.current_skin_bytes()
        img = QImage()
        img.loadFromData(img_bytes)

        head = img.copy(8, 8, 8, 8)
        head_large = head.scaled(
            240,
            240,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        hat = img.copy(40, 8, 8, 8)
        hat_large = hat.scaled(
            256,
            256,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        result = QImage(8, 8, QImage.Format.Format_ARGB32)
        result.fill(Qt.GlobalColor.transparent)
        result_large = result.scaled(256, 256)
        painter = QPainter(result)
        painter_large = QPainter(result_large)

        painter.drawImage(0, 0, head)
        painter.drawImage(0, 0, hat)
        painter.end()
        painter_large.drawImage(8, 8, head_large)
        painter_large.drawImage(0, 0, hat_large)
        painter_large.end()
        result.setText("id", uid)
        result_large.setText("id", uid)

        ico = resources.icon_from_qimg(result, True)
        ico.addPixmap(QPixmap.fromImage(result_large))
        _cached_skins[uid] = ico
        return _cached_skins[uid]

    def get_all_cape_paths(self) -> list[dict[str, str]]:
        capes_out = []
        for cape in self.capes:
            url: str = cape["url"]
            sha = url.split("/")[-1]
            p = os.path.join(
                os.path.join(paths.textures_cache, "capes"), f"{sha}.png"
            )
            check_redownload_skin(p, url, sha, name=cape["alias"])
            new_cape_obj = {**cape, "path": p}
            capes_out.append(new_cape_obj)
        return capes_out

    def get_all_cape_thumbs(self) -> list[dict[str, str | Path | QPixmap]]:
        capes_out = []
        c = self.get_all_cape_paths()
        for cape in c:
            name = cape["alias"]
            if name + "_thumb" in _cached_capes:
                cape["thumb"] = _cached_capes[name + "_thumb"]  # type: ignore
                capes_out.append(cape)
                continue
            img_full = QImage()
            img_full.load(str(cape["path"]))
            img = img_full.copy(1, 1, 10, 16).scaledToHeight(256)
            pix = QPixmap.fromImage(img)
            del img_full, img
            _cached_capes[name + "_thumb"] = pix
            cape["thumb"] = _cached_capes[name + "_thumb"]  # type: ignore
            capes_out.append(cape)
        return capes_out

    def current_cape_path(self):
        if self.current_cape:
            url: str = self.current_cape["url"]
            assert isinstance(url, str)
            sha = url.split("/")[-1]
            p = os.path.join(
                os.path.join(paths.textures_cache, "capes"), f"{sha}.png"
            )
            check_redownload_skin(p, url, sha)
            return p
        return None
