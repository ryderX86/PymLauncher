from datetime import datetime
from typing import Callable
from pathlib import Path
import base64
import json
import logging
import shutil

import requests

from minecraftlauncher.constants import (SKIN_CHANGE_URL, LAUNCHER_DATA_DIR,
                                         MINECRAFT_DIR)
from minecraftlauncher.auth.microsoft_account import MicrosoftAccount
from minecraftlauncher.auth.launcher_account import LauncherAccount
from minecraftlauncher.functions.text import indent
from minecraftlauncher import DEV

log = logging.getLogger(__name__)

ACCOUNTS_FILE = LAUNCHER_DATA_DIR / "accounts.bin"
SKINS_CACHE_DIR = LAUNCHER_DATA_DIR / "skin_cache"
SKIN_METADATA_PATH = SKINS_CACHE_DIR / "skins_meta.json"

save_accounts_mixin:Callable|None = None

accounts:list[LauncherAccount] = []
active_account:str|None = None

def save_accounts(accounts_:list|None=None, *,
                  active_email:str|None=None):
    """
    Save account data to disk.

    Entries should be a full `LauncherProfile` object
    """
    global accounts
    if accounts_:
        log.warning("Overriding accounts cache")
        accounts = accounts_

    LAUNCHER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    json_indent = 4 if DEV else 0
    payload = json.dumps({
        "active": active_email or active_account,
        "accounts": [acc.serialize() for acc in accounts],
        "last_saved": datetime.now().timestamp()
    }, indent=json_indent)

    if isinstance(save_accounts_mixin, Callable):
        # If we have OS-dependant methods for encrypting,
        # let's use them here, else just skip it.
        payload = save_accounts_mixin(payload)
    
    ACCOUNTS_FILE.write_text(payload, "utf-8")

    log.debug("Saved %s accounts to cache file." % len(accounts))
    return

def save_or_replace_account(lp:LauncherAccount,
                            accounts_:list[LauncherAccount]|None=None):
    """Add or replace account into cache and save to disk."""
    global accounts
    if accounts_:
        log.warning("Overriding accounts cache")
        accounts = accounts_
    
    index = 0
    found_account = False
    for acc in accounts:
        new_email = lp.msa.email
        email = acc.msa.email
        if new_email == email:
            index = accounts.index(acc)
            found_account = True
            break
    if found_account:
        log.debug("Account with E-mail '%s' replaced in cache"
                  % lp.msa.email)
        accounts[index] = lp
    else:
        log.debug("Adding account with E-mail '%s' to accounts cache."
                  % lp.msa.email)
        accounts.append(lp)
    save_accounts()

def load_accounts():
    global accounts
    global active_account

    if not ACCOUNTS_FILE.exists():
        return [], None
    
    if accounts and active_account:
        return accounts, active_account
    
    payload = ACCOUNTS_FILE.read_text(encoding="utf-8")
    try:
        accounts_file = json.loads(payload)
    except json.JSONDecodeError as err:
        log.error("Failed to load accounts.bin:", exc_info=err)
        return [], None
    accounts = []
    raw_accounts = accounts_file.get("accounts", [])
    refreshed_account = False
    for raw_acc in raw_accounts:
        acc = LauncherAccount.from_json(raw_acc)
        if not acc.token_valid or not acc.msa_valid:
            success = acc.refresh()
            if success:
                refreshed_account = True
        accounts.append(acc)
    active_account = accounts_file.get("active")
    if len(accounts) > 0 and not active_account:
        active_account = accounts[0].msa.email
        log.warning("No active account set in cache file, setting to '%s'."
                    % active_account)
    if refreshed_account:
        save_accounts()
    return accounts, active_account

def remove_account(email:str) -> bool:
    """
    Remove an account by E-mail; return `True` if removed, otherwise return
    `False`, then save the account cache.
    """
    global accounts

    i:int|None = None
    for acc in accounts:
        if acc.msa.email == email:
            i = accounts.index(acc)
            break
    if isinstance(i, int):
        del accounts[i]
        log.info("Removed %s from accounts cache." % email)
        save_accounts()
        return True
    else:
        return False
    
def set_active_account(email:str) -> bool:
    global active_account

    if email not in [acc.msa.email for acc in accounts]:
        raise ValueError("LauncherProfile '%s' not in cache!")
    active_account = email
    log.debug("Set active account to %s" % email)
    return True

def update_account(account:LauncherAccount):
    global accounts

    for i in range(len(accounts)):
        acc = accounts[i]
        if acc.msa.email == account.msa.email:
            accounts[i] = account
            return
    
    accounts.append(account)

