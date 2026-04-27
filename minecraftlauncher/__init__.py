from logging.handlers import MemoryHandler
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
import requests

from .constants import (
    DEV,
    USER_AGENT,
    DEBUG_LOGGING,
    OS,
    AUTHOR_USR,
    LAUNCHER_NAME,
)

if not DEV:
    match OS:
        case "windows":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"{AUTHOR_USR}.{LAUNCHER_NAME}"
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

    if not DEBUG_LOGGING:

        def format(self, record: logging.LogRecord):
            record.name = record.name.replace("minecraftlauncher.", "")
            return super().format(record)


root_logger = logging.getLogger()
MEMORY_HANDLER = MemoryHandler(capacity=1000, flushLevel=logging.DEBUG)
MEMORY_HANDLER.setLevel(logging.DEBUG)
if DEBUG_LOGGING:
    FORMATTER = _LoggingFormatter(
        "%(thread)5d %(asctime)12s %(levelname)7s  %(name)s[%(lineno)s]: "
        "%(message)s"
    )
else:
    FORMATTER = _LoggingFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
root_logger.addHandler(MEMORY_HANDLER)
_urllib_logger = logging.getLogger("urllib3")
_urllib_logger.setLevel(logging.CRITICAL)

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

    def except_hook(type_: type, err: BaseException, traceback: TracebackType):
        logging.critical("Uncaught %s:", type_.__name__, exc_info=err)
        return sys.__excepthook__(type_, err, traceback)

    sys.excepthook = except_hook


session = requests.sessions.Session()
session.headers["User-Agent"] = USER_AGENT
logging.debug("User agent: %s", USER_AGENT)
