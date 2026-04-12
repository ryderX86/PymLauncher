from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import logging
import time

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage
import requests
import requests.exceptions

from minecraftlauncher.datatypes.MinecraftToken import MinecraftToken
from minecraftlauncher.constants import (
    MOJ_PROF_URL, STEVE_SKIN_URL, LAUNCHER_DATA_DIR
)
from minecraftlauncher import constants
from . import try_request

log = logging.getLogger(__name__)

KNOWN_DICT_KEYS = [
    "id", "name", "skins", "capes", "last_updated"
]

SKIN_CACHE_DIR = LAUNCHER_DATA_DIR / "skins"
STEVE_SKIN_CACHE_PATH = SKIN_CACHE_DIR / "_default.png"

_skins_cache:dict[str, QImage] = {}

def get_steve_skin(cls=None) -> QImage:
    if "_" in _skins_cache:
        return _skins_cache["_"]
    elif STEVE_SKIN_CACHE_PATH.exists():
        _skins_cache["_"] = QImage.fromData(STEVE_SKIN_CACHE_PATH.read_bytes())
        _skins_cache["_"].setText("id", "STEVE")
        return _skins_cache["_"]
    log.debug("Getting default Steve skin...")
    max_retries = 3
    resp = None
    while max_retries > 0:
        try:
            resp = requests.get(STEVE_SKIN_URL)
            resp.raise_for_status()
        except (requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError) as err:
                log.error("Failed to connect to %s:" % STEVE_SKIN_URL,
                          exc_info=err)
                log.info("Waiting 5 seconds before next attempt...")
                time.sleep(5)
                continue
        except requests.HTTPError as err:
            log.error("Failed to fetch skin:")
            raise
        except Exception as err:
            log.error("Unknown error occured while fetching skin:")
            raise
        else:
            break
    if resp is None:
        raise RuntimeError("Failed to get skin from API")
    if not SKIN_CACHE_DIR.exists():
        log.debug("Creating skin cache dir: %s"
                  % str(SKIN_CACHE_DIR))
        SKIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STEVE_SKIN_CACHE_PATH.write_bytes(resp.content)
    _skins_cache["_"] = QImage.fromData(resp.content)
    _skins_cache["_"].setText("id", "STEVE")
    return _skins_cache["_"]

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

