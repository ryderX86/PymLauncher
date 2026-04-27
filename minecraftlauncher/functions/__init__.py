from xml.etree import ElementTree
import logging

from PySide6.QtCore import QSize
from PySide6.QtGui import QClipboard, QImage, QPixmap, QIcon
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

_clip: QClipboard | None = None

clipboard_present: bool = False


def _detect_set_clipboard():
    global _clip, clipboard_present
    if bool(_clip):
        return
    qapp = QApplication.instance()
    if not qapp:
        log.warning("Failed to get QCoreApplication instance!")
        clipboard_present = False
        return
    elif not isinstance(qapp, QApplication):
        log.warning(
            "Got QCoreApplication, but it wasn't QApplication! "
            "Aborting clipboard operation."
        )
        clipboard_present = False
        return
    _clip = qapp.clipboard()
    clipboard_present = bool(_clip)


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
