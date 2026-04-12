import logging
import time
import json

from PySide6.QtCore import Qt, QThread, QUrl, Signal, QCoreApplication
from PySide6.QtGui import QDesktopServices, QClipboard, QPainter
from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QWidget, QMainWindow
)
from PySide6.QtSvgWidgets import QSvgWidget

from minecraftlauncher.front.resources import animation

_FLAGS = Qt.WindowType.SplashScreen

log = logging.getLogger(__name__)

class LoadingBlockerWindow(QDialog):
    def __init__(self, parent=None, flags=_FLAGS):
        super().__init__(parent, flags)
        self.setMinimumSize(500, 360)
        self.setMaximumSize(500, 360)
        self.resize(500, 360)
        self._build_layout()
        if QCoreApplication.instance():
            QCoreApplication.instance().processEvents() # type: ignore
    
    def _build_layout(self):
        _layout = QVBoxLayout(self)
        
        # self.animator = QSvgWidget()
        # self.animator.load(animation("load"))
        # self.animator.renderer().setAnimationEnabled(True) # type: ignore
        # self.animator.renderer().setFramesPerSecond(10) # type: ignore

        # _layout.addWidget(self.animator)

        self.label = QLabel("Loading...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        _layout.addWidget(self.label)
        return
    
    def set_text(self, text:str="Loading..."):
        if not text.endswith("..."):
            text = text + "..."
        self.label.setText(text)
        if QCoreApplication.instance():
            QCoreApplication.instance().processEvents() # type: ignore

    def show(self):
        if QCoreApplication.instance():
            QCoreApplication.instance().processEvents() # type: ignore
        return super().show()

    def hide(self):
        self.set_text()
        super().hide()