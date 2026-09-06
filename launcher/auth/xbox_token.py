from datetime import datetime
import json
import logging
import time

import requests
import requests.exceptions

from launcher import SESSION
from launcher.auth.microsoft_account import MicrosoftAccount
from launcher.constants import (
    XBOX_AUTH_URL,
)
from launcher.offline import offline_man

from .exceptions import (
    BaseAuthenticationException,
    NoConnectionError,
    UnauthorizedError,
)

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
                type(err).__name__,
            )
            offline_man.check_requests_error(err)
            raise NoConnectionError(
                XBOX_AUTH_URL, err, original_request=err.request
            ) from err
        except requests.HTTPError as err:
            if err.response:
                log.error(
                    "Failed to refresh MSA token; response code %d",
                    err.response.status_code,
                )
                match err.response.status_code:
                    case 401:
                        raise UnauthorizedError(err.response) from err
                    case _:
                        raise BaseAuthenticationException(
                            err.response
                        ) from err
            else:
                log.error(
                    "Failed to refresh Xbox token; no response", exc_info=err
                )
                raise
        try:
            resp_json = response.json()
        except json.JSONDecodeError as err:
            raise BaseAuthenticationException(
                response, "Xbox Live returned invalid JSON"
            ) from err
        if "Token" not in resp_json:
            raise BaseAuthenticationException(response)
        return cls(resp_json)

    @property
    def expires_in(self):
        return self.expires_at - time.time()

    @property
    def user_hash(self):
        return self.json["DisplayClaims"]["xui"][0]["uhs"]

    @property
    def gamertag(self):
        return self.json["DisplayClaims"]["xui"][0].get("gtg")

    def as_json(self):
        return self.json
