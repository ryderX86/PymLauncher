from datetime import datetime
import json
import logging

import requests
import requests.exceptions

from minecraftlauncher.auth.microsoft_account import MicrosoftAccount
from minecraftlauncher.constants import (
    XBOX_AUTH_URL,
)
from minecraftlauncher import SESSION, set_offline_mode
from .auth_error import AuthError, AuthStep

log = logging.getLogger(__name__)


class XboxToken:
    __slots__ = ("json", "token", "expires_at", "acquired_at")

    json: dict
    """
    Full JSON Xbox Live token
    """
    token: str
    """
    Xbox Live token (not the raw JSON, use `.as_json()` or `.json` for that)
    """
    expires_at: float
    """
    Unix timestamp at which this token is no longer valid
    """
    acquired_at: float
    """
    Unix timestamp at which this token was acquired by the client
    """

    def __init__(self, xbl_token: dict):
        if isinstance(xbl_token, str):
            try:
                xbl_token = json.loads(xbl_token)
            except json.JSONDecodeError as err:
                raise TypeError("'xbl_jwt' must be valid JSON if str") from err

        self.json = xbl_token
        self.token = self.json["Token"]

        self.expires_at = datetime.fromisoformat(
            xbl_token["NotAfter"]
        ).timestamp()
        """
        Unix timestamp version of `NotAfter` in the XBL token
        """
        self.acquired_at = datetime.fromisoformat(
            xbl_token["IssueInstant"]
        ).timestamp()
        """
        Unix timestamp version of `IssueInstant` in the XBL token
        """

    @classmethod
    def auth(cls, msa: MicrosoftAccount):
        if msa.expires_in < 20:
            log.warning("MSA account wasn't refreshed before trying Xbox auth")
            msa.refresh()

        payload = {
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"d={msa.access_token}",
            },
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-xbl-contract-version": "1",
        }

        try:
            response = SESSION.post(
                XBOX_AUTH_URL, json=payload, headers=headers
            )
            response.raise_for_status()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ConnectTimeout,
        ) as err:
            log.warning(
                "%s occured while attempting MSA token refresh",
                err.__qualname__,
            )
            set_offline_mode(True)
            raise RuntimeError(
                f"Failed to connect to {XBOX_AUTH_URL!r}"
            ) from err
        except requests.HTTPError as err:
            log.error(
                "Failed to refresh MSA token; response code %d",
                err.response.status_code,
            )
            return AuthError(
                AuthStep.XBL, err.response.status_code, err.response.text
            )
        else:
            return cls(response.json())

    @property
    def expires_in(self):
        return self.expires_at - datetime.now().timestamp()

    @property
    def user_hash(self):
        return self.json["DisplayClaims"]["xui"][0]["uhs"]

    @property
    def gamertag(self):
        return self.json["DisplayClaims"]["xui"][0].get("gtg")

    def as_json(self):
        return self.json
