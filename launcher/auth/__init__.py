from .launcher_account import LauncherAccount
from .microsoft_account import MicrosoftAccount
from .minecraft_profile import MinecraftProfile, TextureState, SkinModel
from .minecraft_token import MinecraftToken
from .xbox_token import XboxToken
from .xsts_token import XstsToken


def auth_flow(msa: MicrosoftAccount):
    """
    Complete auth chain from a `MicrosoftAccount` instance.

    Should only be used with new accounts.
    """
    xbox_account = XboxToken.auth(msa)
    xbox_profile = XstsToken.auth(xbox_account, "http://xboxlive.com")
    gamertag = xbox_profile.gamertag
    # NOTE: XUID can also be gathered from MinecraftToken.xuid
    xuid = xbox_profile.xuid
    uhs = xbox_profile.user_hash
    acc = LauncherAccount(msa, gamertag, xuid, uhs, xbox_token=xbox_account)
    acc.refresh()
    return acc
