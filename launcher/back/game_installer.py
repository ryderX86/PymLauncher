import logging
import os
import time

from PySide6.QtCore import (
    QEventLoop,
    QMutex,
    QObject,
    Qt,
    Signal,
    Slot,
)
from shiboken6 import delete

from launcher import config, constants, lifecycle, paths
from launcher.back import java_manager, profile_manager, version_manager
from launcher.threads.downloader import (
    Download,
    DownloaderThread,
    DownloadQueue,
    GameJarDownloaderThread,
    HashType,
    NativeDownload,
)

log = logging.getLogger(__name__)


class GameInstaller(QObject):
    step = Signal(
        str, str, int
    )  # progress bar message, status bar message, total count
    """>>> emit(bar_message:str, status_bar:str, total:int)"""
    download_error = Signal(Exception)
    """>>> emit(error:Exception)"""
    downloaded_file = Signal(str, int)
    """>>> emit(path:str, size:int)"""
    set_display_bytes = Signal(bool)
    """>>> emit(display_bytes:bool)"""
    update_bytes = Signal(int)
    """>>> emit(byte_count:int)"""
    starting = Signal()
    finished = Signal(bool)
    """>>> emit(success:bool)"""

    _threads: list[DownloaderThread]
    _loop: QEventLoop
    _new_overridden_count: int
    _skipped_count: int
    _error_occured: bool
    _already_handled_error: bool
    _mutex: QMutex
    _interrupted: bool

    def __init__(self):
        super().__init__()
        self._threads = []
        self._new_overridden_count = 0
        self._skipped_count = 0
        self._error_occured = False
        self._already_handled_error = False
        self._mutex = QMutex()
        self._interrupted = False

    def _clear_threads(self):
        for t in self._threads:
            if t.isRunning():
                t.requestInterruption()
                if not t.wait(500):
                    log.warning("Thread not quitting! Terminating")
                    t.terminate()
            # using shiboken here helps to know if there's a problem instantly
            # rather than waiting for the event loop to take control
            delete(t)
        self._threads = []

    @Slot()
    def _handle_downloaded(self):
        self._new_overridden_count += 1

    @Slot()
    def _handle_skipped(self):
        self._skipped_count += 1

    @Slot(Exception)
    def _handle_exception(self, err: Exception):
        self._mutex.lock()
        self._error_occured = True
        for t in self._threads:
            t.requestInterruption()
        if not self._already_handled_error:
            self.download_error.emit(err)
        # set this w/ mutex so we don't spam the error signal
        self._already_handled_error = True
        self._mutex.unlock()

    def prep_threads(self, queue: DownloadQueue | None = None, limit: int = 0):
        self._clear_threads()
        if not limit:
            limit = constants.CPU_THREADS
        for i in range(limit):
            t = DownloaderThread(parent=self)
            t.setObjectName(f"{type(self).__name__}.thread.{i}")
            if queue:
                t.set_queue(queue)
            self._threads.append(t)
            t.exception.connect(self._handle_exception)
            t.downloaded_file.connect(self.downloaded_file.emit)
            t.downloaded_file.connect(self._handle_downloaded)
            t.skipped_file.connect(self.downloaded_file.emit)
            t.skipped_file.connect(self._handle_skipped)

    def set_queue_for_all(self, queue: DownloadQueue | None):
        for t in self._threads:
            t.set_queue(queue)

    @Slot()
    def _check_remaining_threads(self):
        if not self._loop.isRunning():
            return
        if all(t.isFinished() for t in self._threads):
            self._loop.quit()

    def _wait_for_threads(self):
        if not self._threads:
            raise RuntimeError("No threads to run")
        self._skipped_count = 0
        self._new_overridden_count = 0
        for t in self._threads:
            t.finished.connect(
                self._check_remaining_threads,
                Qt.ConnectionType.UniqueConnection,
            )
        self._loop.exec(QEventLoop.ProcessEventsFlag.AllEvents)
        for t in self._threads:  # hack for qthread deletion crashes
            if not t.wait(5):
                log.warning(
                    "Thread %r still running, terminating...", t.objectName()
                )
                t.terminate()

    @Slot()
    def _interrupt(self):
        self._interrupted = True
        for t in self._threads:
            if t.isRunning():
                log.debug("Stopping thread %r", t.objectName())
                t.requestInterruption()
                while not t.wait(150):
                    log.debug("Thread still running!")

    def _start_threads(self):
        for t in self._threads:
            t.start()

    def prep_vars(self):
        self._loop = QEventLoop(self)
        self._already_handled_error = False
        self.profile = profile_manager.get_current_profile()

        if not self.profile.real_version_id:
            raise RuntimeError("Couldn't determine profile's selected version")
        self.version = version_manager.fetch_version(
            self.profile.real_version_id
        )

        assets_stub = self.version.assets_stub
        if self.profile.java_path:
            self.java_index = None
            self.java_bin = self.profile.java_path
        else:
            self.java_index = java_manager.get_jvm_version(
                self.version.java_version
            )
            self.java_bin = self.java_index.executable_path

        if assets_stub.available():
            self.assets = assets_stub.get()
        else:
            self.step.emit("Getting assets index", "Preparing", 1)
            self.assets = assets_stub.download()

    def download_assets(self):
        queue = DownloadQueue()
        self.set_queue_for_all(queue)

        self.step.emit(
            "Downloading assets", "Downloading", len(self.assets.assets)
        )
        queue.begin_append()
        self._start_threads()
        if self.assets.virtual:
            for asset in self.assets:
                if self._error_occured:
                    break
                queue.append(
                    Download(asset.url, asset.path, asset.hash, HashType.SHA1)
                )
        else:
            for asset in self.assets:
                if self._error_occured:
                    break
                queue.append(
                    Download(
                        asset.url,
                        asset.path,
                        asset.hash,
                        HashType.SHA1,
                        virtual=asset.virtual_path,
                    )
                )
        if not self._error_occured:
            # add the log4j configuration as well, nowhere else really good to
            # throw it in and it is stored under assets:
            if lc := self.version.logging:
                queue.append(
                    Download(
                        lc.url,
                        lc.path,
                        lc.sha1,
                        HashType.SHA1,
                    )
                )
        queue.end_append()
        self._wait_for_threads()
        self.set_queue_for_all(None)
        if not (self._interrupted or self._error_occured):
            log.debug(
                "Finished downloading %d/%d assets.",
                self._new_overridden_count,
                self._skipped_count + self._new_overridden_count,
            )
        return

    def download_jre(self):
        if not self.java_index:
            return
        queue = DownloadQueue()
        self.set_queue_for_all(queue)

        queue.begin_append()
        self._start_threads()
        count = len(self.java_index.files)
        self.step.emit(
            f"Downloading Java {self.java_index.version_id}",
            "Downloading",
            count,
        )
        if config.disable_lzma_downloads:
            for file in self.java_index.files:
                if self._error_occured:
                    break
                queue.append(
                    Download(
                        file.raw.url, file.path, file.raw.sha1, HashType.SHA1
                    )
                )
        else:
            for file in self.java_index.files:
                if self._error_occured:
                    break
                if file.lzma:
                    queue.append(
                        Download(
                            file.lzma.url,
                            file.path,
                            file.raw.sha1,
                            HashType.SHA1,
                            lzma=True,
                        )
                    )
                else:
                    queue.append(
                        Download(
                            file.raw.url,
                            file.path,
                            file.raw.sha1,
                            HashType.SHA1,
                        )
                    )
        queue.end_append()
        self._wait_for_threads()
        self.set_queue_for_all(None)
        if not (self._interrupted or self._error_occured):
            log.debug(
                "Finished downloading Java %s. %d/%d new files.",
                self.java_index.version_id,
                self._new_overridden_count,
                count,
            )
        return

    def download_jar(self):
        self._clear_threads()

        self.step.emit(
            f"Downloading {self.version.id}.jar",
            "Downloading",
            self.version.jar_file.size,
        )
        self.set_display_bytes.emit(True)
        dler = GameJarDownloaderThread(self.version.jar_file)
        dler.setObjectName(f"{type(self).__name__}.GameJarDownloaderThread")
        lifecycle.shutting_down.connect(dler.requestInterruption)
        dler.setParent(self)
        dler.progress.connect(self.update_bytes.emit)
        dler.exception.connect(self._handle_exception)
        dler.exception.connect(dler.requestInterruption)
        dler.finished.connect(self._loop.quit)
        dler.start()
        self._loop.exec(QEventLoop.ProcessEventsFlag.AllEvents)
        if not dler.wait(50):
            log.warning("Thread %r still running!", dler.objectName())
            dler.terminate()
        if self._interrupted:
            return
        if dler.was_skipped:
            log.debug("Skipped client JAR download, exists already")
        delete(dler)
        return

    def download_libraries(self):
        queue = DownloadQueue()
        self.set_queue_for_all(queue)

        self.step.emit(
            "Downloading libraries",
            "Downloading",
            len(self.version.libraries),
        )
        queue.begin_append()
        self._start_threads()
        natives_path = os.path.join(
            paths.game, "bin", self.version.inherits_from or self.version.id
        )
        count = 0
        for lib in self.version.iter_libraries():
            if self._error_occured:
                break
            if not lib.url:
                log.debug("Skipping library %r since it has no URL.", lib.name)
                continue
            count += 1
            if lib.is_native and not lib.sha1:
                queue.append(
                    NativeDownload(
                        lib.url,
                        lib.path,
                        natives_path=natives_path or self.version.id,
                        excluded_patterns=(
                            lib.extract_rules.get("exclude", [])
                            if lib.extract_rules
                            else None
                        ),
                    )
                )
            elif lib.is_native:
                queue.append(
                    NativeDownload(
                        url=lib.url,
                        file_path=lib.path,
                        natives_path=natives_path,
                        hash_list=lib.sha1,
                        hash_type=HashType.SHA1,
                        excluded_patterns=(
                            lib.extract_rules.get("exclude", [])
                            if lib.extract_rules
                            else None
                        ),
                    )
                )
            elif lib.sha1:
                queue.append(
                    Download(lib.url, lib.path, lib.sha1, HashType.SHA1)
                )
            else:
                queue.append(Download(lib.url, lib.path))
        queue.end_append()
        self._wait_for_threads()
        if not (self._interrupted or self._error_occured):
            log.debug(
                "Finished downloading %d/%d libraries.",
                self._new_overridden_count,
                count,
            )

    def install(self):
        lifecycle.shutting_down.connect(self._interrupt)
        st = time.perf_counter()
        self.starting.emit()
        log.debug("Prepping variables")
        self.prep_vars()
        self.prep_threads()

        install_functions = []

        if not self.profile.java_path:
            install_functions.append(self.download_jre)
        install_functions.append(self.download_libraries)
        install_functions.append(self.download_assets)
        install_functions.append(self.download_jar)

        for func in install_functions:
            if self._error_occured:
                log.info("Error occured, cleaning threads and stopping.")
                self._clear_threads()
                self.finished.emit(False)
                return
            elif self._interrupted:
                return
            func()

        self._clear_threads()
        ft = time.perf_counter()
        log.debug("Finished in %0.4fs", ft - st)
        if self._error_occured:
            self.finished.emit(False)
            return
        self.finished.emit(True)
        lifecycle.shutting_down.disconnect(self._interrupt)


installer = GameInstaller()
