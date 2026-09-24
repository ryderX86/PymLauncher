import logging
import random
import time

from launcher.auth.xsts_token import XstsToken
from launcher.constants import (
    LAUNCH_ENTITLEMENTS_URL,
    MOJ_AUTH_URL,
)
from launcher.datatypes import decode_jwt
from launcher.exceptions.network import (
    HTTPStatusCodeError,
    WrappedUL3Exception,
)
from launcher.networking import make_request
from launcher.offline import offline_man

from .exceptions import (
    BaseAuthenticationException,
    NoConnectionError,
    UnauthorizedError,
)

log = logging.getLogger(__name__)

GAME_OWNERSHIP_ITEMS = {
    "product_minecraft",
    "game_minecraft",
    "product_game_pass_pc",
    "product_game_pass_ultimate",
}


def _unidentified_xuid():
    i = random.randint(0, 99999999)
    s = str(i)[:8]
    while len(s) < 8:
        s = "".join([s, "0"])
    return f"00000000{s}"


class MinecraftToken:
    __slots__ = (
        "username",
        "roles",
        "access_token",
        "token_type",
        "_expires_in",
        "acquired_at",
        "expires_at",
        "owned_items",
        "jwt",
        "xuid",
        "uuid",
    )
    username: str
    """
    UUID, not the public-facing UUID however
    """
    roles: list
    access_token: str
    """
    JWT, Minecraft access token
    """
    token_type: str
    _expires_in: int

    # NOT part of the original response:
    acquired_at: float | int
    expires_at: float | int
    owned_items: set[str] | None
    jwt: dict
    xuid: str
    uuid: str
    """Public facing profile UUID"""

    def __init__(self, mc_token: dict):
        self.username = mc_token["username"]
        self.roles = mc_token["roles"]
        self.access_token = mc_token["access_token"]
        self.token_type = mc_token["token_type"]
        self._expires_in = mc_token["expires_in"]

        # cached values:
        if "jwt" in mc_token:
            self.jwt = mc_token["jwt"]
        else:
            self.jwt = decode_jwt(self.access_token).payload
        self.xuid = self.jwt.get(
            "xuid", self.jwt.get("xid", _unidentified_xuid())
        )
        self.uuid = self.jwt.get("profiles", {}).get("mc", "0")
        self.owned_items = (
            set(mc_token.get("owned_items", []))
            if mc_token.get("owned_items")
            else None
        )
        self.acquired_at = mc_token.get(
            "acquired_at", self.jwt.get("iat", time.time())
        )
        self.expires_at = self.jwt.get(
            "exp", self.acquired_at + self._expires_in
        )

    @property
    def expires_in(self):
        return self.expires_at - time.time()

    @property
    def is_active(self):
        return self.expires_in > 10

    @property
    def _req_header(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    @classmethod
    def auth(cls, xsts_token: XstsToken):
        payload = {
            "identityToken": f"XBL3.0 x={xsts_token.user_hash};{xsts_token.token}",
            "platform": "PC_LAUNCHER",
        }

        try:
            resp = make_request("post", MOJ_AUTH_URL, body=payload)
        except HTTPStatusCodeError as err:
            log.error(
                "Failed to get Minecraft token from %r; HTTP %d - %s\n"
                "Full response: %r",
                MOJ_AUTH_URL,
                err.code,
                err.desc,
                err.body,
            )
            raise UnauthorizedError(
                err.response, f"HTTP {err.code} {err.desc}"
            ) from err
        except WrappedUL3Exception as err:
            log.error(
                "Failed to get Minecraft token from %r:",
                MOJ_AUTH_URL,
                exc_info=err,
            )
            if offline_man.check_requests_error(err):
                raise NoConnectionError(MOJ_AUTH_URL, err) from err
            raise BaseAuthenticationException(
                err.resp, "An unknown issue occured while authenticating."
            ) from err

        return cls(resp.json())

    from_token = auth
    """Alias for `cls.auth()`"""

    @property
    def owns_game(self) -> bool:
        if self.owned_items is None:
            return False
        else:
            return not self.owned_items.isdisjoint(GAME_OWNERSHIP_ITEMS)

    def serialize(self):
        """Returns JSON-serializable dict of this token."""
        # sort set
        if self.owned_items:
            owned_items = [*self.owned_items]
            owned_items.sort()
        else:
            owned_items = None

        return {
            "username": self.username,
            "roles": self.roles,
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self._expires_in,
            "acquired_at": self.acquired_at,
            "jwt": self.jwt,
            "owned_items": owned_items,
        }

    def _update_entitlements(self, use_web_request: bool = False):
        if not self.owned_items and use_web_request:
            self.get_launcher_entitlements()
            assert self.owned_items is not None
        return

    def get_launcher_entitlements(self):
        try:
            resp = make_request(
                "get", LAUNCH_ENTITLEMENTS_URL, headers=self._req_header
            )
        except HTTPStatusCodeError as err:
            raise UnauthorizedError(
                err.response,
                "Failed getting account entitlements (owned items): "
                f"HTTP {err.code} {err.desc}",
            ) from err

        game_list = resp.json()

        items: list[dict[str, str]] = game_list.get("items", [])
        self.owned_items = {i.get("name", "unidentified") for i in items}

        self._update_entitlements()
        assert self.owned_items is not None

        return self.owned_items
