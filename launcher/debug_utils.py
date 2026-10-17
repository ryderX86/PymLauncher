from textwrap import dedent
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile

from PySide6.QtCore import QThread, QThreadPool, Slot, qVersion

from launcher import constants, lifecycle, paths
from launcher.back.account_manager import account_man
from launcher.front.window.text_popup import TextPopup
from launcher.functions.text import indent
from launcher.offline import offline_man

log = logging.getLogger(__name__)


class AccountPreviewThread(QThread):
    p: subprocess.Popen

    def run(self):
        try:
            self._preview_accounts_file()
        except:
            try:
                os.unlink(self.file_name)
            except:
                log.error(
                    "Failed to delete %r, delete this manually.",
                    self.file_name,
                )
        self.deleteLater()

    def _preview_accounts_file(self):
        accounts_list = json.dumps(account_man.dump(), indent=4)
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".json", mode="w"
        ) as file:
            self.file_name = file.name
            log.debug("Created temporary file at %r", self.file_name)
            file.write(accounts_list)
        log.debug("Trying to open file...")
        match constants.OS:
            case "windows":
                self.p = subprocess.Popen(
                    args=("cmd", "/c", "start", "/wait", "", self.file_name)
                )
            case "osx":
                self.p = subprocess.Popen(args=("open", "-W", self.file_name))
            case _:
                self.p = subprocess.Popen(args=("xdg-open", self.file_name))
        if constants.OS in {"windows", "osx"}:
            lifecycle.shutting_down.connect(self._on_closing)
            log.debug("Waiting for process to close.")
            self.p.wait(120)
        else:
            log.debug("Sleeping 1 second to let the file open")
            self.sleep(1)
        log.debug("Deleting file")
        os.unlink(self.file_name)

    @Slot()
    def _on_closing(self):
        if self.p.poll() is None:
            os.unlink(self.file_name)
        self.terminate()


def preview_accounts_file():
    thread = AccountPreviewThread(parent=lifecycle)
    thread.start()


def system_info():
    # pylint: disable=protected-access
    os_info = platform.uname()
    thread_pool = QThreadPool.globalInstance()
    flags = {}
    for entry in dir(sys.flags):
        if entry.startswith("_"):
            continue
        result = getattr(sys.flags, entry, None)
        if isinstance(result, (int, str)):
            flags[entry] = result
    text = dedent(f"""
    System info:
        CPU type: {os_info.machine}
        CPU thread count: {os.cpu_count()}
        Usable CPU threads: {os.process_cpu_count()}
        OS: {os_info.system} {os_info.version}
        Computer name: {os_info.node}
    Process info:
        PID: {os.getpid()}
        CWD: {os.getcwd()}
        Executable: {sys.executable}
        Python flags:\n{
            "\n".join(
                indent(": ".join((k, str(v))), 12)
                for k, v in flags.items()
            )
        }
        GIL enabled: {sys._is_gil_enabled()}
    Launcher info:
        Offline: {"Yes" if offline_man.offline else "No"}
        .minecraft directory: {paths.game}
        Launcher data directory: {paths.data}
        Accounts cache filename: {paths.accounts_file}
    Qt Info:
        Qt version: {qVersion()}
        Ideal thread count: {QThread.idealThreadCount()}
        QThreadPool count: {thread_pool.maxThreadCount()}
        Active threads: {thread_pool.activeThreadCount()}
    """).strip()

    TextPopup(text, "Debug Info", "Debug Info")


def force_account_refresh():
    if account_man.active:
        account_man.active.refresh()
