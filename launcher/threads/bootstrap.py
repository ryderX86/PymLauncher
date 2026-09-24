import logging

from PySide6.QtCore import QThread, Signal
import requests

from launcher.auth.exceptions import BaseAuthenticationException
from launcher.back import java_manager, profile_manager, version_manager
from launcher.back.account_manager import account_man
from launcher.exceptions import EncryptedDataDecodeError
from launcher.offline import offline_man

log = logging.getLogger(__name__)


class BaseBootstrapThread(QThread):
    error = Signal(object, Exception, bool)  # self, error, can continue?
    wait_after_error: bool = False  # wait for user input to continue

    task_name: str | None = None

    loggers: dict[type, logging.Logger] = {}

    # instance attributes
    _interrupted: bool
    log: logging.Logger
    done: bool

    def __init__(self):
        super().__init__()
        self._ui_msg = f"Not yet started ({self.task_name})"
        self.done = False
        self._interrupted = False
        if type(self) in self.loggers:
            self.log = self.loggers[type(self)]
        else:
            logger = log.getChild(type(self).__name__)
            self.loggers[type(self)] = logger
            self.log = logger

    @property
    def ui_msg(self):
        return self._ui_msg

    @property
    def interrupted(self):
        return self._interrupted or self.isInterruptionRequested()

    def interrupt(self):
        self._interrupted = True
        self.requestInterruption()
        return


class VersionManifestBootstrap(BaseBootstrapThread):
    task_name = "Load version manifest"

    def run(self):
        if self.interrupted:
            return
        self._ui_msg = "Checking version manifest"
        self.log.debug("Starting version_manager setup process")
        try:
            version_manager.fetch_version_manifest()
        except requests.HTTPError as err:
            offline_man.check_requests_error(err)
            self.log.error(
                "HTTPError in fetching versions manifest, "
                "proceeding with local only.",
                exc_info=err,
            )
            self.error.emit(self, err, True)
            return
        except Exception as err:
            offline_man.check_requests_error(err)
            self.log.error(
                "Unexpected error while fetching versions manifest",
                exc_info=err,
            )
            self.error.emit(self, err, False)
            return
        if self.interrupted:
            self.log.info("Interrupted, stopping")
            return
        self._ui_msg = "Parsing versions"
        try:
            version_manager.get_version_list()
        except Exception as err:
            self.log.error(
                "Unexpected error parsing versions list:", exc_info=err
            )
            self.error.emit(self, err, False)
        self.done = True
        return


class JavaManifestBootstrap(BaseBootstrapThread):
    task_name = "Load Java info"

    def run(self):
        self._ui_msg = "Loading Java manifest"
        if not self.interrupted:
            try:
                java_manager.get_jvm_manifest()
            except Exception as err:
                self.log.error(
                    "Unexpected error loading JVM manifest:", exc_info=err
                )
                self.error.emit(self, err, False)
            else:
                self.done = True


class LaunchProfileBootstrap(BaseBootstrapThread):
    wait_after_error = True
    task_name = "Load launch profiles"
    _ui_msg = "Waiting to load launch profiles"

    def __init__(self, manifest_loader: VersionManifestBootstrap):
        super().__init__()
        self._mf_loader = manifest_loader
        self._mf_loader.finished.connect(self.start)

    def run(self):
        if not self._mf_loader.done:
            log.warning("Manifest didn't finish loading, aborting.")
            return
        elif self.isInterruptionRequested():
            log.warning("Interruption requested, aborting.")
            return
        self._ui_msg = "Loading launch profiles"
        if self.interrupted:
            return
        self.log.debug("Loading launch profiles")
        try:
            profile_manager.load_launcher_profiles()
        except PermissionError as err:
            log.critical(
                "PermissionError while loading profiles:", exc_info=err
            )
            self.wait_after_error = False
            self.error.emit(self, err, False)
            return
        except Exception as err:
            log.error("Exception while loading profiles:", exc_info=err)
            self.error.emit(self, err, False)
            self._ui_msg = "Waiting on user to confirm"
            return


