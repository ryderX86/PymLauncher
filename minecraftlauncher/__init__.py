from logging.handlers import RotatingFileHandler
from collections.abc import Callable
from types import TracebackType
import logging
import ctypes
import sys
import os

from PySide6.QtCore import (
    qInstallMessageHandler,
    QtMsgType,
    QMessageLogContext,
)
from PySide6.QtWidgets import QApplication
import requests

from .constants import (
    DEV,
    USER_AGENT,
    DEBUG_LOGGING,
    OS,
    APP_SLUG,
    LAUNCHER_DATA_DIR,
)

if not DEV:
    match OS:
        case "windows":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                APP_SLUG
            )

if DEBUG_LOGGING:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)


class _LoggingFormatter(logging.Formatter):
    default_msec_format = "%s.%03d"
    default_time_format = "%H:%M:%S"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format_colors(self, record: logging.LogRecord):
        line = super().format(record)
        match record.levelno:
            case logging.DEBUG:
                color = "90"
            case logging.INFO:
                color = "97"
            case logging.WARNING:
                color = "33"
            case logging.ERROR:
                color = "91"
            case logging.CRITICAL:
                color = "31"
            case _:
                color = "96"
        return f"\033[{color}m{line}\033[0m"

    if DEV:
        format = format_colors


root_logger = logging.getLogger()
if DEBUG_LOGGING:
    FORMATTER = _LoggingFormatter(
        "{thread:5} {asctime:12} {levelname:>7}  {name}[{lineno}]: {message}",
        style="{",
    )
else:
    FORMATTER = _LoggingFormatter(
        "{asctime:12} [{levelname}] {name}: {message}", style="{"
    )
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

root_logger.handlers[0].setFormatter(FORMATTER)

_Q_LOGGER = logging.getLogger("Qt")
_Q_LOGGER.setLevel(logging.DEBUG if DEBUG_LOGGING else logging.INFO)


def _qt_logger(type_: QtMsgType, context: QMessageLogContext, msg: str):
    match type_:
        case QtMsgType.QtDebugMsg:
            func = _Q_LOGGER.debug
        case QtMsgType.QtWarningMsg:
            func = _Q_LOGGER.warning
        case QtMsgType.QtInfoMsg:
            func = _Q_LOGGER.info
        case QtMsgType.QtCriticalMsg | QtMsgType.QtFatalMsg:
            func = _Q_LOGGER.critical
        case QtMsgType.QtSystemMsg:
            func = _Q_LOGGER.info
        case _:
            func = _Q_LOGGER.debug

    func(msg)


qInstallMessageHandler(_qt_logger)

if not DEV:
    log_dir = os.path.join(LAUNCHER_DATA_DIR, "logs")
    log_file = os.path.join(log_dir, "latest.log")
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logging.info("Running frozen, we're compiled")
    fh = RotatingFileHandler(log_file, backupCount=4, maxBytes=1000**3)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(FORMATTER)
    if os.path.isfile(log_file):
        fh.doRollover()
    root_logger = logging.getLogger()
    root_logger.addHandler(fh)
    del root_logger

    def except_hook(type_: type, err: BaseException, traceback: TracebackType):
        logging.critical("Uncaught %s:", type_.__name__, exc_info=err)
        return sys.__excepthook__(type_, err, traceback)

    sys.excepthook = except_hook

# setting it here allows me to not fool around with detecting when it's created
# or spam the functions to get it
QAPP = QApplication(sys.argv)

session = requests.sessions.Session()
session.headers["User-Agent"] = USER_AGENT
logging.debug("User agent: %s", USER_AGENT)

offline_mode = False
"""
Used to stop internet-requiring functions before they execute
"""

offline_mode_hooks: list[Callable[[bool], None]] = []

logging_set_up: bool = False


def add_offline_mode_hook(hook: Callable[[bool], None]):
    """
    Adds a function that handles offline mode changing for that module.

    `hook` should be a function that takes a `bool`.

    If `True` is passed, we're in offline mode.

    Otherwise, we're back online.
    """
    offline_mode_hooks.append(hook)


def set_offline_mode(offline: bool):
    """
    Set the `offline_mode` variable and fire off all the offline mode hooks.
    """
    global offline_mode
    offline_mode = offline
    logging.debug("Setting offline mode %s", "on" if offline_mode else "off")
    for func in offline_mode_hooks:
        func(offline_mode)


logging.info("Starting up")
