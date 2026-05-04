from datetime import datetime, timedelta
from string import ascii_letters, digits
from functools import lru_cache
from typing import Literal
from pathlib import Path
from enum import StrEnum
import logging
import hashlib
import uuid
import time

from PySide6.QtGui import QImage, QIcon, QPixmap
import requests
import requests.exceptions

from minecraftlauncher.auth.minecraft_token import MinecraftToken
from minecraftlauncher.constants import (
    MOJ_PROF_URL,
    STEVE_SKIN_URL,
    NAME_CHANGE_INFO_URL,
    USERNAME_CHANGE_URL,
    USERNAME_CHECK_URL,
)
from minecraftlauncher.back.download_helpers import download as try_request
from minecraftlauncher import constants, session
from minecraftlauncher.functions import indent
from minecraftlauncher.front import resources
from .exceptions import NameChangeError, TooManyRequestsError

log = logging.getLogger(__name__)

KNOWN_DICT_KEYS = ["id", "name", "skins", "capes", "last_updated"]

_STEVE_UUID = str(uuid.UUID(int=0))
SKIN_CACHE_PATH = resources.TEXTURE_CACHE_DIR / "skins"
CAPE_CACHE_PATH = resources.TEXTURE_CACHE_DIR / "capes"
if not SKIN_CACHE_PATH.exists():
    SKIN_CACHE_PATH.mkdir(parents=True, exist_ok=True)
if not CAPE_CACHE_PATH.exists():
    CAPE_CACHE_PATH.mkdir(parents=True, exist_ok=True)

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
    p: Path, url: str, sha: str | None = None, name: str | None = None
):
    if not sha:
        sha = url.split("/")[-1]
    name = name or "".join([sha[:10], "..."])
    if p.exists():
        file_sha = hashlib.sha256(p.read_bytes()).hexdigest()
        if file_sha == sha:
            return
        else:
            log.warning("Cached texture '%s' has mismatched SHA", name)
    if name:
        log.debug("Downloading player texture for '%s'", name)
    resp = try_request(url)
    p.write_bytes(resp.content)
    return