class MinecraftProfile:
    TextureState = TextureState

    _token:MinecraftToken|None
    owned_items:list
    uuid:str
    name:str
    skins:list[dict[str, str]]
    capes:list[dict[str, str]]

    def __init__(self, profile_info:dict, mc_token:MinecraftToken|None=None):
        """Don't use this for new profiles. Use `cls.from_token()` instead."""
        self._token = mc_token
        self.uuid = profile_info["id"]
        self.name = profile_info.get("name", "Steve")
        self.skins = profile_info.get("skins", [])
        self.capes = profile_info.get("capes", [])
        self.last_updated:float|None = profile_info.get("last_updated")
        self._other_info = {k:v
                            for k, v in profile_info.items()
                            if k not in KNOWN_DICT_KEYS}
        
    @staticmethod
    def default_skin_factory():
        return get_steve_skin()
    
    @staticmethod
    def default_face_factory():
        skin = get_steve_skin()
        return skin.copy(8, 8, 8, 8)

    @classmethod
    def from_token(cls, mc_token:MinecraftToken):
        headers = {
            "Authorization": "Bearer %s" % mc_token.access_token
        }

        max_retries = 3
        response = None
        while max_retries > 0:
            max_retries -= 1
            try:
                response = requests.get(MOJ_PROF_URL, headers=headers)
                response.raise_for_status()
                break
            except (requests.exceptions.ConnectTimeout,
                    requests.exceptions.ConnectionError) as err:
                log.error("Failed to connect to %s:" % MOJ_PROF_URL,
                          exc_info=err)
                log.info("Waiting 5 seconds before next attempt...")
                time.sleep(5)
                continue
            except requests.HTTPError as err:
                log.error("Failed to fetch profile info!:")
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
    
    def get_current_skin(self) -> QImage:
        current:dict|None = None
        if self.skins:
            for skin in self.skins:
                state = skin.get("state", "")
                if state not in TextureState:
                    log.warning(
                        "Cannot determine skin texture status from '%s'"
                        % state
                    )
                    continue
                if state != TextureState.ACTIVE:
                    continue
                id_ = skin.get("id", "")
                if not id_:
                    log.warning("Skin ID not found, continuing")
                    continue
                url = skin.get("url", "")
                if not url:
                    log.warning("Player Skin has no URL, continuing")
                    continue
                variant = skin.get("variant", "")
                if variant not in SkinModel:
                    log.warning("Unknown skin model, defaulting to %s"
                                % SkinModel.CLASSIC)
                    variant = SkinModel.CLASSIC
                current = skin
                break
        if not current:
            return get_steve_skin()
        if current["id"] in _skins_cache:
            return _skins_cache[current["id"]]
        if not SKIN_CACHE_DIR.exists():
            SKIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        texture_path = SKIN_CACHE_DIR / f"{current["id"]}.png"
        if texture_path.exists():
            _skins_cache[current["id"]] = QImage.fromData(
                texture_path.read_bytes()
            )
            _skins_cache[current["id"]].setText("id", current["id"])
            return _skins_cache[current["id"]]
        log.debug("Downloading skin '%s'" % current["id"])
        resp = try_request(log, current["url"])
        texture_path.write_bytes(resp.content)
        _skins_cache[current["id"]] = QImage.fromData(resp.content)
        _skins_cache[current["id"]].setText("id", current["id"])
        return _skins_cache[current["id"]]
    
    def get_skin_face(self) -> QImage:
        skin = self.get_current_skin()
        return skin.copy(8, 8, 8, 8)
    
    @property
    def should_refresh(self):
        if not self.token:
            return False
        elif not self.last_updated:
            return True
        elif (self.last_updated <
              (datetime.now() - timedelta(minutes=5)).timestamp()):
            return True
        return False
    
    @property
    def token(self):
        return self._token.access_token if self._token else None
    
    @token.setter
    def token(self, token:MinecraftToken):
        self._token = token
    
    def refresh_profile_info(self):
        if not self._token:
            raise RuntimeError("No Minecraft token present")
        headers = {
            "Authorization": "Bearer %s" % self.token
        }

        max_retries = 3
        response = None
        while max_retries > 0:
            max_retries -= 1
            try:
                response = requests.get(MOJ_PROF_URL, headers=headers)
                response.raise_for_status()
                break
            except (requests.exceptions.ConnectTimeout,
                    requests.exceptions.ConnectionError) as exc:
                log.warning("Failed to connect to %s: %s"
                            % (MOJ_PROF_URL, exc.__qualname__))
                log.debug("Waiting 5 seconds before next attempt")
                time.sleep(5)
                continue
            except requests.HTTPError as exc:
                log.error("Failed to fetch profile info: HTTP %s"
                          % exc.response.status_code)
                raise exc
            except Exception as exc:
                log.error("Unknown error occured fetching profile info:",
                          exc_info=True)
                raise exc
        if max_retries < 1:
            constants.offline_mode = True

        if response is None:
            raise ValueError("Response shouldn't be none!")
        prof_info_json:dict = response.json()

        # dummy data in case of demo account
        self.uuid = prof_info_json.get("id", "UNKNOWN")
        self.name = prof_info_json.get("name", "Steve")
        self.skins = prof_info_json.get("skins", [])
        self.capes = prof_info_json.get("capes", [])

        self.last_updated = datetime.now().timestamp()

        return self
    
    def serialize(self):
        """
        Convert this into a dict
        """
        return {k:v for k, v in {
            "id": self.uuid,
            "name": self.name,
            "skins": self.skins,
            "capes": self.capes,
            "last_updated": self.last_updated,
            **self._other_info
        }.items() if v}