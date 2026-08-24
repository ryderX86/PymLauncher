import atexit
import logging
import sys
from json import JSONDecodeError
from time import sleep

import requests
from PySide6.QtCore import QFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyleFactory

from . import constants, get_qapp, logs, setup_qapp
from .auth import LauncherAccount
from .auth.exceptions import (
    BaseAuthenticationException,
    MSAServerUnavailableError,
    NoConnectionError,
)
from .back import (
    java_manager,
    profile_manager,
    version_manager,
)
from .back.account_manager import account_man
from .config import config
from .exceptions import EncryptedDataDecodeError
from .front.event_filters import FocusEventFilter
from .front.styles import STYLESHEET, FontList, gen_palette, get_fonts
from .front.window.game_error import ErrorDisplay
from .front.window.loading_blocker import LoadingBlockerWindow
from .front.window.login import LoginWindow
from .front.window.main.main_window import MainWindow
from .front.window.warning import ButtonConfig, WarningDialog
from .functions import detect_set_clipboard, uisleep
from .functions.error_box import error_box
from .launchargs import launchargs
from .offline import connectivity_poller, offline_man
from .ostools.win32 import setup_app_id
from .paths import paths
from .threads.install_worker import InstallWorker
from .threads.launch_worker import LaunchWorker

log = logging.getLogger("minecraftlauncher")

# we use this to detect crashes somewhat, allowing us to not write garbage data
# or bad configs, etc.
clean_exit = False


