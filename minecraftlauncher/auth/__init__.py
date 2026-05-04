from .launcher_account import LauncherAccount
from .microsoft_account import MicrosoftAccount
from .minecraft_profile import MinecraftProfile, TextureState, SkinModel
from .minecraft_token import MinecraftToken
from .xbox_token import XboxToken
from .xsts_token import XstsToken
from .auth_error import AuthError, AuthStep


def auth_flow(msa: MicrosoftAccount):
    xbox_account = XboxToken.auth(msa)
    if not xbox_account:
        return xbox_account
    xbox_profile = XstsToken.auth(xbox_account, "http://xboxlive.com")
    if not xbox_profile:
        return xbox_profile
    gamertag = xbox_profile.gamertag
    # NOTE: XUID can also be gathered from MinecraftToken.xuid
    xuid = xbox_profile.xuid
    uhs = xbox_profile.user_hash
    acc = LauncherAccount(msa, gamertag, xuid, uhs, xbox_token=xbox_account)
    success = acc.refresh()
    if not success:
        return success
    return acc
