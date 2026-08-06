from time import sleep
import logging
import atexit
import sys

from PySide6.QtCore import QFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QStyleFactory

from . import constants, DEV, config, QAPP, args
from .functions.error_box import error_box
from .front.styles import STYLESHEET, FONT, PALETTE
from .front.window.loading_blocker import LoadingBlockerWindow
from .front.window.main.main_window import MainWindow
from .front.window.login import LoginWindow
from .front.window.game_error import ErrorDisplay
from .back import (
    account_manager,
    download_helpers,
    profile_manager,
    version_manager,
    java_manager,
)
from .auth import LauncherAccount

LOGGER = logging.getLogger("minecraftlauncher")

# we use this to detect crashes somewhat, allowing us to not write garbage data
# or whatever
clean_exit = False


class App:
    """Controller"""

    close_if_login_aborted: bool
    """Should we close if the login process is aborted?"""

    def __init__(self):
        QAPP.setApplicationName("Minecraft Launcher")
        match constants.OS:
            case "windows":
                pass
            case _:
                QAPP.setStyle(QStyleFactory.create("Windows"))
        QAPP.setStyleSheet(STYLESHEET)
        QAPP.setFont(FONT)
        QAPP.setPalette(PALETTE)
        if QFile(":/icon.ico").exists():
            QAPP.setWindowIcon(QIcon(":/icon.ico"))
        else:
            LOGGER.debug("Couldn't set app icon")

        self.lb_window = LoadingBlockerWindow()
        self.lb_window.rejected.connect(self._close_event)
        self.lb_window.show()
        # just in case it doesn't fully run the rest of main():
        QAPP.aboutToQuit.connect(self._set_clean_exit)

        self.main_window = MainWindow()
        self.main_window.login_requested.connect(self.show_login)
        self.main_window.account_page.logout_requested.connect(self.logout)
        self.main_window.home_page.play_requested.connect(self.play)

        self.main_window.account_dropdown.account_changed.connect(
            self._on_account_changed
        )

        self.main_window.destroyed.connect(
            download_helpers.RunnableDownloader.kill_all
        )

        self.main_window.home_page.game_crash.connect(self.show_crash_dialog)

        if DEV:
            if args.debug_splash_screen:
                self.lb_window.set_text("Waiting 5s for splash debugging")
                sleep(5)

    def _set_clean_exit(self):
        global clean_exit
        clean_exit = True

    def buildall(self):
        for page in self.main_window.page_list:
            page.build()

    def run(self) -> int:
        LOGGER.debug("Attempting to get version manifest set up...")
        self.lb_window.set_text("Fetching version list")
        try:
            version_manager.fetch_version_manifest()
            version_manager.get_version_list()
        except Exception as err:
            LOGGER.error("Failed to load version manifest:", exc_info=err)
            LOGGER.info(
                "Not set up yet to handle offline mode, notify user"
                " and exit."
            )
            error_box(
                f"Failed to get version info (error text: {err!r})", fatal=True
            )
            return 1

        LOGGER.debug("Attempting to get JRE manifest...")
        self.lb_window.set_text("Fetching Java version list")
        try:
            java_manager.get_jvm_manifest()
        except Exception as err:
            LOGGER.error("Failed to load JRE manifest:", exc_info=err)
            LOGGER.info(
                "Not set up yet to handle offline mode, notify user"
                " and exit."
            )
            error_box(f"Failed to get JRE manifest: {err}", fatal=True)
            return 2

        self.lb_window.set_text("Loading UI data...")
        self.buildall()
        LOGGER.debug("Attempting to load accounts from cache...")
        self.lb_window.set_text("Authenticating")
        accounts, _ = account_manager.load_accounts()
        if accounts:
            self.close_if_login_aborted = False
        else:
            self.close_if_login_aborted = True
            self.lb_window.hide()
            self.show_login()
        self._refresh_account_ui()

        LOGGER.info("Finished loading. Showing main window")
        self.main_window.show()
        # self.lb_window.setParent(self.main_window)
        self.lb_window.hide()
        self.main_window.check_for_launch_arg()
        return QAPP.exec()

    def show_login(self):
        dialog = LoginWindow(self.main_window)
        dialog.login_complete.connect(self._on_login_complete)
        dialog.rejected.connect(self._on_login_abort)
        dialog.exec()

    def _on_login_abort(self):
        global clean_exit
        active_acc = account_manager.active_account
        if self.close_if_login_aborted or not active_acc:
            clean_exit = True
            sys.exit(1)
        account_manager.set_active_account(active_acc)
        self._refresh_account_ui()

    def show_crash_dialog(self, exit_code: str, stderr: str):
        LOGGER.debug("Showing crash dialog to user")
        dialog = ErrorDisplay(self.main_window, exit_code, stderr)
        dialog.show()
        dialog.exec()

    def _on_login_complete(self, account: LauncherAccount):
        if account:
            self.close_if_login_aborted = False
        self.lb_window.open()
        self.lb_window.set_text("Loading account details")
        self.lb_window.update()
        account_manager.save_or_replace_account(account)
        account_manager.set_active_account(account.xuid)
        self._refresh_account_ui()
        self.lb_window.hide()

    def logout(self):
        active_account = account_manager.active_account
        if active_account:
            account_manager.remove_account(active_account)
        if len(account_manager.accounts) > 0:
            account_manager.active_account = account_manager.accounts[0].xuid
        self._refresh_account_ui()

        if not account_manager.accounts:
            LOGGER.info("No accounts left, showing login window.")
            self.close_if_login_aborted = True
            self.show_login()

    def play(self):
        if not account_manager.active_account:
            error_box("No active account!")
            return
        active = account_manager.fetch_account(account_manager.active_account)
        assert active

        profile = profile_manager.get_current_profile()
        if not profile:
            error_box("No active profile!")
            return

        if not active.profile:
            LOGGER.debug("Can't find account profile, fetching manually...")
            active.get_profile_info()
            assert active.profile

        if not active.token:
            LOGGER.debug("Can't find account (mojang) token, refreshing...")
            active.minecraft_auth()
            assert active.token

        self.main_window.home_page.install_launch_game(
            profile.version_id, profile, active
        )

    def _on_account_changed(self, xuid: str):
        if self.lb_window.isVisible():
            self.lb_window.accept()
        if xuid in {a.xuid for a in account_manager.accounts}:
            account_manager.active_account = xuid
            acc = account_manager.fetch_account(xuid)
            assert acc
            if not acc.token or not acc.token.is_active:
                self.lb_window.set_text("Reauthenticating")
                self.lb_window.open()
                acc_refresh = acc.refresh()
                if acc_refresh:
                    self.lb_window.accept()
                    account_manager.save_or_replace_account(acc)
                else:  # AuthError
                    LOGGER.warning(
                        "Couldn't refresh %s, prompting user to relog. %s",
                        xuid,
                        acc_refresh.err_string(),
                    )
                    dialog = LoginWindow(self.lb_window)
                    dialog.rejected.connect(
                        self.main_window.account_dropdown.next_account
                    )
                    return dialog.exec()
        else:
            LOGGER.warning("Couldn't find the active account in accounts!")
        self._refresh_account_ui()

    def _refresh_account_ui(self):
        self.main_window.account_dropdown.refresh()
        if not account_manager.active_account:
            return
        active_account = account_manager.fetch_account(
            account_manager.active_account
        )
        assert active_account
        if not active_account.token_valid:
            self.lb_window.set_text("Authenticating")
            active_account.minecraft_auth()
            account_manager.save_or_replace_account(active_account)
        self.main_window.account_page.set_account_info(active_account)

    def _close_event(self):
        QAPP.exit(0)


@atexit.register
def on_exit():
    """
    Registered with `atexit` in `main()`.
    """
    if not clean_exit:
        LOGGER.error("Something went very wrong, not doing normal cleanup.")
        return
    LOGGER.info("Cleaning up")
    config.save()
    profile_manager.save_launcher_profiles()
    profile_manager.save_launcher_meta()
    if account_manager.accounts:
        account_manager.save_accounts()


def main():
    global clean_exit
    if "-m" in sys.argv:  # nuitka multithreading fix
        LOGGER.info("-m specified, not running App().run()")
        return
    else:
        args.get_args()
    app = App()
    code = app.run()
    logging.info("Exiting with code %d", code)
    clean_exit = True
    sys.exit(code)


if __name__ == "__main__":
    main()
