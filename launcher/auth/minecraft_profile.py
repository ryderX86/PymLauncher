from enum import StrEnum
from functools import lru_cache
from json import JSONDecodeError
import hashlib
import logging
import os
import time
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap

from launcher import constants, paths
from launcher.auth.minecraft_token import MinecraftToken
from launcher.constants import SKIN_URL_BASE
from launcher.datatypes.default_skins import DefaultSkin, DefaultSkinSHA
from launcher.exceptions.network import (
    HTTPStatusCodeError,
    WrappedUL3Exception,
)
from launcher.front import resources
from launcher.networking import make_request
from launcher.offline import offline_man

from .exceptions import (
    BaseProfileError,
    NoConnectionError,
    ProfileNotFoundError,
    UnauthorizedError,
)

log = logging.getLogger(__name__)

KNOWN_DICT_KEYS = ["id", "name", "skins", "capes", "last_updated"]

TRIAL_UUID = "00000000-0000-0000-0000-000000000000"

_cached_skins: dict[str, QIcon] = {}
_cached_capes: dict[str, QPixmap] = {}


class TextureState(StrEnum):
    """Enums for skin/cape "state" """

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


@lru_cache(maxsize=32)
def check_redownload_skin(
    p: str, url: str, sha: str | None = None, name: str | None = None
):
    if not sha:
        sha = url.split("/")[-1]
    name = name or "".join([sha[:10], "..."])
    if os.path.isfile(p):
        if os.lstat(p).st_atime >= (time.time() - (1000 * 60 * 60 * 24)):
            return
        with open(p, "rb") as b:
            file_sha = hashlib.sha256(b.read()).hexdigest()
        if file_sha == sha:
            return
        else:
            log.warning("Cached texture %r has mismatched SHA", name)
    if name:
        log.debug("Downloading player texture for %r", name)
    resp = make_request("get", url)
    with open(p, "wb") as b:
        b.write(resp.data)
    return


@lru_cache(maxsize=32)
def check_redownload_cape(
    p: str, url: str, sha: str | None = None, name: str | None = None
):
    if not sha:
        sha = url.split("/")[-1]
    name = name or "".join([sha[:10], "..."])
    if os.path.isfile(p):
        if os.lstat(p).st_atime >= (time.time() - (1000 * 60 * 60 * 24)):
            return
        else:
            log.debug("Old cape texture at %r; re-downloading it.", p)
    if name:
        log.debug("Downloading player texture for %r", name)
    resp = make_request("get", url)
    with open(p, "wb") as b:
        b.write(resp.data)
    return


