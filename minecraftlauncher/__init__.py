import sys

from PySide6.QtWidgets import QApplication
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .constants import USER_AGENT
from .networking import ResilientSession

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


SESSION = ResilientSession()
SESSION.headers["User-Agent"] = USER_AGENT
SESSION.mount(
    "http",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            retry_after_max=15,
        )
    ),
)
