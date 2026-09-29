__all__ = [
    "paths",
    "config",
    "launchargs",
    "set_exiting",
    "get_exit_status",
    "setup_qapp",
    "get_qapp",
    "lifecycle",
    "JarRedownloadBehavior",
    "PostLaunchBehavior",
]

import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

# re-exports
from ._launchargs import launchargs  # isort: skip
from ._config import (  # isort: skip
    JarRedownloadBehavior,
    PostLaunchBehavior,
    config,
)
from ._paths import paths  # isort: skip

# setting it here allows me to not fool around with detecting when it's created
# or spam the functions to get it
_qapp: QApplication | None = None

_exit_status: bool = False


def set_exiting():
    global _exit_status
    _exit_status = True


def get_exit_status():
    """
    Check if the application is exiting or not.
    """
    return _exit_status


def setup_qapp():
    global _qapp
    _qapp = QApplication(sys.argv)
    return _qapp


def get_qapp() -> QApplication:
    if not _qapp:
        raise RuntimeError("get_qapp() called before setup_qapp()")
    return _qapp


class _Lifecycle(QObject):
    bootstrap_done = Signal()
    shutting_down = Signal()


lifecycle = _Lifecycle()
