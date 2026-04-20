from dataclasses import dataclass
from datetime import datetime
import json
import logging
import time

import requests
import requests.exceptions

from minecraftlauncher.datatypes import JWT, decode_jwt
from minecraftlauncher.auth.xsts_token import XstsToken
from minecraftlauncher.constants import (
    AZURE_CLIENT_ID, AZURE_SCOPE, MOJ_AUTH_URL, MSA_REFRESH_URL,
    LAUNCH_ENTITLEMENTS_URL, MOJ_AUTH_URL_ALT)
from minecraftlauncher import constants, session
from .exceptions import xsts_auth_error
from .auth_error import AuthError, AuthStep

log = logging.getLogger(__name__)

class MinecraftToken:
    username:str
    """
    UUID, not the public-facing UUID however
    """
    roles:list
    access_token:str
    """
    JWT, Minecraft access token
    """
    token_type:str
    _expires_in:int

    # NOT part of the original response:
    acquired_at:float
    expires_at:float
    owned_items:list
    _owns_game:bool
    def __init__(self, mc_token:dict):
        self.username = mc_token["username"]
        self.roles = mc_token["roles"]
        self.access_token = mc_token["access_token"]
        self.token_type = mc_token["token_type"]
        self._expires_in = mc_token["expires_in"]

        # cached value only
        self.owned_items = mc_token.get("owned_items", [])
        self.acquired_at = mc_token.get(
            "acquired_at",
            datetime.now().timestamp()
        )
        self.expires_at = mc_token.get(
            "expires_at",
            self.acquired_at + self._expires_in
        )
        self._owns_game = False
        self._update_entitlements()

    @property
    def expires_in(self):
        return (self.expires_at - datetime.now().timestamp())
    
    @property
    def is_active(self):
        return self.expires_in > 10
    
    @classmethod
    def auth_alternate(cls, xsts_token:XstsToken):
        payload = {
            "xtoken": f"XBL3.0 x={xsts_token.user_hash};{xsts_token.token}",
            "platform": "PC_LAUNCHER"
        }

        response = None
        attempts = 0
        while attempts < 3:
            attempts += 1
            try:
                response = session.post(MOJ_AUTH_URL, json=payload)
                response.raise_for_status()
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ConnectTimeout) as exc:
                log.warning(
                    "%s occured while attempting MSA token refresh"
                    % exc.__qualname__)
                if attempts >= 2:
                    constants.offline_mode = True
                    break
                else:
                    log.info("Waiting 5 seconds before next attempt...")
                    time.sleep(5)
                    continue
            except requests.HTTPError as err:
                log.error(
                    "Failed to get Minecraft Token from %s; response code %d\n"
                    "Full response: %s"
                    % (MOJ_AUTH_URL_ALT, err.response.status_code,
                       err.response.text))
                return AuthError(
                    AuthStep.MOJ, err.response.status_code, err.response.text)
            
        if response is None:
            raise ValueError("Failed to get response")
        
        return cls(response.json())

    @classmethod
    def auth(cls, xsts_token:XstsToken):
        payload = {
            "identityToken": "XBL3.0 x=%(uhs)s;%(xsts)s" % {
                "uhs": xsts_token.user_hash,
                "xsts": xsts_token.token
            }
        }

        connection_attempts = 0
        response = None
        while connection_attempts < 3:
            connection_attempts += 1
            try:
                response = session.post(MOJ_AUTH_URL, json=payload)
                response.raise_for_status()
                break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ConnectTimeout) as exc:
                log.warning("%s occured while attempting MSA token refresh"
                            % exc.__qualname__)
                if connection_attempts >= 2:
                    constants.offline_mode = True
                    break
                else:
                    pass
                log.info("Waiting 5 seconds before next attempt...")
                time.sleep(5)
            except requests.HTTPError as exc:
                if exc.response.status_code in (400, 401, 402, 403):
                    log.warning(
                        "Malformed request err; defaulting to alt auth url")
                    log.debug("returning `cls.auth_alternate(xsts_token)`")
                    return cls.auth_alternate(xsts_token)
                log.error("Failed to refresh MSA token; response code %d\n"
                          "Response text: %s"
                          % (exc.response.status_code, exc.response.text))
                return AuthError(
                    AuthStep.MOJ, exc.response.status_code, exc.response.text)
            # TODO: remove this when verified that the loop won't
            # infinitely continue
            if connection_attempts < 4:
                print("WARNING: Why are we still going?")
                print("(.datatypes.MicrosoftAccount....refresh())")

        if response is None:
            raise ValueError("response should not be false!")
        
        return cls(response.json())
    
    from_token = auth
    """Alias for `cls.auth()`"""
    
    @property
    def owns_game(self):
        if self._owns_game is None:
            self._update_entitlements(constants.offline_mode == False)
        return self._owns_game
    
    def serialize(self):
        """Returns JSON-serializable dict of this token."""
        return {
            "username": self.username,
            "roles": self.roles,
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self._expires_in,
            "acquired_at": self.acquired_at,
            "owned_items": self.owned_items
        }
    
    def _update_entitlements(self, use_web_request:bool=False):
        if not self.owned_items and use_web_request:
            self.get_launcher_entitlements()
        elif not self.owned_items:
            return
        self._owns_game = ("product_minecraft" in self.owned_items
                           or "game_minecraft" in self.owned_items
                           or "product_game_pass_pc" in self.owned_items
                           or "product_game_pass_ultimate" in self.owned_items)
    
    def get_launcher_entitlements(self) -> list:
        headers = {
            "Authorization": "Bearer %s" % self.access_token
        }

        response = session.get(LAUNCH_ENTITLEMENTS_URL, headers=headers)
        response.raise_for_status()

        game_list = response.json()

        self.owned_items = game_list.get("items", [])

        self._update_entitlements()

        return self.owned_items