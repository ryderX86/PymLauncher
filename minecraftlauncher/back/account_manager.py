import json
import logging
import os
import time
from collections.abc import Buffer, Callable
from types import MappingProxyType
from typing import Any

from minecraftlauncher.auth import LauncherAccount, encryption
from minecraftlauncher.auth.encryption import data_load_hook, data_save_hook
from minecraftlauncher.auth.exceptions import NoConnectionError
from minecraftlauncher.exceptions import EncryptedDataDecodeError
from minecraftlauncher.functions import reswrite
from minecraftlauncher.offline import offline_man
from minecraftlauncher.paths import paths

log = logging.getLogger(__name__)


class AccountManager:
    _instance: "AccountManager | None" = None

    # instance attributes
    _accounts: dict[str, LauncherAccount] = {}  # str is XUID
    _active_account: LauncherAccount | None
    _loaded: bool = False
    _active_callbacks: list[Callable[[LauncherAccount], None]]
    _original_text: str | None
    """
    Backup of the decrypted text in accounts.bin; used for write-spam
    prevention
    """

    def __new__(cls):
        if cls._instance:
            log.warning(
                "Attempted to construct a second instance of AccountManager"
            )
            return cls._instance  # singleton
        else:
            return object.__new__(cls)

    def __init__(self):
        if self._loaded:
            log.warning("__init__() ran twice!")
            return
        self._loaded = False
        self._accounts = {}
        self._active_account = None
        self._active_callbacks = []
        self._original_text = None
        type(self)._instance = self  # singleton

    @property
    def active(self):
        return self._active_account

    @active.setter
    def active(self, account_or_xuid: str | LauncherAccount):
        return self.set_active(account_or_xuid)

    @property
    def loaded(self):
        return self._loaded

    @property
    def has_accounts(self):
        return len(self._accounts) > 0

    def __bool__(self):
        return self._loaded

    def load_accounts(self):
        """
        Loads accounts from accounts.bin.

        Can raise any of `json.JSONDecodeError`,
        `EncryptedDataDecodeError`, `UnicodeError` (very rarely), or a
        `BaseAuthenticationException`.

        If a `UnicodeError` was raised, this will (usually) mean one of two
        things:
        1. The accounts store was incorrectly identified as unencrypted
        (shouldn't be possible but can happen)
        2. Decryption failed in a spectacular way (it should normally raise
        `EncryptedDataDecodeError`)
        """
        if self._accounts:
            log.warning(
                "load_accounts() called while self._accounts already exists, "
                "re-loading it"
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

        self._original_text = text

        # if a JSONDecodeError exists there's not really a point to catching it
        # here, since we handle this in the callers for load_accounts() so that
        # we can notify the user within the GUI instead.
        accounts_bin: dict = json.loads(text)
        raw_accounts: list[dict] = accounts_bin.get("accounts", [])
        last_used_xuid: str | None = accounts_bin.get("active")

        for cached in raw_accounts:
            try:
                account = LauncherAccount.from_json(cached)
            except Exception as err:
                log.warning(
                    "Failed to load %r from accounts.bin file, skipping",
                    cached.get("xuid", "<No XUID present>"),
                    exc_info=err,
                )
                continue
            else:
                self._accounts[account.xuid] = account

        self._loaded = True

        if last_used_xuid in self._accounts:
            self.auto_set_active(last_used_xuid, raise_on_fail=False)
        elif last_used_xuid is not None:
            log.warning(
                "Last known active account (XUID: %r) not in accounts cache",
                last_used_xuid,
            )
            self.auto_set_active()

        return

    def save_accounts(self):
        store = self.dump()

        json_text = json.dumps(store)
        if self._original_text == json_text:
            log.debug(
                "Skipping accounts.bin write since no changes were made."
            )
            return

        payload: Buffer
        if encryption.ENABLED:
            payload = data_save_hook(json_text)
        else:
            payload = json_text.encode("utf-8")

        reswrite(paths.accounts_file, payload)
        log.debug(
            "Saved %d accounts to %r", len(self._accounts), paths.accounts_file
        )

    def list(self, sort=True) -> list[LauncherAccount]:
        output = [*self._accounts.values()]
        if sort:
            output.sort(key=lambda a: a.displayname.lower())
        return output

    def auto_set_active(
        self,
        preferred_xuid: str | None = None,
        raise_on_fail: bool = False,
        ignore_refreshes: bool = False,
    ) -> LauncherAccount | None:
        set_account = False
        if preferred_xuid and preferred_xuid in self._accounts:
            account = self._accounts[preferred_xuid]

            # we should ignore all refresh needs when calling this from the GUI
            # so that we don't refresh the tokens without showing the user any
            # indicators, since that would end up freezing the GUI needlessly
            if not ignore_refreshes and not account.token_valid:
                try:
                    self._check_refresh_token(account)
                except Exception as err:
                    log.debug(
                        "Ignoring %r exception while refreshing tokens for %r",
                        type(err).__name__,
                        account.gamertag,
                    )
            # after we determine token refresh status, if it's valid we can
            # simply set the account and exit before starting a loop
            if account.token_valid:
                if self._active_account:
                    log.debug(
                        "Switching account from %r to %r",
                        (
                            self._active_account.gamertag
                            if self._active_account
                            else None
                        ),
                        account.gamertag,
                    )
                else:
                    log.debug(
                        "Automatically setting active account to %r",
                        account.gamertag,
                    )
                self._active_account = account
                if self.active:
                    for callback in self._active_callbacks:
                        callback(self.active)
                return self.active
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
                    (
                        self._active_account.gamertag
                        if self._active_account
                        else "<none>"
                    ),
                    acc.gamertag,
                )
                self._active_account = acc
                set_account = True
                break

        if raise_on_fail and not set_account:
            raise RuntimeError("Failed to set any active account")
        if self.active:
            for callback in self._active_callbacks:
                callback(self.active)
        return self.active

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

    def set_active(
        self,
        new_account: str | LauncherAccount,
        ignore_refreshes: bool = False,
    ):
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
        account = self[new_account]

        if (
            not account.token_valid
            and not offline_man.offline
            and not ignore_refreshes
        ):
            log.debug(
                "%r doesn't have an active token, trying to refresh it",
                account.gamertag,
            )
            try:
                account.refresh()
            except NoConnectionError:
                pass

        log.debug(
            "Switching account from %r to %r",
            self.active.gamertag if self.active else None,
            account.gamertag,
        )

        # if refresh fails, exception will be raised before this happens:
        self._active_account = account
        assert self.active
        for callback in self._active_callbacks:
            callback(self.active)
        return self.active

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

    def remove(self, xuid: str | LauncherAccount):
        if isinstance(xuid, LauncherAccount):
            xuid = xuid.xuid
        del self[xuid]

    def __iter__(self):
        """Returns an iterator of all LauncherAccount objects in cache."""
        return self.list().__iter__()

    def __getitem__(self, xuid: str):
        if xuid not in self._accounts:
            raise KeyError(f"Account with XUID {xuid} not in cache")
        return self._accounts[xuid]

    def __delitem__(self, xuid: str):
        if xuid not in self._accounts:
            raise KeyError(f"Account with XUID {xuid} not in cache")
        log.debug("Removing account %r from cache", self[xuid].gamertag)
        if self.active and self.active.xuid == xuid:
            self._active_account = None
        del self._accounts[xuid]
        self.save_accounts()

    def __setitem__(self, xuid: str, account: LauncherAccount):
        if xuid in self._accounts:
            log.debug("Overriding account %r", self[xuid].gamertag)
        self._accounts[xuid] = account

    def __len__(self):
        return len(self._accounts)

    def dump(self):
        return {
            "active": (self.active.xuid if self.active else None),
            "accounts": [account.serialize() for account in self.list()],
        }

    def reset_accounts_file(self):
        """
        "Resets" the accounts.bin file by renaming it to "accounts.bin.bak"

        (adds onto `paths.accounts_file`, so `accounts-DESKTOP-4SQSLS.bin`
        would get renamed to `accounts-DESKTOP-4SQSLS.bin.bak`)

        If the file already exists, the timestamp will be appended to
        `accounts.bin` or `accounts-DESKTOP-4SQSLS.bin` before `.bak`.
        """
        if not os.path.isfile(paths.accounts_file):
            raise RuntimeError(
                "reset_accounts_file() called without an existing file"
            )
        if os.path.isfile(f"{paths.accounts_file}.bak"):
            filename = f"{paths.accounts_file}-{int(time.time())}.bak"
        else:
            filename = f"{paths.accounts_file}.bak"

        log.debug("Resetting %r (backup: %r)", paths.accounts_file, filename)
        os.replace(paths.accounts_file, filename)

    def dict(self):
        return MappingProxyType(self._accounts)

    as_dict = dict

    def __contains__(self, xuid_or_account: str | LauncherAccount):
        """
        Checks if the account (or account associated with the provided XUID)
        is in the accounts cache.
        """
        if isinstance(xuid_or_account, str):
            return xuid_or_account in self._accounts
        else:
            return xuid_or_account in self._accounts.values()

    def add_switch_callback(
        self,
        callback: Callable[[LauncherAccount], Any],
        destroyed_signal: Any = None,
    ):
        if callback in self._active_callbacks:
            log.warning(
                "Attempted to add callback %r multiple times",
                callback.__name__,
            )
            return
        self._active_callbacks.append(callback)
        if destroyed_signal is not None:
            try:
                destroyed_signal.connect(
                    lambda: self.remove_switch_callback(callback)
                )
            except AttributeError as err:
                raise TypeError(
                    "Object passed to 'destroyed_signal' doesn't "
                    "have a 'connect()' method"
                ) from err

    def remove_switch_callback(
        self, callback: Callable[[LauncherAccount], None]
    ):
        if callback not in self._active_callbacks:
            raise AttributeError(
                f"Function {callback.__name__!r} was never registered "
                "as a callback"
            )
        self._active_callbacks.remove(callback)


account_man = AccountManager()
