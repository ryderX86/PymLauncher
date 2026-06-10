import logging

from minecraftlauncher.auth.microsoft_account import MicrosoftAccount
from minecraftlauncher.auth.xbox_token import XboxToken
from minecraftlauncher.auth.xsts_token import XstsToken
from minecraftlauncher.auth.minecraft_token import MinecraftToken
from minecraftlauncher.auth.minecraft_profile import MinecraftProfile

log = logging.getLogger(__name__)


class LauncherAccount:
    __slots__ = ("msa", "xbox", "token", "profile", "gamertag", "xuid", "uhs")
    msa: MicrosoftAccount
    xbox: XboxToken | None
    token: MinecraftToken | None
    profile: MinecraftProfile | None

    gamertag: str
    """
    Xbox Live gamertag, for UI account identification
    """
    xuid: str
    """
    Xbox User ID, for identifying accounts
    """
    uhs: str
    """
    Xbox User Hash, used by XBL/XSTS APIs
    """

    def __init__(
        self,
        msa_token: MicrosoftAccount,
        gamertag: str,
        xuid: str,
        uhs: str,
        *,
        xbox_token: XboxToken | None = None,
        mc_token: MinecraftToken | None = None,
        profile: MinecraftProfile | None = None
    ):
        self.msa = msa_token
        self.gamertag = gamertag
        self.token = mc_token
        self.profile = profile
        self.xuid = xuid
        self.uhs = uhs

        # defaults
        self.xbox = xbox_token

    @property
    def has_profile(self):
        """
        Whether or not the account has a profile associated
        with it or not. (Default: `False`)

        If the account doesn't have a profile but does
        own the game, notify the user to go to minecraft.net
        and sign in to activate their profile.

        This can't be relied on if you haven't first run
        `get_profile_info()` since initializing the class.
        """
        return bool(self.profile)

    @property
    def demo_mode(self):
        """
        Whether or not the game should be in demo mode.
        (Default: `True`)

        Once a game profile has been established, this
        should become `False` automatically.
        """
        if self.token:
            return not self.token.owns_game
        return True

    def refresh(self):
        profile_update = self.profile_needs_update()
        if (
            self.token
            and self.token.is_active
            and self.msa.is_active
            and not profile_update
        ):
            return True
        if not self.msa_valid and not self.token_valid:
            log.info("Refreshing tokens for '%s'", self.gamertag)
            success = self.msa.refresh()
            if not success:
                return success
        if not self.token_valid:
            if not self.xbox:
                xbox = XboxToken.auth(self.msa)
                if not xbox:
                    return xbox
                self.xbox = xbox
            xsts = XstsToken.auth(self.xbox)
            if not xsts:
                return xsts
            xbl_meta = XstsToken.auth(self.xbox, "http://xboxlive.com")
            if not xbl_meta:
                return xbl_meta
            self.gamertag = xbl_meta.gamertag
            mc = MinecraftToken.auth(xsts)
            if not mc:
                return mc
            self.token = mc
        if profile_update:
            self.get_profile_info()
        return True

    minecraft_auth = refresh

    def profile_needs_update(self):
        if not self.profile:
            if self.token and self.token.owns_game:
                return True
            return False
        return self.profile.should_refresh

    def skin_path(self):
        if self.profile:
            return self.profile.current_skin_path()
        return MinecraftProfile.steve_skin_path()

    def skin_bytes(self):
        if self.profile:
            return self.profile.current_skin_bytes()
        return MinecraftProfile.steve_skin_bytes()

    def skin_icon(self):
        if self.profile:
            return self.profile.current_skin_icon()
        return MinecraftProfile.steve_skin_icon()

    def cape_path(self):
        if self.profile:
            return self.profile.current_cape_path()
        return None

    @property
    def token_valid(self):
        """Returns `True` if the token exists and is valid, else `False`"""
        if not self.token:
            return False
        return self.token.is_active

    @property
    def msa_valid(self):
        return self.msa.is_active

    @property
    def player_type(self):
        return "msa"

    @property
    def username(self):
        """
        Retrieves the username safely, always returns str.

        If the profile isn't loaded or there's no username, it will return
        `""`.
        """
        if self.profile:
            return self.profile.name
        else:
            return ""

    @property
    def uuid(self):
        """
        Retrieves the UUID safely, always returns str.

        If the profile isn't loaded, or there's no UUID (somehow), it will
        return `"<uuid>"`.
        """
        if self.profile and self.profile.uuid:
            return self.profile.uuid
        return "<uuid>"

    def serialize(self):
        """Returns a JSON-serializable dict version of the current instance."""
        return {
            k: v
            for k, v in {
                "msa_token": self.msa.serialize(),
                "mc_token": self.token.serialize() if self.token else None,
                "game_profile": (
                    self.profile.serialize() if self.profile else None
                ),
                "gamertag": self.gamertag,
                "xuid": self.xuid,
                "uhs": self.uhs,
            }.items()
            if v
        }

    @classmethod
    def from_json(cls, json_: dict):
        """
        Initializes this class and its' held classes from the provided dict.
        """
        raw_msa_token = json_["msa_token"]
        xbl_name = json_["gamertag"]
        xuid = json_["xuid"]
        uhs = json_["uhs"]
        raw_mc_token = json_.get("mc_token")
        raw_profile = json_.get("game_profile")

        msa_token = MicrosoftAccount(raw_msa_token)
        if raw_mc_token:
            mc_token = MinecraftToken(raw_mc_token)
        else:
            mc_token = None

        if raw_profile:
            profile = MinecraftProfile(raw_profile, mc_token)
        else:
            profile = None

        return cls(
            msa_token,
            xbl_name,
            xuid,
            uhs,
            mc_token=mc_token,
            profile=profile,
        )

    @property
    def user_hash(self):
        return self.uhs

    def get_profile_info(self):
        if (not self.token) or (not self.token.is_active):
            raise RuntimeError("Minecraft token is empty, authenticate first!")
        prof_info = MinecraftProfile.from_token(self.token)
        self.profile = prof_info
        return self.profile

    def __eq__(self, other):
        if isinstance(other, str):
            return other == self.xuid
        return super().__eq__(other)
