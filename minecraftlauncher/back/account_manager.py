from collections.abc import Buffer
import logging
import json
import time
import os

from minecraftlauncher import constants
from minecraftlauncher.paths import paths
from minecraftlauncher.auth import LauncherAccount
from minecraftlauncher.auth.encryption import data_load_hook, data_save_hook
from minecraftlauncher.auth import encryption
from minecraftlauncher.auth.exceptions import NoConnectionError
from minecraftlauncher.exceptions import EncryptedDataDecodeError
from minecraftlauncher.functions import reswrite
from minecraftlauncher.offline import offline_man

log = logging.getLogger(__name__)


class AccountManager:
    """WIP, don't use"""

    _instance: AccountManager | None = None

    # instance attributes
    _accounts: dict[str, LauncherAccount] = {}  # str is XUID
    _active_account: LauncherAccount | None
    _loaded: bool

    def __new__(cls):
        if cls._instance:
            log.warning(
                "Attempted to construct a second instance of AccountManager"
            )
            return cls._instance  # singleton
        else:
            return cls()

    def __init__(self):
        self._loaded = False
        self._accounts = {}
        self._active_account = None
        type(self)._instance = self  # singleton

    @property
    def active(self):
        return self._active_account

    @active.setter
    def active(self, account_or_xuid: str | LauncherAccount):
        return self.set_active(account_or_xuid)

    def load_accounts(self):
        """
        Loads accounts from accounts.bin.

        Can raise any of `json.JSONDecodeError`,
        `minecraftlauncher.exceptions.EncryptedDataDecodeError`,
        `UnicodeError` (very rarely), or a `BaseAuthenticationException`
        """
        if self._accounts:
            log.warning(
                "load_accounts() called while self._accounts already exists, "
                "resetting it"
            )
            self._accounts = {}
        if not paths.ready:
            raise RuntimeError(
                "load_accounts() called without ready PathFinder object"
            )
        if not os.path.isfile(paths.accounts_file):
            return

        try:
            with open(paths.accounts_file, "rb") as file:
                file_bytes = file.read()
        except PermissionError:
            log.debug(
                "PermissionError occured whilst attempting to read accounts.bin"
            )
            log.debug("accounts.bin path: %r", paths.accounts_file)
            log.debug("user directory: %r", os.path.expanduser("~"))
            raise

        if len(file_bytes) == 0:
            log.warning(
                "Blank accounts.bin file detected, aborting load process"
            )
            return
        if file_bytes.startswith(b"{"):
            encrypted = False
        else:
            encrypted = True

        if encrypted:
            try:
                text = data_load_hook(file_bytes)
            except (RuntimeError, UnicodeError) as err:
                raise EncryptedDataDecodeError(*err.args) from err
        else:
            text = file_bytes.decode("utf-8")

        # if a JSONDecodeError exists there's not really a point to catching it
        # here, since we handle this in the callers for load_accounts() so that
        # we can notify the user within the GUI instead.
        accounts_bin: dict = json.loads(text)
        raw_accounts: list[dict] = accounts_bin.get("accounts", [])
        last_used_xuid: str | None = accounts_bin.get("active")

        for cached in raw_accounts:
            account = LauncherAccount.from_json(cached)
            self._accounts[account.xuid] = account

        if last_used_xuid in self._accounts:
            self.auto_set_active(last_used_xuid, raise_on_fail=False)

        return

    def list(self, sort=True) -> list[LauncherAccount]:
        output = [*self._accounts.values()]
        if sort:
            output.sort(key=lambda a: a.displayname.lower())
        return output

    def auto_set_active(
        self, preferred_xuid: str | None, raise_on_fail: bool = False
    ):
        set_account = False
        if preferred_xuid and preferred_xuid in self._accounts:
            account = self._accounts[preferred_xuid]
            try:
                self._check_refresh_token(account)
            except:
                set_account = False
            else:
                log.debug(
                    "Switching account from %r to %r",
                    self._active_account,
                    account,
                )
                self._active_account = account
                return
        elif preferred_xuid:
            raise KeyError(
                f"Account with XUID {preferred_xuid!r} not found in cache!"
            )

        for acc in self.list():
            if acc.xuid == preferred_xuid:
                continue
            try:
                self._check_refresh_token(acc)
            except Exception as err:
                log.debug(
                    "Ignoring exception from refreshing %r:",
                    acc.gamertag,
                    exc_info=err,
                )
                continue
            else:
                log.debug(
                    "Switching account from %r to %r",
                    self._active_account,
                    acc,
                )
                self._active_account = acc
                set_account = True
                break

        if raise_on_fail and not set_account:
            raise RuntimeError("Failed to set any active account")
        return

    def save_accounts(self):
        store = {
            "active": (
                self._active_account.gamertag if self._active_account else None
            ),
            "accounts": [account.serialize() for account in self.list()],
            "last_saved": time.time(),
        }

        payload: Buffer
        if encryption.ENABLED:
            payload = data_save_hook(store)
        else:
            payload = json.dumps(store).encode("utf-8")

        reswrite(paths.accounts_file, payload)
        log.debug(
            "Saved %d accounts to %r", len(self._accounts), paths.accounts_file
        )

    def _check_refresh_token(self, acc_or_xuid: str | LauncherAccount):
        if isinstance(acc_or_xuid, str):
            acc = self.get(acc_or_xuid)
        elif isinstance(acc_or_xuid, LauncherAccount):
            acc = acc_or_xuid
        else:
            raise TypeError(acc_or_xuid)
        if offline_man.offline or acc.token_valid:
            return
        try:
            acc.refresh()
        except NoConnectionError:
            return  # handled elsewhere
        else:
            self.save_accounts()
            return

    def set_active(self, new_account: str | LauncherAccount):
        if isinstance(new_account, LauncherAccount):
            if new_account.xuid not in self._accounts:
                log.warning(
                    "set_active() called (with LauncherAccount instance) "
                    "without account present in cache. "
                    "Adding it to cache and switching to it. "
                    "Ensure you use add_account() first."
                )
                self._accounts[new_account.xuid] = new_account
            new_account = new_account.xuid
        account = self.get(new_account)

        if not account.token_valid and not offline_man.offline:
            log.debug(
                "%r doesn't have an active token, trying to refresh it",
                account.gamertag,
            )
            try:
                account.refresh()
            except NoConnectionError:
                pass

        # if refresh fails, exception will be raised before this happens:
        self._active_account = account

    def replace_into(self, account: LauncherAccount):
        """Add or replace account into the cache"""
        self._accounts[account.xuid] = account

    replace = replace_into
    """Alias for replace_into()"""
    add = replace_into
    """Alias for replace_into()"""

    def get(self, xuid: str):
        if xuid not in self._accounts:
            raise KeyError(f"Account with XUID {xuid} not in cache")
        return self._accounts[xuid]

    def remove(self, xuid: str):
        if xuid not in self._accounts:
            raise KeyError(f"Account with XUID {xuid} not in cache")
        if self._active_account and self._active_account.xuid == xuid:
            self._active_account = None
        log.debug("Removing %r from accounts", self._accounts[xuid].gamertag)
        del self._accounts[xuid]

    def __iter__(self):
        return self.list().__iter__()

    def __getitem__(self, xuid: str):
        if xuid not in self._accounts:
            raise KeyError(f"Account with XUID {xuid} not in cache")
        return self._accounts[xuid]

    def __delitem__(self, xuid: str):
        if xuid not in self._accounts:
            raise KeyError(f"Account with XUID {xuid} not in cache")
        log.debug("Removing account %r from cache", self[xuid].gamertag)
        del self._accounts[xuid]

    def __setitem__(self, xuid: str, account: LauncherAccount):
        if xuid in self._accounts:
            log.debug("Overriding account %r", self[xuid].gamertag)
        self._accounts[xuid] = account


