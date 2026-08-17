from collections.abc import Buffer
import logging
import time
import os

from PySide6.QtCore import QSize, QCoreApplication
from PySide6.QtGui import QClipboard, QImage, QPixmap, QIcon
from PySide6.QtWidgets import QApplication

from minecraftlauncher import get_qapp

from .text import indent, is_path_valid, pathsafe_str
from .error_box import error_box

log = logging.getLogger(__name__)

_clip: QClipboard | None = None

clipboard_present: bool = False


def detect_set_clipboard():
    global _clip, clipboard_present
    if _clip:
        return
    _clip = QApplication.clipboard()
    clipboard_present = _clip is not None


def beep():
    QApplication.beep()


def copy_to_clipboard(item: str | int | QPixmap | QIcon | QImage):
    """
    Easier than typing everything out
    """
    if not _clip:
        detect_set_clipboard()
        assert _clip
    if isinstance(item, int):
        item = str(item)

    match item:
        case str():
            _clip.setText(item)
        case QPixmap():
            _clip.setPixmap(item)
        case QIcon():
            size = item.actualSize(QSize(9999, 9999))
            _clip.setPixmap(item.pixmap(size))
        case QImage():
            _clip.setImage(item)
        case _:
            raise TypeError(
                f"Cannot set clipboard with type {type(item).__name__}"
            )

    log.debug("Copied %s to clipboard", type(item).__name__)


def reswrite(path: str | os.PathLike, content: str | Buffer):
    """
    Helper function for saving to a tmp file, then deleting the actual target
    and renaming the tmp file to the target's name.

    For example, `reswrite('C:\\test.txt', ...)` would create
    `C:\\test.txt.tmp`, then delete `C:\\test.txt`, then finally rename
    `C:\\test.txt.tmp` to `C:\\test.txt`.

    This gives the process *some* resiliance to interruptions while writing.

    If any exception occurs while writing, the process is interrupted and the
    original file remains in-tact (along with the new file at the "temporary"
    path), then the exception is raised.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    if not isinstance(path, str):
        path = str(path)
        if not is_path_valid(path):
            raise ValueError(f"Invalid path: {path!r}")
    if not os.path.isdir(os.path.dirname(path)):
        raise FileNotFoundError(
            f"File '{os.path.split(path)}' parent at "
            f"'{os.path.dirname(path)}' doesn't exist"
        )

    tmp = os.path.join(os.path.dirname(path), f"{os.path.split(path)[-1]}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(content)
    except Exception as err:
        log.error(
            "Exception occured while writing to '%s':", path, exc_info=err
        )
        raise err
    else:
        if os.path.isfile(path):
            os.unlink(path)
        os.rename(tmp, path)
        return True


def uisleep(seconds: int | float):
    start = time.time()
    end = start + seconds
    while True:
        QCoreApplication.processEvents()
        if time.time() >= end:
            break
