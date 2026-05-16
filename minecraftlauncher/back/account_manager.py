import logging
import json
import time
import os

from minecraftlauncher.constants import LAUNCHER_DATA_DIR
from minecraftlauncher.auth import LauncherAccount
from minecraftlauncher.auth.encryption import data_load_hook, data_save_hook
from minecraftlauncher.functions import reswrite
from minecraftlauncher import DEV, offline_mode

log = logging.getLogger(__name__)

ACCOUNTS_FILE = LAUNCHER_DATA_DIR / "accounts.bin"
SKINS_CACHE_DIR = LAUNCHER_DATA_DIR / "skin_cache"
SKIN_METADATA_PATH = SKINS_CACHE_DIR / "skins_meta.json"

accounts: list[LauncherAccount] = []
active_account: str | None = None


def save_accounts(
    accounts_: list | None = None,
    *,
    active_xuid: str | None = None,
    return_unencrypted: bool = False,
):
    """
    Save account data to disk.

    Entries should be a full `LauncherProfile` object
    """
    global accounts
    if accounts_:
        log.warning("Overriding accounts cache")
        accounts = accounts_

    LAUNCHER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    payload_json = {
        "active": active_xuid or active_account,
        "accounts": [acc.serialize() for acc in accounts],
        "last_saved": time.time(),
    }

    if return_unencrypted:
        log.warning("Returning unencrypted accounts.bin to var (not saving)")
        return json.dumps(payload_json, indent=4 if DEV else None)

    payload = data_save_hook(payload_json)

    reswrite(ACCOUNTS_FILE, payload)

    log.info("Saved %d accounts to cache file.", len(accounts))
    return None


def save_or_replace_account(
    lp: LauncherAccount, accounts_: list[LauncherAccount] | None = None
):
    """Add or replace account into cache and save to disk."""
    global accounts
    if accounts_:
        log.warning("Overriding accounts cache")
        accounts = accounts_

    index = 0
    found_account = False
    xuid = ""
    gtg = ""
    for acc in accounts:
        new_xuid = lp.xuid
        xuid = acc.xuid
        gtg = acc.gamertag
        if new_xuid == xuid:
            index = accounts.index(acc)
            found_account = True
            break
    if found_account:
        if gtg == lp.gamertag:
            log.debug("Account %r replaced in cache", lp.gamertag)
        else:
            log.debug(
                "Account %r replaced in cache w/ new gtg: %r",
                gtg,
                lp.gamertag,
            )
        accounts[index] = lp
    else:
        log.debug("Adding account %r to accounts cache.", lp.gamertag)
        accounts.append(lp)
    save_accounts()


def load_accounts() -> tuple[list[LauncherAccount], str | None]:
    global accounts
    global active_account

    if not os.path.isfile(ACCOUNTS_FILE):
        return [], None

    if accounts and active_account:
        return accounts, active_account

    with open(ACCOUNTS_FILE, "rb") as b:
        payload_bytes = b.read()
    if payload_bytes[0:1] == b"{":
        payload = payload_bytes.decode("utf-8")
    else:
        payload = data_load_hook(payload_bytes)

    try:
        accounts_file = json.loads(payload)
    except json.JSONDecodeError as err:
        log.error("Failed to load accounts.bin:", exc_info=err)
        return [], None
    accounts = []
    raw_accounts = accounts_file.get("accounts", [])
    refreshed_account = False
    active_account = accounts_file.get("active")
    found_active = False
    for raw_acc in raw_accounts:
        acc = LauncherAccount.from_json(raw_acc)
        if (
            acc.gamertag == active_account
            and (not acc.token_valid or not acc.msa_valid)
            and not offline_mode
        ):
            success = acc.refresh()
            if success:
                refreshed_account = True
            else:
                log.warning(
                    "Failed to refresh account %r/%r:%s",
                    acc.gamertag,
                    acc.xuid,
                    success,
                )
                active_account = None
        accounts.append(acc)
        if acc.xuid == active_account:
            found_active = True
    if len(accounts) > 0 and not active_account or not found_active:
        for account in accounts:
            active_account = account.xuid
            log.warning(
                "No active account set in cache file, setting to %r.",
                account.gamertag,
            )
            if account.token_valid:
                break
            elif offline_mode or account.refresh():
                refreshed_account = True
                break
            log.warning(
                "Couldn't refresh tokens for %r, trying again",
                account.gamertag,
            )
            active_account = None
        save_accounts()
    elif refreshed_account:
        save_accounts()
    log.info(
        "Loaded %d account(s) from %r",
        len(accounts),
        os.path.split(ACCOUNTS_FILE)[-1],
    )
    return accounts, active_account


def remove_account(xuid: str) -> bool:
    """
    Remove an account by E-mail; return `True` if removed, otherwise return
    `False`, then save the account cache.
    """
    i: int | None = None
    for acc in accounts:
        if acc.xuid == xuid:
            i = accounts.index(acc)
            break
    if isinstance(i, int):
        del accounts[i]
        log.info("Removed %s from accounts cache.", xuid)
        save_accounts()
        return True
    else:
        log.warning(
            "Tried to remove an account that wasn't in the cache! (XUID: %r)",
            xuid,
        )
        return False


def set_active_account(xuid: str) -> bool:
    global active_account

    if xuid not in [acc.xuid for acc in accounts]:
        raise ValueError(f"LauncherProfile {xuid} not in cache!")
    active_account = xuid
    acc = fetch_account(xuid)
    assert acc
    log.debug("Set active account to %s", acc.gamertag)
    return True


def update_account(account: LauncherAccount):
    for i, acc in enumerate(accounts):
        if acc.xuid == account.xuid:
            accounts[i] = account
            return

    accounts.append(account)


def fetch_account(xuid: str) -> LauncherAccount | None:
    for acc in accounts:
        if acc.xuid == xuid:
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
            raise RuntimeError(
                "Failed to create skin cache directory!"
            ) from err

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