accounts: list[LauncherAccount] = []
active_account: str | None = None


def _sort_accounts():
    accounts.sort(key=lambda a: a.displayname.lower())


def save_accounts(
    accounts_: list | None = None,
    *,
    active_xuid: str | None = None,
    return_unencrypted: bool = False,
):
    """
    Save account data to disk.

    Entries should be a full `LauncherAccount` object.

    If `accounts_` isn't provided, the global `accounts` is used instead.
    """
    global accounts
    if accounts_:
        log.warning("Overriding accounts cache")
        accounts = accounts_
    elif not accounts_ and not accounts:
        log.debug("No accounts to save")
        return

    payload_json = {
        "active": active_xuid or active_account,
        "accounts": [acc.serialize() for acc in accounts],
        "last_saved": time.time(),
    }

    if return_unencrypted:
        log.warning("Returning unencrypted accounts.bin to var (not saving)")
        return json.dumps(payload_json, indent=4 if constants.DEV else None)

    payload = data_save_hook(payload_json)

    reswrite(paths.accounts_file, payload)

    log.info("Saved %d accounts to cache file.", len(accounts))
    return None


def save_or_replace_account(
    acc: LauncherAccount, accounts_: list[LauncherAccount] | None = None
):
    """Add or replace account into cache and save to disk."""
    global accounts
    if accounts_:
        log.warning("Overriding accounts cache")
        accounts = accounts_

    for i, account in enumerate(accounts):
        if account.xuid == acc.xuid:
            if account.has_same_info(acc):
                log.warning(
                    "save_or_replaced_account() called with no changes!"
                )
            if account.gamertag == acc.gamertag:
                log.debug(
                    "Replacing cached account %r with updated info",
                    account.gamertag,
                )
            else:
                log.debug(
                    "Replacing cached account %r with updated info (new tag: %r)",
                    account.gamertag,
                    acc.gamertag,
                )
            accounts[i] = acc
            save_accounts()
            return
    log.debug("Adding %r to cached accounts", acc.gamertag)
    accounts.append(acc)
    _sort_accounts()
    save_accounts()
    return