class LauncherApp:
    """Controller"""

    qapp: QApplication

    close_if_login_aborted: bool
    """Should we close if the login process is aborted?"""

    fonts: FontList
    """Named tuple containing the fonts"""

    install_worker: InstallWorker
    launch_worker: LaunchWorker

    def __init__(self):
        self.qapp = get_qapp()
        self.fonts = get_fonts()
        detect_set_clipboard()
        self.qapp.setApplicationName("Minecraft Launcher")
        match constants.OS:
            case "windows":
                pass
            case _:
                self.qapp.setStyle(QStyleFactory.create("Windows"))
        self.qapp.setStyleSheet(STYLESHEET)
        self.qapp.setFont(self.fonts.main)
        self.qapp.setPalette(gen_palette())
        if QFile(":/icon.ico").exists():
            self.qapp.setWindowIcon(QIcon(":/icon.ico"))
        else:
            log.debug("Couldn't set app icon")
        self._event_filter = FocusEventFilter()
        self.qapp.installEventFilter(self._event_filter)

        self.lb_window = LoadingBlockerWindow()
        self.lb_window.rejected.connect(self._close_event)
        self.lb_window.show()
        # just in case it doesn't fully run the rest of main():
        self.qapp.aboutToQuit.connect(self._set_clean_exit)

        self.main_window = MainWindow()
        self.main_window.login_requested.connect(self.show_login)
        self.main_window.account_page.logout_requested.connect(self.logout)
        self.main_window.home_page.play_requested.connect(self.play)

        account_man.add_switch_callback(self._on_account_changed)

        self.main_window.home_page.game_crash.connect(self.show_crash_dialog)

        if constants.DEV:
            if launchargs.debug_splash_screen:
                self.lb_window.set_text("Waiting 5s for splash debugging")
                sleep(5)

    def _set_clean_exit(self):
        global clean_exit
        clean_exit = True

    def buildall(self):
        for page in self.main_window.page_list:
            page.build()

    def run(self) -> int:
        global clean_exit
        log.debug("Attempting to get version manifest set up...")
        self.lb_window.set_text("Fetching version list")
        try:
            version_manager.fetch_version_manifest()
            version_manager.get_version_list()
        except Exception as err:
            log.error("Failed to load version manifest:", exc_info=err)
            if isinstance(err, requests.RequestException):
                if not offline_man.check_requests_error(err):
                    error_box(
                        "Failed to get the version manifest! "
                        "Relaunch if versions are missing."
                    )

        log.debug("Attempting to get JRE manifest...")
        self.lb_window.set_text("Fetching Java version list")
        try:
            java_manager.get_jvm_manifest()
        except Exception as err:
            log.error("Failed to load JRE manifest:", exc_info=err)
            if isinstance(err, requests.RequestException):
                if not offline_man.check_requests_error(err):
                    error_box(
                        "Failed to get the Java manifest! "
                        "Relaunch if you can't install/launch the game."
                    )

        self.lb_window.set_text("Loading launch profiles")
        try:
            profile_manager.load_launcher_profiles()
        except Exception as err:
            reset_profiles = WarningDialog.warn(
                text="Failed to load launch profiles. The file may be corrupted.\n"
                "Would you like to reset the profiles file?\n"
                "(A backup will be created.)",
                title="Error loading accounts",
                button_config=ButtonConfig.YES_NO,
                button_labels={"no": "Close Launcher"},
                parent=self.lb_window,
            )
            if reset_profiles:
                profile_manager.reset_profiles()
                profile_manager.load_launcher_profiles()
            else:
                clean_exit = True
                sys.exit()
        self.lb_window.set_text("Loading UI data...")
        self.buildall()
        self.load_accounts()

        log.info("Finished loading. Showing main window")
        self.main_window.show()
        # self.lb_window.setParent(self.main_window)
        self.lb_window.hide()
        focused = QApplication.focusWidget()
        if focused:
            focused.clearFocus()
        self.main_window.check_for_launch_arg()
        return self.qapp.exec()

    def load_accounts(self):
        global clean_exit
        log.debug("Attempting to load accounts from cache...")
        if not offline_man.offline:
            self.lb_window.set_text("Authenticating")
        try:
            account_man.load_accounts()
        except PermissionError as err:
            log.error("Failed to read accounts.bin:", exc_info=err)
            error_box(
                "Failed to read accounts from storage.\n"
                "The launcher cannot continue loading and will close.\n"
                "Please make sure you are using the right account with the "
                "necessary permissions."
            )
            sys.exit(-1)
        except AttributeError as err:
            log.error("AttributeError in account loading:", exc_info=err)
            if err.obj is not None:
                log.debug("Object type at fault: %r", type(err.obj).__name__)
            else:
                log.debug("Can't retrieve object type from exception")
            if err.name is not None:
                log.debug("Missing key: %r", err.name)
            else:
                log.debug("Can't retrieve key name from exception")
            sys.exit(-1)
        except (JSONDecodeError, EncryptedDataDecodeError) as err:
            # get user input before proceeding, if True then the user answered
            # yes to deleting the accounts.bin file
            if isinstance(err, EncryptedDataDecodeError):
                dialog_text = (
                    "Failed to load accounts from storage.\n"
                    "The file may be unrecoverable due to a decryption error.\n"
                    "Would you like to reset the storage file and try again?\n"
                    "(A backup will remain in place)"
                )
            else:
                dialog_text = (
                    "Failed to load accounts from storage.\n"
                    "The file may have invalid formatting.\n"
                    "Would you like to reset the storage file and try again?\n"
                    "(A backup will remain in place)"
                )
            delete_accounts = WarningDialog.warn(
                text=dialog_text,
                title="Error loading accounts",
                button_config=ButtonConfig.YES_NO,
                button_labels={"no": "Close Launcher"},
                parent=self.lb_window,
            )
            if delete_accounts:
                account_man.reset_accounts_file()
                account_man.load_accounts()
            else:
                clean_exit = True
                sys.exit()
        except BaseAuthenticationException as err:
            if len(account_man) > 1:
                self.close_if_login_aborted = False
            else:
                self.close_if_login_aborted = True
            self.lb_window.hide()
            self.show_login()
            if not account_man.active:
                try:
                    account_man.auto_set_active()
                except RuntimeError:
                    log.debug(
                        "User aborted login and no accounts have up-to-date "
                        "credentials. Exiting."
                    )
                    clean_exit = True
                    sys.exit()
        except Exception as err:
            log.error("Unexpected error in account loading:", exc_info=err)
            error_box(
                "Failed to read accounts from storage.\n"
                "The launcher cannot continue loading and will now close."
            )
            sys.exit(-1)
        if account_man.has_accounts:
            self.close_if_login_aborted = False
        else:
            self.close_if_login_aborted = True
            self.lb_window.hide()
            self.show_login()
        self._refresh_account_ui()

    def show_login(
        self, *, reason: str | None = None, automatic: bool = False
    ):
        if offline_man.offline and not automatic:
            error_box(
                "Cannot log in while offline! Please wait and try again."
            )
            return self._on_login_abort()
        elif offline_man.offline:  # TODO: confirm this works
            if len(account_man) > 1:
                account_man.auto_set_active()
                return
        dialog = LoginWindow(self.main_window, reason=reason)
        dialog.login_complete.connect(self._on_login_complete)
        dialog.rejected.connect(self._on_login_abort)
        dialog.exec()
        return

    def _on_login_abort(self):
        global clean_exit
        active_acc = account_man.active
        if self.close_if_login_aborted or not active_acc:
            clean_exit = True
            sys.exit(1)
        account_man.set_active(active_acc)
        return self._refresh_account_ui()

    def show_crash_dialog(self, exit_code: str, stderr: str):
        log.debug("Showing crash dialog to user")
        dialog = ErrorDisplay(self.main_window, exit_code, stderr)
        dialog.show()
        dialog.exec()
        return

    def _on_login_complete(self, account: LauncherAccount):
        if account:
            self.close_if_login_aborted = False
        self.lb_window.open()
        self.lb_window.set_text("Loading account details")
        self.lb_window.update()
        account_man.replace(account)
        account_man.set_active(account.xuid)
        self._refresh_account_ui()
        self.lb_window.hide()
        return

    def logout(self):
        if account_man.active:
            account_man.remove(account_man.active)
        if account_man.has_accounts:
            account_man.auto_set_active()
        self._refresh_account_ui()

        if not account_man.has_accounts:
            log.info("No accounts left, showing login window.")
            self.close_if_login_aborted = True
            return self.show_login()
        return

    def play(self):
        if not account_man.active:
            error_box("No active account! Please submit a bug report.")
            return
        active = account_man.auto_set_active()
        if not active:
            self.main_window.home_page.aborted_launch()
            return

        profile = profile_manager.get_current_profile()
        if not profile:
            error_box("No active launch profile! Please submit a bug report.")
            return

        if not active.profile:
            log.debug("Can't find account profile, fetching manually...")
            active.get_profile_info()
            assert active.profile

        if not active.token or not active.token_valid:
            log.debug(
                "Invalid or no token for %r, refreshing...", active.gamertag
            )
            try:
                active.refresh()
            except NoConnectionError:
                log.info("No connection, getting user's input")
                should_proceed = WarningDialog.warn(
                    self.main_window,
                    "Authentication Error",
                    "Failed to connect to the authentication servers. "
                    "Do you want to launch in offline mode?",
                    button_config=ButtonConfig.YES_NO,
                )
                if not should_proceed:
                    self.main_window.home_page.aborted_launch()
                    return
            except Exception as err:
                self.main_window.home_page.aborted_launch()
                dialog = LoginWindow(self.main_window, reason=str(err))
                dialog.exec()
                return

        self.install_worker = InstallWorker(
            profile.version_id, profile, active, True, self.main_window
        )
        self.launch_worker = LaunchWorker(
            self.install_worker, None, self.main_window
        )
        self.main_window.home_page.prep_for_launch(
            self.install_worker, self.launch_worker
        )
        self.install_worker.done.connect(self.launch_worker.start_if_success)
        self.install_worker.start()

    def _on_account_changed(
        self, acc: LauncherAccount, *, current_retries: int = 0
    ) -> None:
        MAX_RETRIES = 5
        if self.lb_window.isVisible():
            self.lb_window.accept()
        if (
            not acc.token or not acc.token.is_active
        ) and not offline_man.offline:
            if not current_retries:
                self.lb_window.set_text("Reauthenticating")
            self.lb_window.open()
            try:
                acc.refresh()
            except NoConnectionError:
                pass  # handled elsewhere already
            except MSAServerUnavailableError:
                if not current_retries or current_retries < MAX_RETRIES:
                    log.warning(
                        "Failed to authenticate: Server unavailable; "
                        "retrying (attempt %i of %i)",
                        current_retries,
                        MAX_RETRIES,
                    )
                    self.lb_window.set_text(
                        "Server currently unavailable, "
                        "waiting to try again (attempt "
                        f"{current_retries+1} of {MAX_RETRIES+1})"
                    )
                    uisleep(5)
                    self.lb_window.accept()
                    return self._on_account_changed(
                        acc, current_retries=current_retries + 1
                    )
                else:
                    log.error(
                        "Failed to authenticate: Server unavailable;"
                        " max retries exceeded. Notifying user."
                    )
                    error_box(
                        "Failed to authenticate: "
                        "The server is currently unavailable. "
                        "Please try again later."
                    )
                    self.lb_window.accept()
                    self.main_window.account_dropdown.next_account()
                    return
            except (
                BaseAuthenticationException
            ) as err:  # should only ever be a 402 by this point
                log.warning(
                    "Failed to refresh %r: %r. Prompting user to relog.",
                    acc.gamertag,
                    type(err).__name__,
                )
                dialog = LoginWindow(self.lb_window, reason=str(err))
                dialog.rejected.connect(
                    self.main_window.account_dropdown.next_account
                )
                dialog.exec()
                return
            else:
                self.lb_window.accept()
                account_man.replace_into(acc)
        self._refresh_account_ui()
        return

    def _refresh_account_ui(self):
        self.main_window.account_dropdown.refresh()
        if not account_man.active:
            return
        active_account = account_man.active
        assert active_account
        if not active_account.token_valid and not offline_man.offline:
            self.lb_window.set_text("Authenticating")
            try:
                active_account.refresh()
            except NoConnectionError:
                pass
            except Exception as err:
                dialog = LoginWindow(self.main_window, reason=str(err))
                dialog.exec()
                if not active_account.token_valid:
                    self.main_window.account_dropdown.next_account()
                    return
            else:
                account_man.replace_into(active_account)

    def _close_event(self):
        self.qapp.exit(0)


