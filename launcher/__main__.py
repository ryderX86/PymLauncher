from json import JSONDecodeError
from typing import NoReturn
import atexit
import logging
import sys
import warnings

from PySide6.QtCore import QEventLoop, QFile, QTimer
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
    profile_manager,
)
from .back.account_manager import account_man
from .config import config
from .exceptions import EncryptedDataDecodeError
from .exceptions.encryption import EncryptionUnavailableWarning
from .front.event_filters import FocusEventFilter
from .front.styles import STYLESHEET, FontList, gen_palette, get_fonts
from .front.window.game_error import ErrorDisplay
from .front.window.loading_blocker import LoadingBlockerWindow
from .front.window.login import LoginWindow
from .front.window.main.main_window import MainWindow
from .front.window.warning import ButtonConfig, WarningDialog, WarningType
from .functions import detect_set_clipboard, uisleep
from .functions.error_box import error_box
from .launchargs import launchargs
from .offline import connectivity_poller, offline_man
from .ostools.win32 import setup_app_id
from .paths import paths
from .threads.bootstrap import (
    AccountManagerBootstrap,
    BaseBootstrapThread,
    JavaManifestBootstrap,
    LaunchProfileBootstrap,
    VersionManifestBootstrap,
)
from .threads.install_worker import InstallWorker
from .threads.launch_worker import LaunchWorker