def choose_account(last_used_xuid: str | None = None):
    """
    Look at all accounts currently loaded in memory, then compare XUIDs and
    authentication status. If everything looks good from the first, we run with
    that, otherwise we attempt reauthentication until we get an authenticated
    account or find out we're in offline mode.
    """
    global active_account

    refreshed_any_account: bool = False

    for account in sorted(accounts, key=lambda a: a.xuid != last_used_xuid):
        if account.token_valid:
            log.debug(
                "Found an account with active token: %r; using this one.",
                account.gamertag,
            )
            active_account = account.xuid
            break
        else:
            log.debug(
                "Invalid token for %r, trying to refresh it...",
                account.gamertag,
            )
            try:
                account.refresh()
            except NoConnectionError:
                log.info("We're offline, proceeding with %r.", account.gamertag)
                active_account = account.xuid
                break
            except Exception as err:
                log.debug(
                    "Failed token refresh, trying next account", exc_info=err
                )
                active_account = None
                continue
            else:
                refreshed_any_account = True
                log.debug(
                    "Successfully refreshed token, we'll use %r.",
                    account.gamertag,
                )
                active_account = account.xuid
                break

    # we have to save accounts if we know there's a refresh otherwise there's
    # no guarentee anywhere we'll save accounts unless one is added or there's
    # a refresh in the play button's process
    if refreshed_any_account:
        save_accounts()
    return


def load_accounts() -> tuple[list[LauncherAccount], str | None]:
    global accounts
    global active_account

    if not os.path.isfile(paths.accounts_file):
        return [], None

    if accounts:
        return accounts, active_account

    # read accounts file:
    with open(paths.accounts_file, "rb") as b:
        payload_bytes = b.read()
    if payload_bytes[0:1] == b"{":
        encrypted = False
        payload = payload_bytes.decode("utf-8")
    else:
        encrypted = True
        try:
            payload = data_load_hook(payload_bytes)
        except (UnicodeError, RuntimeError) as err:
            raise EncryptedDataDecodeError(*err.args) from err

    try:
        accounts_file = json.loads(payload)
    except json.JSONDecodeError as err:
        log.error("Failed to load accounts.bin:", exc_info=err)
        if encrypted and not payload.startswith("{"):
            raise EncryptedDataDecodeError from err
        else:
            raise err

    # parse accounts:
    accounts = []
    raw_accounts = accounts_file.get("accounts", [])
    active_account = accounts_file.get("active")
    for raw_acc in raw_accounts:
        acc = LauncherAccount.from_json(raw_acc)
        accounts.append(acc)

    # sort & choose first account
    _sort_accounts()
    choose_account(active_account)

    log.info(
        "Loaded %d account(s) from %r",
        len(accounts),
        os.path.split(paths.accounts_file)[-1],
    )
    return accounts, active_account


def remove_account(xuid: str) -> bool:
    """
    Remove an account by XUID; return `True` if removed, otherwise return
    `False`, then save the account cache.
    """
    global active_account
    i: int | None = None
    for acc in accounts:
        if acc.xuid == xuid:
            i = accounts.index(acc)
            break
    if isinstance(i, int):
        if xuid == active_account:
            active_account = None
        del accounts[i]
        log.info("Removed %s from accounts cache.", xuid)
        if len(accounts) > 0:
            choose_account()
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
        raise KeyError(f"Account {xuid!r} not in cache")
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


def reset_accounts_file():
    """
    Reset the accounts.bin file and save previous version to a backup file
    """
    global accounts, active_account
    if not os.path.isfile(paths.accounts_file):
        log.warning(
            "reset_accounts_file() called while accounts.bin doesn't "
            "exist! (checked at %r)",
            paths.accounts_file,
        )
        return
    accounts = []
    active_account = None
    backup_name = f"{paths.accounts_file}-corrupted-{int(time.time())}.bak"
    log.warning("Renaming %r -> %r", paths.accounts_file, backup_name)
    os.replace(paths.accounts_file, backup_name)
