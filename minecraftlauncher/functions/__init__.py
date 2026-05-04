from collections.abc import Buffer
from xml.etree import ElementTree
from pathlib import Path
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


def reswrite(path: str | Path, content: str | Buffer):
    if isinstance(content, str):
        content = content.encode("utf-8")
    if isinstance(path, str):
        path = Path(path)
    if not path.parent.exists():
        raise FileNotFoundError(
            f"File '{path.name}' parent at '{path.parent}' doesn't exist"
        )

    tmp = path.parent / ".".join([path.name, "tmp"])
    try:
        tmp.write_bytes(content)
    except Exception as err:
        log.error(
            "Exception occured while writing to '%s':", path, exc_info=err
        )
    if path.exists():
        path.unlink()
    tmp.rename(path)
    return True