log = logging.getLogger("launcher")

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

    # Trackers for threads
    bootstrap_threads: list[BaseBootstrapThread]
    java_mf_loaded: bool
    version_mf_loaded: bool

    event_loop_running: bool

    def __init__(self):
        # set default values first so we can check them
        self.event_loop_running = False
        self.login_dialog = None
        self.java_mf_loaded = False
        self.version_mf_loaded = False
        self.bootstrap_threads = []
        self.close_if_login_aborted = True

        self.qapp = get_qapp()
        self.fonts = get_fonts()
        detect_set_clipboard()
        self.qapp.setApplicationName("PymLauncher")
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
        # just in case it doesn't fully run the rest of main():
        self.qapp.aboutToQuit.connect(self._set_clean_exit)

        # anything that potentially can be made outside of the main thread
        # should probably be checked here before any of the base UI is
        # constructed
        if account_man.signals.thread() != self.qapp.thread():
            log.warning(
                "Account manager lives on an incorrect thread, "
                "attempting to mediate this before UI creation."
            )
            account_man.signals = account_man._Signals()

        self.main_window = MainWindow()
        self.main_window.login_requested.connect(self.show_login)
        self.main_window.account_page.logout_requested.connect(self.logout)
        self.main_window.home_page.play_requested.connect(self.play)

        account_man.signals.account_changed.connect(self._on_account_changed)

        self.main_window.home_page.game_crash.connect(self.show_crash_dialog)

    def _set_clean_exit(self):
        global clean_exit
        clean_exit = True

    def buildall(self):
        for page in self.main_window.page_list:
            page.build()

    def _on_bootstrap_error(
        self, thread: BaseBootstrapThread, err: Exception, can_continue: bool
    ):
        match thread:
            case AccountManagerBootstrap():
                return self._auth_thread_error(thread, err, can_continue)
            case LaunchProfileBootstrap():
                return self._profile_thread_error(thread, err, can_continue)
        log.warning(
            "Recieved Exception object from %s thread", type(thread).__name__
        )
        if not can_continue and not thread.wait_after_error:
            log.warning("Cannot continue, notifying user and shutting down.")
            log.debug("Stopping other bootstrap threads...")
            for t in self.bootstrap_threads:
                t.requestInterruption()
            error_box(
                "An unexpected error occured while loading the launcher:\n"
                f"{type(err).__name__}: {err!r}\n"
                "Additional info:\n"
                f"{'\n'.join((str(a) for a in err.args))}"
            )
            self.exit(1)

    def _auth_thread_error(
        self, thread: BaseBootstrapThread, err: Exception, can_continue: bool
    ):
        match err:
            case PermissionError():
                error_box(
                    "Failed to read accounts from storage.\n"
                    "The launcher cannot continue loading and will close.\n"
                    "Please make sure you are using the right account with the "
                    "necessary permissions.\n"
                    f"Error type: {type(err).__name__}"
                )
                self.exit(1)
            case AttributeError():
                log.error("AttributeError in account loading:", exc_info=err)
                if err.obj is not None:
                    log.debug(
                        "Object type at fault: %r", type(err.obj).__name__
                    )
                else:
                    log.debug("Can't retrieve object type from exception")
                if err.name is not None:
                    log.debug("Missing key: %r", err.name)
                else:
                    log.debug("Can't retrieve key name from exception")
                error_box(str(err))
                self.exit(1)
            case JSONDecodeError() | EncryptedDataDecodeError():
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
                    return thread.run()
                else:
                    self.exit(0)

    def _profile_thread_error(
        self, thread: BaseBootstrapThread, err: Exception, can_continue: bool
    ):
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
            self._cancel_bootstrap()
            self.exit()

    def _cancel_bootstrap(self):
        for thread in self.bootstrap_threads:
            thread.requestInterruption()

    def _wait_on_threads_loop(self, loop: QEventLoop, timer: QTimer):
        if all(a.isFinished() for a in self.bootstrap_threads):
            loop.quit()
            timer.stop()
            self.bootstrap_threads = []
            return
        match len(self.bootstrap_threads):
            case 1:
                self.lb_window.set_text(self.bootstrap_threads[0].ui_msg)
            case _:
                self.lb_window.set_text(  # final "..." appended automatically
                    "...\n".join([a.ui_msg for a in self.bootstrap_threads])
                )

    def _on_thread_finished(self, thread: BaseBootstrapThread):
        idx = self.bootstrap_threads.index(thread)
        self.bootstrap_threads.pop(idx)
        thread.deleteLater()
        return

    def _on_accounts_loaded(self):
        if account_man.has_accounts:
            self.close_if_login_aborted = False
        else:
            self.close_if_login_aborted = True

    def bootstrap(self):
        # initialize QThreads
        java_mf_loader = JavaManifestBootstrap()
        version_mf_loader = VersionManifestBootstrap()
        account_loader = AccountManagerBootstrap()
        profile_loader = LaunchProfileBootstrap(version_mf_loader)
        self.bootstrap_threads.append(java_mf_loader)
        self.bootstrap_threads.append(version_mf_loader)
        self.bootstrap_threads.append(account_loader)
        self.bootstrap_threads.append(profile_loader)

        # setup thread signals
        for thread in self.bootstrap_threads:
            thread.error.connect(self._on_bootstrap_error)
        account_loader.finished.connect(self._on_accounts_loaded)

        loop = QEventLoop(self.lb_window)

        # start threads
        version_mf_loader.start()
        java_mf_loader.start()
        account_loader.start()

        loop_timer = QTimer(singleShot=False, interval=25)
        loop_timer.timeout.connect(
            lambda: self._wait_on_threads_loop(loop, loop_timer)
        )
        log.debug("Starting event loop")
        with self.lb_window.shown("Loading..."):
            loop_timer.start()
            loop.exec()
        with self.lb_window.shown("Polishing UI"):
            self.buildall()
        with self.lb_window.shown("Waiting on login"):
            if self.login_dialog and self.login_dialog.isVisible():
                loop = QEventLoop(self.qapp)
                self.login_dialog.finished.connect(loop.quit)
                loop.exec(QEventLoop.ProcessEventsFlag.AllEvents)

        log.info("Finished loading. Showing main window")
        self.main_window.show()
        # self.lb_window.setParent(self.main_window)
        focused = QApplication.focusWidget()
        if focused:
            focused.clearFocus()
        self.main_window.check_for_launch_arg()

    def run(self) -> int:
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            with self.lb_window.shown():
                try:
                    self.bootstrap()
                except EncryptionUnavailableWarning as err:
                    WarningDialog(
                        err.args[0],
                        WarningType.ACCOUNTS_BIN_ENCRYPTION,
                        parent=self.lb_window,
                    )
                except UserWarning as err:
                    WarningDialog(
                        "\n".join((str(a) for a in err.args)),
                        parent=self.lb_window,
                    )
                except Exception as err:
                    log.error(
                        "Error occured in bootstrap process:", exc_info=err
                    )
                    error_box(
                        f"Error occured in bootstrap: {err}\n"
                        "Startup cannot continue"
                    )
                    raise
        self.event_loop_running = True
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
                "necessary permissions.\n"
                f"Error type: {type(err).__name__}"
            )
            self.exit(1)
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
            error_box(str(err))
            self.exit(1)
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
                self.exit()
        except BaseAuthenticationException as err:
            if len(account_man) > 1:
                self.close_if_login_aborted = False
            else:
                self.close_if_login_aborted = True
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
                    self.exit()
        except Exception as err:
            log.error("Unexpected error in account loading:", exc_info=err)
            error_box(
                "Failed to read accounts from storage.\n"
                "The launcher cannot continue loading and will now close."
            )
            self.exit()
        if account_man.has_accounts:
            self.close_if_login_aborted = False
        else:
            self.close_if_login_aborted = True
            self.show_login()
        self._refresh_account_ui()

    def show_login(
        self, *, reason: str | None = None, automatic: bool = False
    ):
        with self.lb_window.hidden():
            if offline_man.offline and not automatic:
                error_box(
                    "Cannot log in while offline! Please wait and try again."
                )
                return self._on_login_abort()
            elif offline_man.offline:  # TODO: confirm this works
                if len(account_man) > 1:
                    account_man.auto_set_active()
                    return
            self.login_dialog = LoginWindow(self.main_window, reason=reason)
            self.login_dialog.login_complete.connect(self._on_login_complete)
            self.login_dialog.rejected.connect(self._on_login_abort)
            self.login_dialog.open()
        return

    def _on_login_abort(self):
        global clean_exit
        active_acc = account_man.active
        while self.login_dialog and self.login_dialog.isVisible():
            self.qapp.processEvents()
        if not active_acc or (
            not offline_man.offline and not active_acc.token_valid
        ):
            active_acc = account_man.auto_set_active(ignore_refreshes=True)
        else:
            self.main_window.account_dropdown.refresh()
        if self.close_if_login_aborted or not active_acc:
            clean_exit = True
            self.exit()
        return

    def show_crash_dialog(self, exit_code: str, stderr: str):
        log.debug("Showing crash dialog to user")
        dialog = ErrorDisplay(self.main_window, exit_code, stderr)
        dialog.open()
        return

    def _on_login_complete(self, account: LauncherAccount):
        if account:
            self.close_if_login_aborted = False
        with self.lb_window.shown("Loading account details..."):
            account_man.replace_into(account)
            account_man.set_active(account.xuid)
            self._refresh_account_ui()
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
        active = account_man.active
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
                self.show_login(reason=str(err))
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
        self.install_worker.error.connect(self._on_install_error)
        self.install_worker.start()

    def _on_account_changed(
        self, acc: LauncherAccount, *, current_retries: int = 0
    ) -> None:
        MAX_RETRIES = 5
        if (
            not acc.token or not acc.token.is_active
        ) and not offline_man.offline:
            if not current_retries:
                text = "Reauthenticating"
            else:
                text = (
                    "Server unavailable, waiting to try again... "
                    f"(attempt {current_retries+1} of {MAX_RETRIES+1})"
                )
            with self.lb_window.shown(text):
                try:
                    acc.refresh()
                except NoConnectionError:
                    pass  # handled elsewhere already
                except MSAServerUnavailableError:
                    offline_man.offline = True
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
                        return
                except (
                    BaseAuthenticationException
                ) as err:  # should only ever be a 402 by this point
                    log.warning(
                        "Failed to refresh %r: %r. Prompting user to relog.",
                        acc.gamertag,
                        type(err).__name__,
                    )
                    self.show_login(reason=str(err))
                    return
                except Exception as err:
                    log.error(
                        "Unexpected exception occured while authenticating",
                        exc_info=err,
                    )
                    self.show_login(
                        reason="Unexpected error occured during "
                        "reauthentication"
                    )
                else:
                    account_man.replace_into(acc)
        self._refresh_account_ui()
        return

    def _refresh_account_ui(self):
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
                self.show_login(reason=str(err))
                if not active_account.token_valid:
                    self.main_window.account_dropdown.next_account()
                    return
            else:
                account_man.replace_into(active_account)
        self.main_window.account_dropdown.refresh()

    def _on_install_error(self, err: Exception):
        log.debug("Notifying user of error in game launch process")
        error_box(str(err))

    def _close_event(self):
        self.exit()

    def exit(self, return_code: int = 0) -> NoReturn:
        global clean_exit
        if return_code == 0:
            clean_exit = True
        if self.event_loop_running:
            self.qapp.exit(return_code)
            raise SystemExit()
        else:
            sys.exit(return_code)


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
    if constants.FLAG_ENABLE_WEBVIEW:
        # pylint: disable-next=import-outside-toplevel
        from PySide6.QtWebView import QtWebView

        QtWebView.initialize()
    setup_qapp()
    app = LauncherApp()
    atexit.register(on_exit)
    code = app.run()
    logging.info("Exiting with code %d", code)
    clean_exit = True
    sys.exit(code)


if __name__ == "__main__":
    main()