def fetch_account(email:str) -> LauncherAccount|None:
    for acc in accounts:
        if acc.msa.email == email:
            return acc
    return None

def _create_skin_cache_if_not_exists():
    """
    Checks if the skin cache directory and metadata .json exist, and if not
    then this function creates them.
    """
    if not SKINS_CACHE_DIR.exists():
        try:
            SKINS_CACHE_DIR.mkdir(parents=True)
        except Exception as err:
            raise Exception("Failed to create skin cache directory!") from err
        
    def create_metadata_file():
        SKIN_METADATA_PATH.touch()
        SKIN_METADATA_PATH.write_text("{}", "utf-8")
        return
        
    if not SKIN_METADATA_PATH.exists():
        SKIN_METADATA_PATH.touch()
        create_metadata_file()
        return True
    else:
        md_text = SKIN_METADATA_PATH.read_text("utf-8")
        try:
            json.loads(md_text)
        except json.JSONDecodeError:
            log.error("Failed to load skin metadata cache, wiping it.")
            SKIN_METADATA_PATH.unlink()
            create_metadata_file()
            return True
        else:
            return False


def cache_skin(uuid:str, skin_data:bytes, *,
               skin_name:str="", variant:str="classic"):
    """
    Save a skin image to cache

    Returns the path
    """
    _create_skin_cache_if_not_exists()
    
    # Create filepath
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    if not skin_name:
        skin_name = "skin"
    filepath = SKINS_CACHE_DIR / uuid / ("%s_%s.png" % (skin_name, timestamp))

    # Save PNG
    if not filepath.exists():
        filepath.touch()
    filepath.write_bytes(skin_data)

    # Save metadata
    meta = json.loads(SKIN_METADATA_PATH.read_text("utf-8"))
    # that should be fine since we verify we can load the JSON earlier on
    # with _create_skin_cache_if_not_exists()
    meta[filepath.name] = {
        "name": skin_name,
        "variant": variant,
        "cached_at": int(now.timestamp()),
        "account": uuid
    }
    SKIN_METADATA_PATH.write_text(json.dumps(meta), "utf-8")

    log.debug("Saved skin for %s with name '%s' to cache."
              % (uuid, filepath.name))
    return filepath

def _load_cached_skin_meta_no_uuid():
    """
    USE `_create_skin_cache_if_not_exists()` FIRST
    THIS WILL NOT CALL IT
    """
    meta:dict[str, dict[str, str|int]]
    meta = json.loads(SKIN_METADATA_PATH.read_text("utf-8"))
    return meta

def load_cached_skin_metadata(uuid:str|None=None):
    _create_skin_cache_if_not_exists()

    if not uuid:
        return _load_cached_skin_meta_no_uuid()

    meta_all:dict[str, dict[str, str|int]]
    meta_all = json.loads(SKIN_METADATA_PATH.read_text("utf-8"))
    meta = {k: v for k, v in meta_all.items() if v.get("uuid", "") == uuid}
    return meta

def get_cached_skin_path(uuid:str, filename:str):
    """Returns a `pathlib.Path()` object if the skin exists, else `None`"""
    _create_skin_cache_if_not_exists()

    filepath = SKINS_CACHE_DIR / uuid / filename
    if (not filepath.exists()) and (not filepath.is_file()):
        return None
    else:
        return filepath
    
def set_skin(access_token:str, skin_path:str|Path, variant:str="classic"):
    """
    Upload and set the user's current skin via Mojang's API

    `variant` should be either `"classic"` or `"slim"`, will default to
    `"classic"` if not one of those two values.

    Returns `True` on success, otherwise `False`.
    """
    _create_skin_cache_if_not_exists()

    if isinstance(skin_path, str):
        skin_path = Path(skin_path)
    if (not skin_path.exists()) or (not skin_path.is_file()):
        log.warning("Skin at given path '%s' doesn't exist!" % str(skin_path))
        return False

    headers = {
        "Authorization": "Bearer %s" % access_token
    }

    variant = variant.lower()
    match variant:
        case "classic" | "slim":
            pass
        case _:
            log.warning("Skin variant type was set to invalid value '%s'!"
                        % variant)
            variant = "classic"
    
    skin_bytes = skin_path.read_bytes()
    files = {
        "variant": variant,
        "file": ("skin.png", skin_bytes, "image/png")
    }
    resp = requests.post(SKIN_CHANGE_URL, headers=headers, files=files)

    if resp.status_code in (200, 204):
        log.info("Successfully changed skin to '%s'" % skin_path.name)
        return True
    else:
        log.error("Skin upload failed!\n  HTTP status %d:\n%s"
                  % (resp.status_code, indent(resp.text, 4)))
    return False