from json import JSONDecodeError
import os
from types import NoneType
from typing import NoReturn
import atexit
import logging
import sys
import warnings

from PySide6.QtCore import QEventLoop, QFile, Qt, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from launcher.front.icon_helpers import ico_mgr
from launcher.threads.lro_thread import LROThread

from . import (
    config,
    constants,
    launchargs,
    lifecycle,
    logs,
    paths,
)
from .auth import LauncherAccount
from .auth.exceptions import (
    BaseAuthenticationException,
    MSAServerUnavailableError,
    NoConnectionError,
    UnauthorizedError,
)
from .back import (
    profile_manager,
)
from .back.account_manager import account_man
from .back.game_installer import installer
from .exceptions import EncryptedDataDecodeError
from .exceptions.encryption import EncryptionUnavailableWarning
from .front.event_filters import FocusEventFilter
from .front.styles import FontList, get_fonts
from .front.theming import theme_manager
from .front.window.game_error import ErrorDisplay
from .front.window.loading_blocker import LoadingBlockerWindow
from .front.window.login import LoginWindow
from .front.window.main.main_window import MainWindow
from .front.window.warning import ButtonConfig, WarningDialog, WarningType
from .functions import detect_set_clipboard, uisleep
from .functions.error_box import error_box
from .offline import connectivity_poller, offline_man
from .ostools import setup_app_id
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

system_plugin_paths = []

