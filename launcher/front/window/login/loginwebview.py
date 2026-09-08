from functools import cache
import logging

from PySide6.QtCore import QPluginLoader, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebView import QWebView, QWebViewLoadingInfo
from PySide6.QtWidgets import QDialog, QPushButton, QVBoxLayout

from launcher import constants

log = logging.getLogger(__name__)

match constants.OS:
    case "windows":
        WEBVIEW_PLUGIN_PATH = "webview/qtwebview_webview2"
    case "osx":
        WEBVIEW_PLUGIN_PATH = "webview/libqtwebview_darwin"
    case _:
        WEBVIEW_PLUGIN_PATH = ""  # don't use webview on other platforms


@cache
def is_webview_available():
    if not constants.FLAG_ENABLE_WEBVIEW:
        return False
    webview = QPluginLoader(WEBVIEW_PLUGIN_PATH)
    loaded = webview.load()
    if not loaded:
        log.warning(
            "Failed to load QWebView from %r (QPluginLoader(%r)): %s",
            webview.fileName(),
            WEBVIEW_PLUGIN_PATH,
            webview.errorString(),
        )
    return loaded


class LoginWebViewDialog(QDialog):
    error = Signal(str)

    # instance
    stop: bool

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.stop = False
        self.setMinimumSize(500, 650)
        self.wv = QWebView()
        container = self.createWindowContainer(self.wv)
        container.setContentsMargins(0, 0, 0, 0)
        wf = self.wv.flags() & ~Qt.WindowType.WindowDoesNotAcceptFocus
        self.wv.setFlags(wf)
        lo = QVBoxLayout(self)
        self.setLayout(lo)
        lo.setContentsMargins(0, 0, 0, 0)
        self.open_browser_button = QPushButton("Open in external browser")
        self.open_browser_button.clicked.connect(self._open_browser)
        lo.addWidget(self.open_browser_button, 0)
        lo.addWidget(container, 1)
        self.wv.setHttpUserAgentString(constants.USER_AGENT)
        self.wv.setUrl(url)
        self.wv.loadingChanged.connect(self._on_load_change)
        self._login_url = url
        self.setWindowTitle("Loading...")
        self.wv.titleChanged.connect(self.setWindowTitle)

    def _open_browser(self):
        QDesktopServices.openUrl(self._login_url)
        self.accept()

    def _on_load_change(self, progress: QWebViewLoadingInfo):
        if self.stop:
            return None
        match progress.status():
            case progress.LoadStatus.Failed:
                log.error(
                    "Failed to load page: Qt error string: %r",
                    progress.errorString(),
                )
                self.error.emit(progress.errorString())
            case progress.LoadStatus.Stopped:
                log.warning("URL loading stopped for some reason")
            case progress.LoadStatus.Started:
                log.debug("Started loading %r", self.wv.url().toString())
        return None

    def accept(self) -> None:
        self.stop = True
        return super().accept()
