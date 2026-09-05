from datetime import datetime
import json
import logging
import time

import requests
import requests.exceptions

from pymlauncher import SESSION
from pymlauncher.auth.xbox_token import XboxToken
from pymlauncher.constants import (
    XSTS_AUTH_URL,
)
from pymlauncher.offline import offline_man

from .exceptions import NoConnectionError, XstsAuthError

log = logging.getLogger(__name__)


class XstsToken:
    mojang_uri = "rp://api.minecraftservices.com/"
    xbox_uri = "http://xboxlive.com"

    __slots__ = ("json", "token", "expires_at", "acquired_at")
    json: dict
    """
    Full JSON Xbox Live XSTS token
    """
    token: str
    """
    Xbox Live XSTS token (not the raw JSON, use `.as_json()` or `.json` for that)
    """
    expires_at: float
    """
    Unix timestamp at which this token is no longer valid
    """
    acquired_at: float
    """
    Unix timestamp at which this token was acquired by the client
    """

    def __init__(self, xsts_token: dict):
        if isinstance(xsts_token, str):
            try:
                xsts_token = json.loads(xsts_token)
            except json.JSONDecodeError as err:
                raise TypeError("'xbl_jwt' must be valid JSON if str") from err

        self.json = xsts_token
        self.token = self.json["Token"]

        self.expires_at = datetime.fromisoformat(
            xsts_token["NotAfter"]
        ).timestamp()
        """
        Unix timestamp version of `NotAfter` in the XSTS token
        """
        self.acquired_at = datetime.fromisoformat(
            xsts_token["IssueInstant"]
        ).timestamp()
        """
        Unix timestamp version of `IssueInstant` in the XSTS token
        """

    @classmethod
    def auth(
        cls,
        xbl_token: XboxToken,
        relying_party: str = "rp://api.minecraftservices.com/",
    ):
        if xbl_token.expires_in < 20:
            raise ValueError("Xbox Live token expired alredy!")

        payload = {
            "Properties": {
                "SandboxId": "RETAIL",
                "UserTokens": [xbl_token.token],
            },
            "RelyingParty": relying_party,
            "TokenType": "JWT",
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-xbl-contract-version": "1",
        }

        try:
            response = SESSION.post(
                XSTS_AUTH_URL, json=payload, headers=headers
            )
            response.raise_for_status()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ConnectTimeout,
        ) as err:
            log.warning(
                "%s occured while attempting MSA token refresh",
                type(err).__name__,
            )
            offline_man.check_requests_error(err)
            raise NoConnectionError(
                XSTS_AUTH_URL, err, original_request=err.request
            ) from err
        except requests.HTTPError as err:
            if err.response:
                log.error(
                    "Failed to refresh MSA token; response code %d\n"
                    "Response text: %s",
                    err.response.status_code,
                    err.response.text,
                )
                raise XstsAuthError(err.response.json()) from err
            log.error("Failed to refresh MSA token; no response", exc_info=err)
            raise err

        return cls(response.json())

    @property
    def expires_in(self):
        return self.expires_at - time.time()

    @property
    def user_hash(self):
        return self.json["DisplayClaims"]["xui"][0]["uhs"]

    @property
    def display_claims(self) -> dict[str, str | int]:
        return self.json["DisplayClaims"]["xui"][0]

    @property
    def gamertag(self) -> str:
        if "gtg" not in self.json["DisplayClaims"]["xui"][0]:
            raise AttributeError("Gamertag not present in this XSTS token")
        return self.json["DisplayClaims"]["xui"][0]["gtg"]

    @property
    def xuid(self) -> str:
        return self.json["DisplayClaims"]["xui"][0]["xid"]

    def as_json(self):
        return self.json