def on_exit():
    """
    Registered with `atexit` in `main()`.
    """
    if not clean_exit:
        log.error("Something went very wrong, not doing normal cleanup.")
        return
    log.info("Cleaning up")
    if connectivity_poller.has_run and offline_man.offline:
        log.info("Terminating connectivity poller")
        connectivity_poller.terminate()
    config.save()
    profile_manager.save_launcher_profiles()
    profile_manager.save_launcher_meta()
    if account_man.has_accounts:
        account_man.save_accounts()


def main():
    global clean_exit
    if not constants.DEV and "-m" in sys.argv:  # nuitka multithreading fix
        log.info("-m specified, not running App().run()")
        return
    else:
        launchargs.get_args()
        setup_qapp()
        setup_app_id()
    try:
        paths.setup()
    except Exception as err:
        error_box(str(err))
        raise
    try:
        paths.generate_folder_structure()
    except Exception as err:
        error_box(f"Failed to generate folder structure! ({type(err)}: {err})")
        raise
    try:
        logs.setup()
    except Exception as err:
        error_box(str(err))
        raise
    try:
        config.load()
    except Exception as err:
        log.error("Failed to load config file:", exc_info=err)
        error_box("Failed to load config file! Config will be regenerated.")
    app = LauncherApp()
    atexit.register(on_exit)
    code = app.run()
    logging.info("Exiting with code %d", code)
    clean_exit = True
    sys.exit(code)


if __name__ == "__main__":
    main()
