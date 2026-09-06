from logging.handlers import RotatingFileHandler
from types import TracebackType
import logging
import os
import sys

from PySide6.QtCore import (
    QMessageLogContext,
    QtMsgType,
    qInstallMessageHandler,
)

from launcher import constants
from launcher.launchargs import launchargs
from launcher.paths import paths

ROOT_LOGGER = logging.getLogger()


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

    if constants.DEV:
        format = format_colors


def setup():
    # first checks
    if not paths.ready:
        raise RuntimeError("setup() called before PathFinder object is ready")
    if not launchargs.ready:
        raise RuntimeError("setup() called before CLI args are parsed")

    use_debug_logging = launchargs.debug_logging or constants.DEV

    # formatting:
    if use_debug_logging:
        logging.basicConfig(level=logging.DEBUG)
        FORMATTER = _LoggingFormatter(
            "{thread:5} {asctime:12} {levelname:>7}  {name}[{lineno}]: {message}",
            style="{",
        )
    else:
        logging.basicConfig(level=logging.INFO)
        FORMATTER = _LoggingFormatter(
            "{asctime:12} [{levelname}] {name}: {message}", style="{"
        )
    ROOT_LOGGER.handlers[0].setFormatter(FORMATTER)

    # log files
    if not constants.DEV:
        log_dir = paths.launcher_logs
        log_file = os.path.join(log_dir, "latest.log")

        fh = RotatingFileHandler(log_file, backupCount=4, maxBytes=1000**3)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(FORMATTER)
        if os.path.isfile(log_file):
            fh.doRollover()
        ROOT_LOGGER.addHandler(fh)

        # set up to log final exception if we crash while frozen
        def excepthook(
            type_: type, err: BaseException, traceback: TracebackType
        ):
            logging.critical("Uncaught %r:", type_.__name__, exc_info=err)
            return sys.__excepthook__(type_, err, traceback)

        sys.excepthook = excepthook

    # set urllib3 to critical logs only so it doesn't spam us
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)

    # Qt logging:
    qt_logger = logging.getLogger("Qt")
    qt_logger.setLevel(logging.DEBUG if use_debug_logging else logging.INFO)

    @qInstallMessageHandler
    def log_qt_msg(type_: QtMsgType, context: QMessageLogContext, msg: str):
        match type_:
            case QtMsgType.QtDebugMsg:
                func = qt_logger.debug
            case QtMsgType.QtWarningMsg:
                func = qt_logger.warning
            case QtMsgType.QtInfoMsg:
                func = qt_logger.info
            case QtMsgType.QtCriticalMsg | QtMsgType.QtFatalMsg:
                func = qt_logger.critical
            case QtMsgType.QtSystemMsg:
                func = qt_logger.info
            case _:
                func = qt_logger.info

        func(msg)
