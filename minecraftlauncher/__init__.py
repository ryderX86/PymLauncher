from pathlib import Path
from logging.handlers import MemoryHandler
import logging
import sys
import os
import urllib3

from PySide6.QtCore import (qInstallMessageHandler, Qt, QMessageLogger,
                            QtMsgType, QMessageLogContext)
from PySide6.QtWidgets import QApplication
import requests

from .constants import DEV, USER_AGENT, DEBUG_LOGGING

# pyinstaller workaround for windows, since logging uses stdout at times:
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# logging setup AFTER stdout/stderr workaround, just in case.
# TODO: log files
if DEBUG_LOGGING:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)
class _LoggingFormatter(logging.Formatter):
    default_msec_format = '%s.%03d'
    default_time_format = "%H:%M:%S"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def format(self, record:logging.LogRecord):
        record.name = record.name.replace("minecraftlauncher.", "")
        return super().format(record)
root_logger = logging.getLogger()
MEMORY_HANDLER = MemoryHandler(capacity=1000, flushLevel=logging.DEBUG)
MEMORY_HANDLER.setLevel(logging.DEBUG)
if DEV:
    FORMATTER = _LoggingFormatter(
        "%(thread)5d %(asctime)12s %(levelname)7s  %(name)s: %(message)s")
else:
    FORMATTER = _LoggingFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
root_logger.addHandler(MEMORY_HANDLER)
_urllib_logger = logging.getLogger("urllib3")
_urllib_logger.setLevel(logging.CRITICAL)

root_logger.handlers[0].setFormatter(FORMATTER)

_Q_LOGGER = logging.getLogger("Qt")
_Q_LOGGER.setLevel(logging.DEBUG)
def _qt_logger(type:QtMsgType, context:QMessageLogContext, msg:str):
    match type:
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

# stuff so i can access QApplication without the linter throwing a damn tantrum
_qapp:QApplication|None = None

def qapp():
    global _qapp
    if _qapp:
        return _qapp
    else:
        _qapp = QApplication([])
        return _qapp
    
def set_qapp(qapp:QApplication):
    global _qapp
    _qapp = qapp
    
def style():
    global _qapp
    if not _qapp:
        qapp()
        assert _qapp
    style = _qapp.style()
    assert style
    return style

session = requests.sessions.Session()
session.headers["User-Agent"] = USER_AGENT
logging.debug("User agent: %s" % USER_AGENT)