class AccountManagerBootstrap(BaseBootstrapThread):
    wait_after_error = True
    task_name = "Load accounts from cache"

    def try_until_failure(self, ui_msg: str, function, first_exc: Exception):
        attempts = 0
        success = False
        self._ui_msg = f"{ui_msg} <i>(waiting to try again...)</i>"
        self.sleep(1)
        sleep_time = 1
        last_err = first_exc
        while True:
            if attempts > 3:
                break
            attempts += 1
            self._ui_msg = f"{ui_msg} <i>(attempt {attempts} of 3...)</i>"
            try:
                function()
            except requests.HTTPError as err:
                if err.args and isinstance(err.args[0], str):
                    match err.args[0][:2]:
                        case "503":
                            log.error(
                                "Server unavailable, trying again...",
                                exc_info=err,
                            )
                            sleep_time *= 2
                        case _:
                            log.error(
                                "Unexpected HTTP code, aborting...",
                                exc_info=err,
                            )
                            break
            else:
                success = True
                break
        if success is not True:
            return last_err
        else:
            return True

    def run(self):
        self._ui_msg = "Authenticating"
        if self.interrupted:
            return
        try:
            account_man.load_accounts()
        except PermissionError as err:
            self.wait_after_error = False
            self.log.critical("Unable to open accounts file:", exc_info=err)
            self.error.emit(self, err, False)
        except (UnicodeDecodeError, EncryptedDataDecodeError) as err:
            self.log.error("Failed to decrypt accounts file:", exc_info=err)
            self.error.emit(self, err, False)
        except AttributeError as err:
            self.wait_after_error = False
            self.log.error("AttributeError in account loading:", exc_info=err)
            self.error.emit(self, err, False)
        except BaseAuthenticationException as err:
            self.log.error("Auth error while loading accounts", exc_info=err)
            self.error.emit(self, err, False)
        except Exception as err:
            self.log.error(
                "Unexpected error loading accounts file:", exc_info=err
            )
            self.error.emit(self, err, False)
        else:
            if self.interrupted:
                self.log.debug("Ending early, interruption requested")
                return
            if account_man.active:
                acc = account_man.active
                if (
                    acc.token
                    and acc.token.owns_game
                    and acc.profile_needs_update()
                ):
                    self.log.info("Updating game profile")
                    self._ui_msg = "Fetching in-game profile"
                    if acc.profile:
                        func = acc.profile.refresh_profile_info
                    else:
                        func = acc.get_profile_info
                    try:
                        func()
                    except requests.HTTPError as err:
                        if offline_man.check_requests_error(err):
                            log.warning(
                                "We're offline, aborting profile fetching..."
                            )
                            return
                        if err.args and isinstance(err.args[0], str):
                            # if 503, might be momentary, try again, otherwise,
                            # abort.
                            match err.args[0][:2]:
                                case "503":
                                    success = self.try_until_failure(
                                        "Fetching profile info", func, err
                                    )
                                    if isinstance(success, Exception):
                                        log.warning(
                                            "Couldn't get profile info, "
                                            "aborting..."
                                        )
                                        self.error.emit(success, True)
                                        return
                                case _:
                                    log.warning(
                                        "Unexpected HTTP error code %s, "
                                        "aborting...",
                                        err.args[0][:2],
                                    )
                                    self.error.emit(err, True)
                        else:
                            log.error(
                                "Unexpected HTTPError, aborting...",
                                exc_info=err,
                            )
                    except Exception as err:
                        log.error(
                            "Failed to refresh profile info", exc_info=err
                        )
                        self.error.emit(self, err, True)  # non-fatal IMO
            else:
                try:
                    account_man.auto_set_active(
                        raise_on_fail=True, ignore_refreshes=True
                    )
                except RuntimeError as err:
                    self.log.warning(
                        "Failed to automatically set active account, "
                        "trying to refresh..."
                    )
                    self._ui_msg = "Reauthenticating"
                    try:
                        account_man.auto_set_active()
                    except Exception as err_2:
                        self.log.error(
                            "Unexpected error whilst reauthenticating:",
                            exc_info=err_2,
                        )
                        self.wait_after_error = False
                        self.error.emit(self, err_2, False)
                        return
                except Exception as err:
                    self.log.error(
                        "Unexpected error setting active account:",
                        exc_info=err,
                    )
                    self.wait_after_error = False
                    self.error.emit(self, err, False)
                    return
            self.done = True