class MinecraftProfile:
    _token: MinecraftToken | None
    owned_items: list
    uuid: str
    name: str
    skins: list[dict[str, str]]
    capes: list[dict[str, str]]

    rate_limit_end: datetime | None
    na_rate_limit_end: datetime | None
    """
    Rate limit specific to /minecraft/profile/{name}/available
    """

    def __init__(
        self, profile_info: dict, mc_token: MinecraftToken | None = None
    ):
        """Don't use this for new profiles. Use `cls.from_token()` instead."""
        self._token = mc_token
        self.uuid = profile_info["id"]
        self.name = profile_info.get("name", "Steve")
        self.skins = profile_info.get("skins", [])
        self.capes = profile_info.get("capes", [])
        self.last_updated: float | None = profile_info.get("last_updated")
        self._other_info = {
            k: v for k, v in profile_info.items() if k not in KNOWN_DICT_KEYS
        }
        self._cape_list_cache: list[tuple[str, str, str, QImage]] | None = None
        self._cape_thumbnails: list[tuple[str, str, str, QImage]] | None = None

        self.current_skin = self._default_skin_inf = {
            "id": _STEVE_UUID,
            "state": "ACTIVE",
            "url": STEVE_SKIN_URL,
            "textureKey": STEVE_SKIN_URL.rsplit("/", maxsplit=1)[-1],
            "variant": "CLASSIC",
        }

        self.current_cape = None
        self._check_current_skin()
        self.rate_limit_end = None
        self.na_rate_limit_end = None

    def _check_current_skin(self):
        self.current_skin = self._default_skin_inf
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
        skin_path = SKIN_CACHE_PATH / (_STEVE_UUID + ".png")
        check_redownload_skin(skin_path, STEVE_SKIN_URL)
        return skin_path.read_bytes()

    @staticmethod
    def steve_skin_path():
        skin_path = SKIN_CACHE_PATH / (_STEVE_UUID + ".png")
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

        max_retries = 3
        response = None
        while max_retries > 0:
            max_retries -= 1
            try:
                response = session.get(MOJ_PROF_URL, headers=headers)
                response.raise_for_status()
                break
            except (
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError,
            ) as err:
                log.error(
                    "Failed to connect to %s:", MOJ_PROF_URL, exc_info=err
                )
                log.info("Waiting 5 seconds before next attempt...")
                time.sleep(5)
                continue
            except requests.HTTPError as err:
                log.error("Failed to fetch profile info!:", exc_info=err)
                raise
            except Exception as err:
                log.error("Unknown error occured while fetching profile info:")
                raise
        if max_retries < 1:
            constants.offline_mode = True

        if response is None:
            raise ValueError("Repsonse shouldn't be none!")
        prof_info_json = response.json()
        prof_info_json["last_updated"] = datetime.now().timestamp()

        return cls(prof_info_json, mc_token)

    @property
    def should_refresh(self):
        if not self.token:
            return False
        elif not self.last_updated:
            return True
        elif (
            self.last_updated
            < (datetime.now() - timedelta(minutes=5)).timestamp()
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

        max_retries = 3
        response = None
        while max_retries > 0:
            max_retries -= 1
            try:
                response = session.get(MOJ_PROF_URL, headers=headers)
                response.raise_for_status()
                break
            except (
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError,
            ) as exc:
                log.warning(
                    "Failed to connect to %s: %s",
                    MOJ_PROF_URL,
                    exc.__qualname__,
                )
                log.debug("Waiting 5 seconds before next attempt")
                time.sleep(5)
                continue
            except requests.HTTPError as exc:
                log.error(
                    "Failed to fetch profile info: HTTP %s",
                    exc.response.status_code,
                )
                raise exc
            except Exception as exc:
                log.error(
                    "Unknown error occured fetching profile info:",
                    exc_info=True,
                )
                raise exc
        if max_retries < 1:
            constants.offline_mode = True

        if response is None:
            raise ValueError("Response shouldn't be none!")
        prof_info_json: dict = response.json()

        # dummy data in case of demo account
        self.uuid = prof_info_json.get("id", "UNKNOWN")
        self.name = prof_info_json.get("name", "Steve")
        self.skins = prof_info_json.get("skins", [])
        self.capes = prof_info_json.get("capes", [])

        self.last_updated = datetime.now().timestamp()
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
        p = SKIN_CACHE_PATH / (str(self.current_skin["textureKey"]) + ".png")
        check_redownload_skin(
            p,
            self.current_skin["url"],
            name=str(self.current_skin["textureKey"]),
        )
        return p.read_bytes()

    def current_skin_path(self):
        p = SKIN_CACHE_PATH / (str(self.current_skin["textureKey"]) + ".png")
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
        img.setText("id", uid)
        ico = resources.icon_from_qimg(img.copy(8, 8, 8, 8), True)
        _cached_skins[uid] = ico
        return _cached_skins[uid]

    def get_all_cape_paths(self) -> list[dict[str, str]]:
        capes_out = []
        for cape in self.capes:
            url: str = cape["url"]
            sha = url.split("/")[-1]
            p = CAPE_CACHE_PATH / (sha + ".png")
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
            p = CAPE_CACHE_PATH / (sha + ".png")
            check_redownload_skin(p, url, sha)
            return p
        return None

    def is_rl_active(self):
        if not self.rate_limit_end:
            return False
        return (self.rate_limit_end - datetime.now()).total_seconds() > 0

    def is_na_rl_active(self):
        if not self.na_rate_limit_end:
            return False
        return (self.na_rate_limit_end - datetime.now()).total_seconds() > 0

    def check_name_available(
        self, name: str
    ) -> tuple[Literal[True], None] | tuple[Literal[False], str]:
        allowed_chars = "".join([*ascii_letters, *digits, "_"])
        # check the name itself first so we don't spam useless requests for
        # absolutely zero reason
        if len(name) > 16:
            raise ValueError(
                "Name too long. Max length: 16; requested name length: "
                f"{len(name)}"
            )
        elif not all(c in allowed_chars for c in name):
            raise ValueError(
                "Name must only consist of letters, numbers, and underscores."
            )
        elif self.is_rl_active() or self.is_na_rl_active():
            raise TooManyRequestsError(
                self.rate_limit_end or self.na_rate_limit_end,  # type: ignore
                continuation=True,
            )
        try:
            resp = session.get(
                USERNAME_CHECK_URL % name, headers=self._req_header
            )
            resp.raise_for_status()
        except requests.HTTPError as err:
            match err.response.status_code:
                case 429:
                    self.na_rate_limit_end = datetime.now() + timedelta(
                        minutes=5
                    )
                    log.error(
                        "Name availability endpoint returned 429, setting RL "
                        "end to +5 mins. Full text (if any): %s",
                        err.response.text,
                    )
                    raise TooManyRequestsError(self.na_rate_limit_end) from err
                case _:
                    raise err
        else:
            self.na_rate_limit_end = datetime.now() + timedelta(seconds=15)
            resp_json: dict[str, str] = resp.json()
            status = resp_json.get("status")
            match status:
                case "DUPLICATE":
                    return False, "This username is already taken."
                case "AVAILABLE":
                    return True, None
                case "NOT_ALLOWED":
                    return False, "This username doesn't meet the requirements."
                case None:
                    err = RuntimeError("API returned no name status!")
                    err.add_note(f"Original response:\n{indent(resp.text)}")
                    raise err
                case _:
                    err = RuntimeError("Unexpected response from API!")
                    err.add_note(f"API response:\n{indent(resp.text)}")
                    raise err

    def check_can_change_name(self) -> tuple[bool, datetime | None]:
        if self.is_rl_active():
            assert self.rate_limit_end
            raise TooManyRequestsError(self.rate_limit_end, continuation=True)
        try:
            resp = session.get(NAME_CHANGE_INFO_URL, headers=self._req_header)
            resp.raise_for_status()
        except requests.HTTPError as err:
            code = err.response.status_code
            match code:
                case 429:
                    log.error(
                        "Error 429 from Mojang API, cooling off before next "
                        "request"
                    )
                    _api_timeout_expiration = datetime.now() + timedelta(
                        minutes=1
                    )
                    raise TooManyRequestsError(_api_timeout_expiration) from err
                case _:
                    raise err

        info = resp.json()

        last_change = info.get("changedAt", info.get("createdAt"))
        if last_change:
            last_change = datetime.fromisoformat(last_change)
        can_change = info.get("nameChangeAllowed", False)
        return can_change, last_change

    def change_username(self, new_name: str):
        if self.is_rl_active():
            assert self.rate_limit_end
            raise TooManyRequestsError(self.rate_limit_end, continuation=True)
        log.info("Changing player name from '%s' to '%s'", self.name, new_name)

        try:
            resp = session.put(
                USERNAME_CHANGE_URL % new_name, headers=self._req_header
            )
            resp.raise_for_status()
        except requests.HTTPError as err:
            code = err.response.status_code
            match code:
                case 400 | 403:
                    raise NameChangeError(err.response.text) from err
                case 429:
                    log.error(
                        "Error 429 from Mojang API, cooling off before next "
                        "request"
                    )
                    self.rate_limit_end = datetime.now() + timedelta(minutes=5)
                    raise TooManyRequestsError(self.rate_limit_end) from err
                case _:
                    raise err
        else:
            log.info("Name changed successfully.")
            prof_json: dict = resp.json()
            if set(prof_json.keys()) == {"id", "name", "skins", "capes"}:
                log.debug("Using profile data included in request")
                self.uuid = prof_json.get("id", "UNKNOWN")
                self.name = prof_json.get("name", "Steve")
                self.skins = prof_json.get("skins", [])
                self.capes = prof_json.get("capes", [])
            else:
                log.debug("No profile info included, getting our own")
                log.debug("Original response:\n%s", indent(resp.text))
                self.refresh_profile_info()
            return new_name
