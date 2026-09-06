import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from launcher import constants

log = logging.getLogger(__name__)


def error_box(
    message: str,
    error_type: type[Exception] | Exception | None = None,
    *,
    fatal: bool = False,
    dev_only: bool = False,
):
    """
    Show an error box.

    If `type` is included, Qt will allow the user to dismiss the box
    permenantly via a checkbox.

    If `fatal` is set to `True`, the application will exit afterwards.

    If `dev_only` is set to `True`, the message box will only be shown if the
    program is running under a python executable and not a frozen executable.
    """
    if dev_only and not constants.DEV:
        log.debug("Not showing error box ('dev_only' is True)")
        return
    log.debug(
        "Showing error dialog... (%s)", "FATAL" if fatal else "not fatal"
    )
    error_win = QMessageBox()
    error_win.setText(message)
    if error_type:
        error_win.setWindowTitle(str(error_type))
    else:
        error_win.setWindowTitle("Error")
    error_win.setStandardButtons(QMessageBox.StandardButton.Ok)
    QApplication.beep()
    error_win.exec()
    log.debug("Error dialog dismissed.")
    if fatal:
        log.info("We had a fatal error, shutting down. Goodbye")
        sys.exit(1)
    return
