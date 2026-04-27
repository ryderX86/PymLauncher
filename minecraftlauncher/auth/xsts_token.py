from datetime import datetime
import json
import logging
import time

import requests
import requests.exceptions

from minecraftlauncher.auth.xbox_token import XboxToken
from minecraftlauncher.constants import (
    XSTS_AUTH_URL,
)
from minecraftlauncher import constants, session
from .exceptions import XstsAuthError
from .auth_error import AuthError, AuthStep

log = logging.getLogger(__name__)


class XstsToken:
    json: dict
    """
    Full JSON Xbox Live XSTS token
    """
    token: str
    """
    Xbox Live XSTS token (not the raw JSON, use `.as_json()` or `.json` for that)
    """

    mojang_uri = "rp://api.minecraftservices.com/"
    xbox_uri = "http://xboxlive.com"

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

        connection_attempts = 0
        response = None
        while connection_attempts < 3:
            connection_attempts += 1
            try:
                response = session.post(
                    XSTS_AUTH_URL, json=payload, headers=headers
                )
                response.raise_for_status()
                break
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ConnectTimeout,
            ) as exc:
                log.warning(
                    "%s occured while attempting MSA token refresh",
                    exc.__qualname__,
                )
                if connection_attempts >= 2:
                    constants.offline_mode = True
                    break
                else:
                    pass
                log.info("Waiting 5 seconds before next attempt...")
                time.sleep(5)
            except requests.HTTPError as exc:
                if exc.errno == 401:
                    if response is None:
                        raise TypeError(
                            "Response was given but is still none?"
                        ) from exc
                    raise XstsAuthError(response.json()) from exc
                else:
                    log.error(
                        "Failed to refresh MSA token; response code %d\n"
                        "Response text: %s",
                        exc.response.status_code,
                        exc.response.text,
                    )
                    return AuthError(
                        (
                            AuthStep.XSTS
                            if relying_party == cls.mojang_uri
                            else AuthStep.GTG
                        ),
                        exc.response.status_code,
                        exc.response.text,
                    )
            # TODO: remove this when verified that the loop won't
            # infinitely continue
            if connection_attempts < 4:
                print("WARNING: Why are we still going?")
                print("(.datatypes.MicrosoftAccount....refresh())")

        if response is None:
            raise RuntimeError(
                "Request to XBL unsuccessful? (Response doesn't exist!)"
            )

        return cls(response.json())

    @property
    def expires_in(self):
        return self.expires_at - datetime.now().timestamp()

    @property
    def user_hash(self):
        return self.json["DisplayClaims"]["xui"][0]["uhs"]

    @property
    def display_claims(self) -> dict[str, str | int]:
        return self.json["DisplayClaims"]["xui"][0]

    @property
    def gamertag(self) -> str:
        return self.json["DisplayClaims"]["xui"][0]["gtg"]

    @property
    def xuid(self) -> str:
        return self.json["DisplayClaims"]["xui"][0]["xid"]

    def as_json(self):
        return self.json
