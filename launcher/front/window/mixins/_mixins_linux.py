from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QDialog,
    QMessageBox,
)

from ._mixins_base import BaseWindowMixin


class WindowMixins(BaseWindowMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Find the QMainWindow and assign that as our parent, so any modality
        # is directed towards the parent window, instead of towards air?
        # Probably a KDE-only fix
        if isinstance(self, (QDialog, QMessageBox)):
            for w in QApplication.topLevelWidgets():
                if isinstance(w, QMainWindow):
                    self.setParent(w)
            if self._use_appmodal_:
                self.setWindowModality(Qt.WindowModality.ApplicationModal)
