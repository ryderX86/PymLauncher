from pathlib import Path
import logging
import sys
import os
import urllib3

from PySide6.QtCore import (qInstallMessageHandler, Qt, QMessageLogger,
                            QtMsgType, QMessageLogContext)
from PySide6.QtWidgets import QApplication

# pyinstaller uses sys.frozen to indicate if we're running compiled or not,
# doesn't exist in python normally
DEV = bool(getattr(sys, 'frozen', False) == False)

# pyinstaller workaround for windows, since logging uses stdout at times:
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# logging setup AFTER stdout/stderr workaround, just in case.
# TODO: log files
class _LoggingFormatter(logging.Formatter):
    def format(self, record:logging.LogRecord):
        record.name = record.name.replace("minecraftlauncher.", "")
        return super().format(record)
root_logger = logging.getLogger()
if DEV:
    logging.basicConfig(level=logging.DEBUG)
    root_logger.handlers[0].setFormatter(_LoggingFormatter(
        "[%(levelname)s] %(name)s: %(message)s"
    ))
    logging.info("Not running frozen, dev mode active")
    _urllib_logger = logging.getLogger("urllib3")
    _urllib_logger.setLevel(logging.CRITICAL)

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