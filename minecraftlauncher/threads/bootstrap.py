"""
W.I.P. module containing threads to lose some startup time
"""

import logging

from PySide6.QtCore import QThread, Signal, QObject

from minecraftlauncher.back import (
    version_manager,
    java_manager,
    account_manager,
)


class BootstrapThreadsErrorSignaler(QObject):
    error_occured = Signal(BaseException)


error_signaler = BootstrapThreadsErrorSignaler()


class _BootstrapThread(QThread):
    done = Signal(bool)
    """Finished bootstrap task. Argument is a boolean for success."""

    log: logging.Logger

    def __init__(self):
        super().__init__()
        self.log = logging.getLogger(type(self).__qualname__)


class ManifestFetcherThread(_BootstrapThread):
    def run(self) -> None:
        try:
            version_manager.fetch_version_manifest()
        except Exception as err:
            self.log.error("Failed to fetch version manifest")
            error_signaler.error_occured.emit(err)
            success = False
        else:
            success = True
        self.done.emit(success)
        self.log.debug("Finished")


class JavaManifestFetcherThread(_BootstrapThread):
    def run(self):
        try:
            java_manager.get_jvm_manifest()
        except Exception as err:
            self.log.error("Failed to fetch JVM manifest")
            error_signaler.error_occured.emit(err)
            success = False
        else:
            success = True
        self.done.emit(success)
        self.log.debug("Finished")


class Authenticator(_BootstrapThread):
    accounts_list = Signal(list)

    def run(self):
        try:
            accounts, _ = account_manager.load_accounts()
        except Exception as err:
            self.log.error("Failed to load/refresh accounts")
            error_signaler.error_occured.emit(err)
            success = False
            accounts = []
        else:
            success = True
        self.accounts_list.emit(accounts)
        self.done.emit(success)
        self.log.debug("Finished")
