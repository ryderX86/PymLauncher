from collections.abc import Buffer
import logging
import os

from PySide6.QtCore import QSize
from PySide6.QtGui import QClipboard, QImage, QPixmap, QIcon

from minecraftlauncher import QAPP, config

from .text import indent, is_path_valid
from .error_box import error_box

log = logging.getLogger(__name__)

_clip: QClipboard | None = None

clipboard_present: bool = False


def _detect_set_clipboard():
    global _clip, clipboard_present
    if bool(_clip):
        return
    _clip = QAPP.clipboard()
    clipboard_present = bool(_clip)


def beep():
    if config.allow_audio:
        QAPP.beep()
        return True
    return False


def copy_to_clipboard(item: str | int | QPixmap | QIcon | QImage):
    """
    Easier than typing everything out
    """
    if not _clip:
        return
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

    log.info("Copied %s to clipboard.", type(item).__name__)


_detect_set_clipboard()


def reswrite(path: str | os.PathLike, content: str | Buffer):
    """
    Helper function for saving to a tmp file, then deleting the actual target
    and renaming the tmp file to the target's name.

    For example, `reswrite('C:\\test.txt', ...)` would create
    `C:\\test.txt.tmp`, then delete `C:\\test.txt`, then finally rename
    `C:\\test.txt.tmp` to `C:\\test.txt`.

    This gives the process *some* resiliance to interruptions while writing.
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
    if os.path.isfile(path):
        os.unlink(path)
    os.rename(tmp, path)
    return True