class MinecraftProfile:
    default_skin_inf = {
        "id": TRIAL_UUID,
        "state": "ACTIVE",
        "url": constants.STEVE_SKIN_URL,
        "textureKey": constants.STEVE_SKIN_URL.rsplit("/", maxsplit=1)[-1],
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
        "_is_demo_profile",
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
    _is_demo_profile: bool

    def __init__(
        self,
        profile_info: dict,
        mc_token: MinecraftToken | None = None,
        demo_profile: bool = False,
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
        self._is_demo_profile = demo_profile

        self.current_cape = None
        self._check_current_skin()

    def _check_current_skin(self) -> None:
        self.current_skin = self.default_skin_inf
        if self.skins:
            current: dict | None = None
            for skin in self.skins:
                state = skin["state"]
                if state == TextureState.ACTIVE:
                    current = skin
                    break
            if current:
                self.current_skin = current
            del current

        self.current_cape = None
        if self.capes:
            current: dict | None = None
            for cape in self.capes:
                if cape["state"] == TextureState.ACTIVE:
                    current = cape
                    break
            if current:
                self.current_cape = current
            del current

    @staticmethod
    def steve_skin_bytes():
        skin_path = os.path.join(
            os.path.join(paths.textures_cache, "skins"), f"{TRIAL_UUID}.png"
        )
        check_redownload_skin(skin_path, constants.STEVE_SKIN_URL)
        with open(skin_path, "rb") as file:
            b = file.read()
        return b

    @staticmethod
    def steve_skin_path():
        skin_path = os.path.join(
            os.path.join(paths.textures_cache, "skins"), f"{TRIAL_UUID}.png"
        )
        check_redownload_skin(skin_path, constants.STEVE_SKIN_URL)
        return skin_path

    @classmethod
    def default_skin_icon(cls):
        if "UNKNOWN" in _cached_skins:
            return _cached_skins["UNKNOWN"]
        img = QPixmap(":/skin-placeholders/unknown.png").toImage()
        ico = resources.icon_from_qimg(img, True)
        _cached_skins["UNKNOWN"] = ico
        return _cached_skins["UNKNOWN"]

    @staticmethod
    def _get_profile_json(mc_token: MinecraftToken):
        headers = {"Authorization": f"Bearer {mc_token.access_token}"}

        try:
            response = make_request(
                "get", constants.MOJ_PROF_URL, headers=headers
            )
        except HTTPStatusCodeError as err:
            if err.code == 401:  # Unauthorized
                raise UnauthorizedError(
                    err.response, err.body or err.desc
                ) from err
            try:
                j = err.response.json()
            except JSONDecodeError as err2:
                log.warning(
                    "Failed to decode response from Mojang:", exc_info=err2
                )
                raise BaseProfileError.auto_select_class(err.code)(
                    err.code, constants.MOJ_PROF_URL
                ) from err
            path = j.get("path", constants.MOJ_PROF_URL)
            msg = j.get("error", "<unknown>")
            err_msg = j.get("errorMessage", "<unknown>")
            raise BaseProfileError.auto_select_class(err.code)(
                err.code, path, msg, err_msg
            )
        except WrappedUL3Exception as err:
            log.error(
                "Failed to get profile info from %r:",
                constants.MOJ_PROF_URL,
                exc_info=err,
            )
            if offline_man.check_requests_error(err):
                raise NoConnectionError(constants.MOJ_PROF_URL, err) from err
            raise BaseProfileError() from err
        except Exception as err:
            log.error(
                "Unexpected error occured while fetching profile info:",
                exc_info=err,
            )
            raise

        prof_info_json = response.json()
        prof_info_json["last_updated"] = time.time()

        return prof_info_json

    @classmethod
    def from_token(cls, mc_token: MinecraftToken):
        try:
            return cls(cls._get_profile_json(mc_token))
        except ProfileNotFoundError as err:
            log.warning(
                "No account profile, setting to demo profile", exc_info=err
            )
            return cls(
                {"id": TRIAL_UUID, "name": "Demo Player"},
                mc_token,
                demo_profile=True,
            )

    @property
    def should_refresh(self):
        if not self.token:
            return False
        elif not self.last_updated:
            return True
        elif self.last_updated < time.time() - constants.TINY_CACHE_TIME:
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
        if self._is_demo_profile and not (
            self._token and self._token.owns_game
        ):
            log.debug("Skipping profile refresh on demo account")
            self.last_updated = time.time()
            return self
        elif self._is_demo_profile:
            log.warning(
                "Account with demo profile owns game, "
                "changing to full profile and refreshing."
            )
            self._is_demo_profile = False
        if not self._token:
            raise RuntimeError("No Minecraft token present")

        prof_info_json: dict = self._get_profile_json(self._token)

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
        if self._is_demo_profile or not self.current_skin:
            return self.get_default_skin_icon()
        uid = self.current_skin["textureKey"] + "_thumb"
        if uid in _cached_skins:
            return _cached_skins[uid]
        try:
            img_bytes = self.current_skin_bytes()
        except Exception as err:
            log.error("Failed to fetch current skin:", exc_info=err)
            return self.get_default_skin_icon()
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
            check_redownload_cape(p, url, sha, name=cape["alias"])
            new_cape_obj = {**cape, "path": p}
            capes_out.append(new_cape_obj)
        return capes_out

    def get_all_cape_thumbs(self) -> list[dict[str, str | QPixmap]]:
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
            check_redownload_cape(p, url, sha)
            return p
        return None

    def get_default_skin_path(self):
        skin = self.get_default_skin_name()
        sha256 = DefaultSkinSHA[skin.name]
        path = os.path.join(paths.textures_cache, "skins", f"{sha256}.png")
        check_redownload_skin(path, f"{SKIN_URL_BASE}/{sha256}", skin)
        return path

    def get_default_skin_bytes(self):
        with open(self.get_default_skin_path(), "rb") as file:
            return file.read()

    def get_default_skin_name(self, legacy: bool = False) -> DefaultSkin:
        if self.uuid == TRIAL_UUID:
            return DefaultSkin.STEVE

        uid = uuid.UUID(self.uuid)

        most = (uid.int >> 64) & 0xFFFFFFFFFFFFFFFF
        least = uid.int & 0xFFFFFFFFFFFFFFFF

        hilo = most ^ least

        upper_32 = (hilo >> 32) & 0xFFFFFFFF
        lower_32 = hilo & 0xFFFFFFFF
        hash_code = upper_32 ^ lower_32

        if hash_code & 0x80000000:
            hash_code -= 0x100000000

        if legacy:
            return (
                DefaultSkin.ALEX if (hash_code & 1) == 1 else DefaultSkin.STEVE
            )
        index = hash_code % 9
        skins = (
            DefaultSkin.STEVE,
            DefaultSkin.SUNNY,
            DefaultSkin.ALEX,
            DefaultSkin.NOOR,
            DefaultSkin.ARI,
            DefaultSkin.ZURI,
            DefaultSkin.MAKENA,
            DefaultSkin.KAI,
            DefaultSkin.EFE,
        )
        return skins[index]

    def get_default_skin_icon(self, legacy: bool = False):
        name = self.get_default_skin_name(legacy=legacy)

        if name.value in _cached_skins:
            return _cached_skins[name.value]

        img = QPixmap(
            f":/skin-placeholders/default_{name.value}.png"
        ).toImage()
        ico = resources.icon_from_qimg(img, True)
        _cached_skins[name.value] = ico
        return _cached_skins[name.value]
