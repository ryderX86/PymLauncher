__all__ = [
    "paths",
    "config",
    "launchargs",
    "set_exiting",
    "get_exit_status",
    "lifecycle",
    "JarRedownloadBehavior",
    "PostLaunchBehavior",
]

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QApplication

from .front import _resources_bundled  # pylint: disable=W0611

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


class _Lifecycle(QObject):
    bootstrap_done = Signal()
    shutting_down = Signal()
    config_updated = Signal()

    bootstrap_already_run: bool
    _qapp: QApplication

    def __init__(self):
        super().__init__()
        self.bootstrap_already_run = False
        self.bootstrap_done.connect(self._on_bootstrap)

    @Slot()
    def _on_bootstrap(self):
        self.bootstrap_already_run = True

    @property
    def qapp(self):
        try:
            return self._qapp
        except AttributeError as err:
            raise RuntimeError(
                "Tried to retrieve QApplication before it was set"
            ) from err

    @qapp.setter
    def qapp(self, app: QApplication):
        self._qapp = app


lifecycle = _Lifecycle()