if sys.platform == "linux":
    system_plugin_paths.extend(
        filter(os.path.isdir, ["/usr/lib/qt6/plugins", "/usr/lib/plugins"])
    )
    os.environ["QT_PLUGIN_PATH"] = os.pathsep.join(system_plugin_paths)


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
        if system_plugin_paths:
            log.debug("Added the following plugin paths to Qt:")
            for p in system_plugin_paths:
                log.debug("- %s", p)
        # set default values first so we can check them
        self.event_loop_running = False
        self.login_dialog = None
        self.java_mf_loaded = False
        self.version_mf_loaded = False
        self.bootstrap_threads = []
        self.close_if_login_aborted = True
        self.relog_after_bootstrap = False

        self._loop = QEventLoop()

        self.fonts = get_fonts()
        detect_set_clipboard()
        lifecycle.qapp.setApplicationName(constants.LAUNCHER_NAME)
        # lifecycle.qapp.setStyleSheet(STYLESHEET)
        # lifecycle.qapp.setFont(self.fonts.main)
        # lifecycle.qapp.setPalette(gen_palette())
        lifecycle.qapp.setApplicationVersion(constants.LAUNCHER_VERSION)
        lifecycle.qapp.setApplicationDisplayName(constants.LAUNCHER_NAME)
        ico_mgr.add_search_path(paths.icon_themes)
        ico_mgr.load_themes()
        ico_mgr.set_theme(config.icon_theme)
        theme_manager.load()
        theme_manager.set_theme(config.theme)
        if QFile(":/icon.ico").exists():
            lifecycle.qapp.setWindowIcon(QIcon(":/icon.ico"))
        else:
            log.debug("Couldn't set app icon")
        self._event_filter = FocusEventFilter()
        lifecycle.qapp.installEventFilter(self._event_filter)
        lifecycle.config_updated.connect(self._on_config_update)

        self.lb_window = LoadingBlockerWindow()
        self.lb_window.rejected.connect(self._close_event)
        # just in case it doesn't fully run the rest of main():
        lifecycle.qapp.aboutToQuit.connect(self._set_clean_exit)

        # startdebug
        # anything that potentially can be made outside of the main thread
        # should probably be checked here before any of the base UI is
        # constructed
        if account_man.signals.thread() != lifecycle.qapp.thread():
            log.warning(
                "Account manager signals object lives on an incorrect thread, "
                "attempting to mediate this before UI creation."
            )
            account_man.signals = account_man._Signals()
        # enddebug

        self.main_window = MainWindow()
        self.main_window.login_requested.connect(self.show_login)
        account_man.signals.logout_requested.connect(self.logout)
        self.main_window.home_page.play_requested.connect(self.play)

        account_man.signals.account_changed.connect(self._on_account_changed)

        self.main_window.home_page.game_crash.connect(self.show_crash_dialog)

    @Slot()
    def _on_config_update(self):
        # adjust icon theme
        # adjust theme
        current_name = lifecycle.qapp.style().name()
        new_name = config.theme
        if current_name != new_name:
            theme_manager.set_theme(new_name)
        ico_mgr.set_theme(config.icon_theme)

    @Slot()
    def _set_clean_exit(self):
        global clean_exit
        clean_exit = True

    def buildall(self):
        for page in self.main_window.tab_list.values():
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
        return None

    def _auth_thread_error(
        self, thread: BaseBootstrapThread, err: Exception, can_continue: bool
    ):
        match err:
            case UnauthorizedError():
                self.relog_after_bootstrap = True
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
            case _:
                error_box(
                    "Failed to read accounts from storage.\n"
                    "The launcher cannot continue loading and will close.\n"
                    "Please make sure you are using the right account with the "
                    "necessary permissions.\n"
                    f"Error type: {type(err).__name__}"
                )
                self.exit(1)

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
            self.exit(cleanup_save=False)

    def _cancel_bootstrap(self):
        for thread in self.bootstrap_threads:
            thread.requestInterruption()

    def _check_threads_finished(self):
        if all(a.isFinished() for a in self.bootstrap_threads):
            self._loop.quit()
            self.bootstrap_threads = []
            return
        for i in range(len(self.bootstrap_threads) - 1, -1, -1):
            if self.bootstrap_threads[i].isFinished():
                self.bootstrap_threads.pop(i)
        match len(self.bootstrap_threads):
            case 1:
                self.lb_window.set_text(self.bootstrap_threads[0].ui_msg)

    def _on_accounts_loaded(self):
        if account_man.has_accounts and any(
            a.token_valid for a in account_man
        ):
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
            thread.finished.connect(self._check_threads_finished)
        account_loader.finished.connect(self._on_accounts_loaded)

        # start threads
        version_mf_loader.start()
        java_mf_loader.start()
        account_loader.start()

        log.debug("Waiting for bootstrap w/ event loop")
        with self.lb_window.shown("Loading..."):
            self._loop.exec(QEventLoop.ProcessEventsFlag.AllEvents)
        with self.lb_window.shown("Polishing UI"):
            lifecycle.bootstrap_done.emit()
            self.buildall()
        if (
            (not account_man.has_accounts)
            or (not account_man.active_usable)
            or (self.relog_after_bootstrap)
        ):
            if (not self.login_dialog) or (not self.login_dialog.isVisible()):
                if account_man.has_accounts:
                    reason = "Your session has expired, please log in again."
                else:
                    reason = None
                self.close_if_login_aborted = True
                self.show_login(reason=reason)
            if self.login_dialog and self.login_dialog.isVisible():
                with self.lb_window.hidden():
                    loop = QEventLoop(lifecycle.qapp)
                    self.login_dialog.finished.connect(loop.quit)
                    loop.exec(QEventLoop.ProcessEventsFlag.AllEvents)
            self._refresh_account_ui()

        log.info("Showtime!")
        self.main_window.show()
        # self.lb_window.setParent(self.main_window)
        focused = QApplication.focusWidget()
        if focused:
            focused.clearFocus()
        installer.download_error.connect(
            self._on_install_error, Qt.ConnectionType.QueuedConnection
        )
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
        return lifecycle.qapp.exec()

    @Slot(NoneType, bool)
    @Slot(str, bool)
    def show_login(
        self, *, reason: str | None = None, automatic: bool = False
    ):
        with self.lb_window.hidden():
            if offline_man.offline and not account_man.has_usable_account:
                error_box(
                    "Cannot log in while offline! Please wait and try again."
                )
                return self._on_login_abort()
            elif offline_man.offline:  # TODO: confirm this works
                if account_man.has_usable_account:
                    account_man.auto_set_active()
                    return
            self.login_dialog = LoginWindow(self.main_window, reason=reason)
            self.login_dialog.login_complete.connect(self._on_login_complete)
            self.login_dialog.rejected.connect(self._on_login_abort)
            self.login_dialog.open()
            self.login_dialog.finished.connect(
                lambda _: (
                    (
                        self.login_dialog.deleteLater(),  # type: ignore
                        setattr(self, "login_dialog", None),
                    )
                )
            )
        return

    @Slot()
    def _on_login_abort(self):
        global clean_exit
        active_acc = account_man.active
        while self.login_dialog and self.login_dialog.isVisible():
            lifecycle.qapp.processEvents()
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

    @Slot(str, str)
    def show_crash_dialog(self, exit_code: str, stderr: str):
        log.debug("Showing crash dialog to user")
        dialog = ErrorDisplay(self.main_window, exit_code, stderr)
        dialog.open()
        return

    @Slot(LauncherAccount)
    def _on_login_complete(self, account: LauncherAccount):
        if account:
            self.close_if_login_aborted = False
        with self.lb_window.shown("Loading account details..."):
            account_man.replace_into(account)
            account_man.set_active(account.xuid)
            self._refresh_account_ui()
        return

    @Slot()
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

    @Slot()
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

        self.launch_worker = LaunchWorker(installer, None, self.main_window)
        self.launch_worker.done.connect(
            self.main_window.home_page.on_launch_finished,
            Qt.ConnectionType.UniqueConnection,
        )
        self.launch_worker.game_closed.connect(
            self.main_window.home_page.on_game_closed,
            Qt.ConnectionType.UniqueConnection,
        )
        self.launch_worker.game_log.connect(
            self.main_window.home_page.handle_game_log,
            Qt.ConnectionType.UniqueConnection,
        )
        self.launch_worker.finished.connect(
            self.launch_worker.deleteLater, Qt.ConnectionType.UniqueConnection
        )
        installer.finished.connect(
            self.launch_worker.start_if_success,
            Qt.ConnectionType.UniqueConnection,
        )
        installer.install()

    @Slot(LauncherAccount)
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
                runner = LROThread(
                    lifecycle.qapp,
                    dialog_instance_or_type=self.lb_window,
                    msg=text,
                )
                try:
                    runner.go(acc.refresh)
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

    @Slot(Exception)
    def _on_install_error(self, err: Exception):
        log.debug("Notifying user of error in game launch process")
        error_box(str(err))

    @Slot()
    def _close_event(self):
        self.exit()

    def exit(
        self, return_code: int = 0, cleanup_save: bool = True
    ) -> NoReturn:
        global clean_exit
        if return_code == 0 and cleanup_save:
            clean_exit = True
        else:
            clean_exit = False
        if self.event_loop_running:
            lifecycle.qapp.exit(return_code)
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
    if (
        connectivity_poller
        and connectivity_poller.has_run
        and offline_man.offline
    ):
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
        log.error("Error initializing PathFinder:", exc_info=err)
        error_box(str(err))
        raise
    try:
        paths.generate_folder_structure()
    except Exception as err:
        log.error("Failed to generate folder structure:", exc_info=err)
        error_box(
            "Failed to generate folder structure! "
            f"({type(err).__name__}: {err})"
        )
        raise
    try:
        logs.setup()
    except Exception as err:
        log.error("Failed to set up logging files:", exc_info=err)
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
    lifecycle.qapp = QApplication(sys.argv)
    app = LauncherApp()
    atexit.register(on_exit)
    code = app.run()
    logging.info("Exiting with code %d", code)
    clean_exit = True
    sys.exit(code)


if __name__ == "__main__":
    main()
