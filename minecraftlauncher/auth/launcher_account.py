from dataclasses import dataclass
from datetime import datetime
import json
import time
import logging

from PySide6.QtGui import QImage
import requests
import requests.exceptions

from minecraftlauncher.auth.microsoft_account import MicrosoftAccount
from minecraftlauncher.auth.xbox_token import XboxToken
from minecraftlauncher.auth.xsts_token import XstsToken
from minecraftlauncher.auth.minecraft_token import MinecraftToken
from minecraftlauncher.auth.minecraft_profile import MinecraftProfile
from minecraftlauncher import constants

log = logging.getLogger(__name__)

class LauncherAccount:
    msa: MicrosoftAccount
    xbox: XboxToken|None
    token: MinecraftToken|None
    profile: MinecraftProfile|None

    demo_mode: bool # default: True
    """
    Whether or not the game should be in demo mode.
    (Default: `True`)

    Once a game profile has been established, set
    this to `False`.
    """
    has_profile: bool # default: False
    """
    Whether or not the account has a profile associated
    with it or not. (Default: `False`)

    If the account doesn't have a profile but does
    own the game, notify the user to go to minecraft.net
    and sign in to activate their profile.

    This can't be relied on if you haven't first run
    `get_profile_info()` since initializing the class.
    """
    gamertag: str
    """
    Xbox Live gamertag, for identifying accounts
    """
    def __init__(self, msa_token:MicrosoftAccount, gamertag:str, xuid:str,
                 uhs:str, *, xbox_token:XboxToken|None=None,
                 mc_token:MinecraftToken|None=None,
                 profile:MinecraftProfile|None=None,
                 use_demo_mode:bool=True):
        self.msa = msa_token
        self.gamertag = gamertag
        self.token = mc_token
        self.profile = profile
        self.xuid = xuid
        self.uhs = uhs
        if self.token and self.token.is_active:
            self.demo_mode = self.token.owns_game
        else:
            self.demo_mode = use_demo_mode

        # defaults
        self.xbox = xbox_token
        self.has_profile = bool(self.profile)

        if self.demo_mode and self.token:
            if not self.token.is_active:
                return
                if self.msa.expires_in < 5:
                    success = self.msa.refresh()
                    if not success:
                        return
                xbox = XboxToken.auth(self.msa)
                if not xbox:
                    return
                self.xbox = xbox
                xsts = XstsToken.auth(self.xbox)
                if not xsts:
                    return
                new_token = MinecraftToken.auth(xsts)
                if not new_token:
                    return
                self.token = new_token
            self.demo_mode = self.token.owns_game

    def refresh(self):
        if self.token and self.token.is_active and self.msa.is_active:
            log.debug("Skipping refresh since we don't need it")
            return True
        log.info("Refreshing tokens for '%s'" % self.gamertag)
        if not self.msa_valid:
            success = self.msa.refresh()
            if not success:
                return success
        if not self.xbox:
            xbox = XboxToken.auth(self.msa)
            if not xbox:
                return xbox
            self.xbox = xbox
        if not self.token_valid:
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
            return True
        else:
            return True
        
    minecraft_auth = refresh

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
        return self.token.expires_in > 10
    
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
        return {k:v for k, v in {
            "msa_token": self.msa.serialize(),
            "mc_token": self.token.serialize() if self.token else None,
            "demo_user": self.demo_mode,
            "game_profile": self.profile.serialize() if self.profile else None,
            "gamertag": self.gamertag,
            "xuid": self.xuid,
            "uhs": self.uhs
        }.items() if v}
    
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
        
        if mc_token and mc_token.owns_game:
            demo_mode = False
        else:
            demo_mode = True

        if raw_profile:
            profile = MinecraftProfile(raw_profile, mc_token)
        else:
            profile = None
        
        return cls(
            msa_token, xbl_name, xuid, uhs, mc_token=mc_token,
            use_demo_mode=demo_mode, profile=profile)
    
    @property
    def user_hash(self):
        return self.uhs
    
    def get_profile_info(self):
        if (not self.token) or (not self.token.is_active):
            raise Exception("Minecraft token is empty, authenticate first!")
        prof_info = MinecraftProfile.from_token(self.token)
        self.profile = prof_info
        return self.profile