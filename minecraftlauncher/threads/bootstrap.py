import logging

from PySide6.QtCore import QThread, Signal, QObject

from minecraftlauncher.back import version_manager


class BootstrapThreadsErrorSignaler(QObject):
    error_occured = Signal(BaseException)


error_signaler = BootstrapThreadsErrorSignaler()


class ManifestFetcherThread(QThread):
    finished = Signal(bool)
    """Finished fetching manifest. Argument is a boolean for success"""

    log: logging.Logger

    def __init__(self):
        self.log = logging.getLogger(type(self).__qualname__)

    def run(self) -> None:
        try:
            version_manager.fetch_version_manifest()
        except Exception as err:
            self.log.error("Failed to fetch version manifest")
            error_signaler.error_occured.emit(err)
