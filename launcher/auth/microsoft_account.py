import json
import logging
import time

from launcher.constants import (
    AZURE_CLIENT_ID,
    AZURE_SCOPE,
    MSA_REFRESH_URL,
)
from launcher.exceptions.network import (
    HTTPStatusCodeError,
    WrappedUL3Exception,
)
from launcher.networking import make_request
from launcher.offline import offline_man

from .exceptions import (
    MSABaseAuthenticationException,
    NoConnectionError,
    UnauthorizedError,
)

log = logging.getLogger(__name__)

KNOWN_MSA_DICT_VALS = {
    "token_type",
    "scope",
    "expires_in",
    "access_token",
    "refresh_token",
    "id_token",
    "acquired_at",
    "user_id",
    "ext_expires_in",
}


class MicrosoftAccount:
    __slots__ = (
        "token_type",
        "scope",
        "_expires_in",
        "access_token",
        "refresh_token",
        "acquired_at",
        "user_id",
        "_ext_expires_in",
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
    _ext_expires_in: int
    """
    Usually the same as `expires_in`, it's meant for server outages. It *can*
    be longer than `expires_in`, but usually isn't from what I can tell.
    """
    access_token: str
    refresh_token: str | None
    user_id: str | None
    """Can appear inside the token, unknown why or purpose."""

    _other_token_info: dict
    """
    Backup of all other data included in the API response, mostly for debugging
    """

    # The following is NOT included in the MS API response:
    acquired_at: float

    def __init__(self, msa_info: dict, acquired_at: int | float | None = None):
        if acquired_at is not None:
            self.acquired_at = float(acquired_at)
        else:
            self.acquired_at = msa_info.get("acquired_at", time.time())

        self.token_type = msa_info["token_type"]
        self.scope = msa_info["scope"]
        self._expires_in = msa_info["expires_in"]
        self.access_token = msa_info["access_token"]
        self.refresh_token = msa_info.get("refresh_token", None)
        self._ext_expires_in = msa_info.get("ext_expires_in", self._expires_in)
        self.user_id = msa_info.get("user_id", None)
        self._other_token_info = {
            k: v for k, v in msa_info.items() if k not in KNOWN_MSA_DICT_VALS
        }
        for key, value in self._other_token_info.items():
            log.warning("Unknown MSA token key: {%r: %r}", key, value)
        return

    @property
    def expires_in(self) -> float:
        return (self.acquired_at + self._expires_in) - time.time()

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
                "ext_expires_in": self._ext_expires_in,
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

    @property
    def can_refresh(self):
        return bool(self.refresh_token)

    def refresh(self):
        if not self.refresh_token:
            raise UnauthorizedError(msg="No refresh token present")
        if self.scope:
            scope = self.scope
            if scope != AZURE_SCOPE:
                log.warning(
                    "Current account's MSA scope differs from default; "
                    "Default: %r; current: %r",
                    AZURE_SCOPE,
                    scope,
                )
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

        try:
            response = make_request("post", MSA_REFRESH_URL, form=form_data)
        except WrappedUL3Exception as err:
            log.error(
                "%s occured while attempting MSA token refresh",
                type(err).__qualname__,
            )
            if offline_man.check_requests_error(err):
                raise NoConnectionError(MSA_REFRESH_URL, err) from err
            raise MSABaseAuthenticationException() from err
        except HTTPStatusCodeError as err:
            if err.response is not None:
                log.error(
                    "Failed to refresh MSA token; response code %d",
                    err.code,
                )
                if err.code in range(400, 500):
                    exc_type = (
                        MSABaseAuthenticationException.get_exception_type(
                            err.response
                        )
                    )
                    raise exc_type(err.response) from err
            else:
                if offline_man.check_requests_error(err):
                    raise NoConnectionError(MSA_REFRESH_URL, err) from err
                log.error("Failed to refresh MSA token; no response")
            raise MSABaseAuthenticationException(
                None, "Account refresh"
            ) from err

        if len(response.data) < 5:
            exc_type = MSABaseAuthenticationException.get_exception_type(
                response
            )
            raise exc_type(response)

        new_token = response.json()
        self.acquired_at = time.time()

        self.access_token = new_token.get("access_token")
        if not self.access_token:
            errtype = MSABaseAuthenticationException.get_exception_type(
                response
            )
            raise errtype(response, "no access token in response")
        self.refresh_token = new_token.get("refresh_token", self.refresh_token)
        self.expires_in = new_token.get("expires_in", self._expires_in)

        return True
