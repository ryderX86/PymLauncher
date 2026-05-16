from datetime import datetime
import json
import logging

import requests
import requests.exceptions

from minecraftlauncher.constants import (
    AZURE_CLIENT_ID,
    AZURE_SCOPE,
    MSA_REFRESH_URL,
)
from minecraftlauncher import SESSION, set_offline_mode
from .auth_error import AuthError, AuthStep

log = logging.getLogger(__name__)

KNOWN_MSA_DICT_VALS = [
    "token_type",
    "scope",
    "expires_in",
    "access_token",
    "refresh_token",
    "id_token",
    "acquired_at",
]


class MicrosoftAccount:
    __slots__ = (
        "token_type",
        "scope",
        "_expires_in",
        "access_token",
        "refresh_token",
        "acquired_at",
        "_other_token_info",
    )
    token_type: str  # Always "Bearer"
    scope: str
    """
    See `minecraftlauncher.constants.AZURE_SCOPE`
    """
    _expires_in: int
    """
    The *unmodified, original* time (in seconds as int)
    until the token expires, as given from the MS API.

    Never change this manually outside of `refresh()`,
    it *never* needs to be. Use `acquired_at` (float)
    instead.
    """
    access_token: str
    refresh_token: str

    # The following is NOT included in the MS API response:
    acquired_at: float

    def __init__(self, msa_info: dict):
        self.acquired_at = msa_info.get(
            "acquired_at", datetime.now().timestamp()
        )

        self.token_type = msa_info["token_type"]
        self.scope = msa_info["scope"]
        self._expires_in = msa_info["expires_in"]
        self.access_token = msa_info["access_token"]
        self.refresh_token = msa_info["refresh_token"]
        self._other_token_info = {
            k: v for k, v in msa_info.items() if k not in KNOWN_MSA_DICT_VALS
        }
        return

    @property
    def expires_in(self) -> float:
        return (
            self.acquired_at + self._expires_in
        ) - datetime.now().timestamp()

    @expires_in.setter
    def expires_in(self, new_val: int):
        if new_val < 0:
            raise ValueError(
                "expires_in cannot be below 0. "
                "Did you mean to access _expires_in?"
            )
        self._expires_in = new_val

    def _original_token_dict(self):
        return {
            "token_type": self.token_type,
            "scope": self.scope,
            "expires_in": self._expires_in,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            **self._other_token_info,
        }

    def serialize(
        self, *, uuid: str | None = None, username: str | None = None
    ):
        return {
            k: v
            for k, v in {
                "token_type": self.token_type,
                "scope": self.scope,
                "expires_in": self._expires_in,
                "acquired_at": self.acquired_at,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "uuid": uuid,
                "username": username,
                **self._other_token_info,
            }.items()
            if v
        }

    @property
    def is_active(self):
        return self.expires_in > 20.0

    def original_token(self):
        """
        original_token

        :param self: Returns the original JSON for this token
        """
        return json.dumps(self._original_token_dict())

    def refresh(self):
        if self.scope:
            scope = self.scope
            if scope != AZURE_SCOPE:
                log.debug("MSA scope differs from default: '%s'", scope)
        else:
            log.warning(
                "No scope present in MSA! Trying default but user may have to "
                "re-log"
            )
            scope = AZURE_SCOPE
        form_data = {
            "client_id": AZURE_CLIENT_ID,
            "scope": scope,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        # None in place of filename -- `requests.post(files=...)`
        # is currently the way to submit form data with requests.

        response = None
        try:
            response = SESSION.post(MSA_REFRESH_URL, data=form_data)
            response.raise_for_status()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ConnectTimeout,
        ) as exc:
            log.warning(
                "%s occured while attempting MSA token refresh",
                exc.__qualname__,
            )
            set_offline_mode(True)
            return AuthError(AuthStep.MSA, -1, "Connection failed")
        except requests.HTTPError as exc:
            log.error(
                "Failed to refresh MSA token; response code %s",
                exc.response.status_code,
            )
            return AuthError(
                AuthStep.MSA, exc.response.status_code, exc.response.text
            )

        if response is None or len(response.text) < 5:
            return AuthError(
                AuthStep.MSA,
                "N/A",
                response.text if response is not None else "No response",
            )

        new_token = response.json()
        self.acquired_at = datetime.now().timestamp()

        self.access_token = new_token.get("access_token")
        if not self.access_token:
            return AuthError(
                AuthStep.MSA,
                new_token.get("error", "Error code not provided"),
                new_token.get("error_description", "Description not provided"),
            )
        self.refresh_token = new_token.get("refresh_token", self.refresh_token)
        self.expires_in = new_token.get("expires_in", self._expires_in)

        return True
