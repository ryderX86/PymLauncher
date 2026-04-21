"""
Device code flow window
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import logging
import time
import json

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QClipboard, QPixmap
from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QCheckBox, QWidget, QHBoxLayout,
    QSizePolicy, QApplication)
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtSvg import QtSvg
import requests

from minecraftlauncher import config
from minecraftlauncher.constants import (
    AZURE_CLIENT_ID, MS_DEVICE_CODE_URL, MS_TOKEN_URL, AZURE_SCOPE)
from minecraftlauncher.auth import MicrosoftAccount, LauncherAccount, auth_flow
from minecraftlauncher.front.styles import ACCENT, TEXT_PRIMARY, TEXT_SECONDARY
from minecraftlauncher.front.resources import link_to_qrcode

log = logging.getLogger(__name__)

# DEVICE_CODE_SCOPE = "openid email XboxLive.signin XboxLive.offline_access"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

class DeviceCodePoller(QThread):
    """Poller for MSA token endpoint"""
    token_recieved = Signal(dict)
    error = Signal(str)
    status = Signal(str)
    log = log.getChild("DeviceCodePoller")

    def __init__(self, device_code:str, interval:int=5,
                 expires_in:int=900, parent=None):
        super().__init__(parent)
        self.device_code = device_code
        self.interval = max(interval, 5)
        self.expires_in = expires_in
        self._cancelled = False

    def cancel(self):
        self.log.info("Cancelling operation")
        self._cancelled = True
    
    def run(self):
        deadline = time.time() + self.expires_in

        while time.time() < deadline and not self._cancelled:
            time.sleep(self.interval)
            if self._cancelled:
                self.log.info("Login cancelled. Exiting.")
                return
            
            try:
                resp = requests.post(MS_TOKEN_URL, data={
                    "grant_type": GRANT_TYPE,
                    "client_id": AZURE_CLIENT_ID,
                    "device_code": self.device_code,
                    "scope": AZURE_SCOPE
                })
            except requests.RequestException as exc:
                self.status.emit("Connection error: %s" % str(exc))
                continue

            data = resp.json()

            if "access_token" in data:
                self.token_recieved.emit(data)
                return
            
            error = data.get("error", "")
            match error:
                case "authorization_pending":
                    self.status.emit("Waiting for authorization...")
                case "authorization_declined":
                    self.status.emit("Authorization declined.")
                    log.debug("Login denied by user on MSA page.")
                    self._cancelled = True
                    return
                case "expired_token":
                    self.error.emit("Device code expired. Please try again.")
                    log.debug("Login token expired")
                    self._cancelled = True
                    return
                case "slow_down":
                    self.interval += 5
                    log.warning("MS said to slow down! Interval += 5")
                case _:
                    self.error.emit("Unexpected error: %s\n%s"
                                    % (str(error),
                                       data.get("error_description", "")))
                    log.error("Login error occured: %s" % str(error))
                    if data.get("error_description"):
                        log.error("Details: %s" % data["error_description"])
                    return
        
        if not self._cancelled:
            self.error.emit("Login window timed out.")

class LoginWindow(QDialog):
    """
    Dialog window for the login process.

    On complete, emits `login_complete` with full auth chain result.
    """

    login_complete = Signal(object)
    login_aborted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sign in with Microsoft")
        self.setFixedWidth(420)
        self.setSizeGripEnabled(False)
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.setModal(True)
        self._poller:DeviceCodePoller|None = None
        self._open_browser = config.open_browser_for_login
        self._build_ui()

    def _build_ui(self): # TODO: turn this into a QStackedWidget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.setSpacing(16)

        title = QLabel("Sign in with Microsoft")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: %s"
                            % ACCENT)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.instruction_label = QLabel(
            "Click the button below to start the sign-in process.\n"
            "A code will be generated for you to enter on Microsoft's website."
        )
        self.instruction_label.setStyleSheet("color: %s;" % TEXT_SECONDARY)
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setMinimumWidth(self.width() - 64)
        self.instruction_label.setMaximumWidth(self.width() - 32)
        layout.addWidget(self.instruction_label)
        
        qr_cont_w = QWidget()
        qr_cont = QHBoxLayout(qr_cont_w)
        qr_cont.setContentsMargins(0, 0, 0, 0)
        self.code_qr_w = QLabel()
        self.code_qr_w.setHidden(True)
        qr_cont.addWidget(self.code_qr_w)
        layout.addWidget(qr_cont_w)

        self.code_label = QLabel("")
        self.code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_label.setStyleSheet(
            "font-size: 28px; font-weight: 700; "
            "color: %s; letter-spacing: 4px; padding: 12px;" % ACCENT
        )
        self.code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.code_label)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: %s; font-size: 12px;"
                                        % TEXT_SECONDARY)
        layout.addWidget(self.status_label)

        # so complicated for what
        open_browser_w = QWidget()
        open_browser_l = QHBoxLayout(open_browser_w)
        open_browser_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.open_browser = QCheckBox("Open default browser")
        self.open_browser.checkStateChanged.connect(self._set_open_browser)
        self.open_browser.setChecked(self._open_browser)
        open_browser_l.addWidget(self.open_browser)
        layout.addWidget(open_browser_w)

        self.start_button = QPushButton("Sign in")
        self.start_button.setProperty("accent", True)
        self.start_button.clicked.connect(self._start_device_code)
        layout.addWidget(self.start_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self._cancel)
        layout.addWidget(cancel_button)

    def _start_device_code(self):
        self.start_button.setEnabled(False)
        self.open_browser.setHidden(True)
        self.status_label.setText("Requesting device code...")

        try:
            resp = requests.post(MS_DEVICE_CODE_URL, data={
                "client_id": AZURE_CLIENT_ID,
                "scope": AZURE_SCOPE,
                "response_type": "device_code"
            }, timeout=15)
        except requests.RequestException as err:
            log.error("Device code request raised an exception:", exc_info=err)
            self.status_label.setText("An unexpected %s error occured."
                                      % type(err).__name__)
            self.start_button.setEnabled(True)
            self.open_browser.setHidden(False)
            return
        
        if resp.status_code < 200 and resp.status_code > 299:
            err = resp.json() if resp.text else {}
            desc = err.get("error_description",
                           err.get("error", resp.text[:50]))
            log.error("Device code request failed: %d\n%s"
                      % (resp.status_code, resp.text))
            self.status_label.setText("HTTP %d" % resp.status_code)
            self.start_button.setEnabled(True)
            self.open_browser.setHidden(False)
            return
        
        data = resp.json()
        user_code = data.get("user_code", "")
        verification_uri = data.get("verification_uri", "")
        device_code = data.get("device_code", "")
        interval = data.get("interval", 5)
        expires_in = data.get("expires_in", 900)
        error = data.get("error")
        error_desc = data.get("error_description")
        error_uri = data.get("error_uri")

        display_uri = verification_uri

        if verification_uri == "https://www.microsoft.com/link":
            verification_uri = ''.join([
                verification_uri, "?otc=%s" % user_code])
            
        qr = link_to_qrcode(verification_uri)
        # self.code_qr_w.load(qr)
        self.code_qr_w.setPixmap(qr)
        self.code_qr_w.setFixedSize(qr.size())
        self.setMinimumHeight(self.minimumHeight() + qr.height()) # qt complains a lot
        self.code_qr_w.setHidden(False)

        if error:
            self.status_label.setText(
                f"Failed to start authentication: {error}\n"
                f"Description: {error_desc}\n"
                f"<a href=\"{error_uri}\">More info</a>")
            self.open_browser.setHidden(False)
            self.start_button.setEnabled(True)
            self.code_qr_w.setHidden(True)
            return

        self.code_label.setText(user_code)
        self.instruction_label.setText(
            "Go to <a href=\"%s\">%s</a> or scan the QR code\n "
            "and enter the code above to sign in."
            % (verification_uri, display_uri)
        )
        self.instruction_label.setOpenExternalLinks(True)
        self.status_label.setText("Waiting for sign-in to complete...")

        if display_uri == verification_uri:
            qapp = QApplication.instance()
            if not qapp or not isinstance(qapp, QApplication):
                log.warning("Couldn't get %sQApplication instance!"
                            % ("correct " if qapp else ""))
                return
            clip = qapp.clipboard()
            if clip:
                clip.setText(user_code, clip.Mode.Clipboard)
                log.debug("Verification code should be in clipboard.")
            else:
                log.warning("Couldn't get clipboard!")

        if self._open_browser:
            QDesktopServices.openUrl(QUrl(verification_uri))
            log.debug("Opened URL in default browser.")

        log.debug("Starting up poller")
        self._poller = DeviceCodePoller(device_code, interval, expires_in)
        self._poller.token_recieved.connect(self._on_token)
        self._poller.error.connect(self._on_error)
        self._poller.status.connect(
            lambda msg: self.status_label.setText(msg)
        )
        self._poller.start()

    def _on_token(self, token_data:dict):
        self.status_label.setText("Authenticating with Xbox Live...")

        msa = MicrosoftAccount(token_data)
        lp = auth_flow(msa)
        if not lp:
            log.error("Auth chain failed! Details:\n%s" % str(lp))
            self.status_label.setText("Authentication failed")
            self.start_button.setEnabled(True)
            self.open_browser.setHidden(False)
            return
        try:
            lp.minecraft_auth()
            lp.get_profile_info()
        except Exception as err:
            log.error("Auth chain failed!", exc_info=err)
            self.status_label.setText(f"Auth failed: {err}")
            self.start_button.setEnabled(True)
            self.open_browser.setHidden(False)
        else:
            self.status_label.setText("Logged in successfully.")
            log.info("Logged in as %s" % lp.gamertag)
            self.login_complete.emit(lp)
            self.accept()
            self.start_button.setEnabled(True)
            self.open_browser.setHidden(False)
            self.code_qr_w.setHidden(True)

    def _on_error(self, message:str):
        log.error("Login error: %s" % message)
        self.status_label.setText(message)
        self.start_button.setEnabled(True)
        self.open_browser.setHidden(False)
        self.code_qr_w.setHidden(True)

    def _cancel(self):
        if self._poller:
            self._poller.cancel()
        self.reject()
    
    def closeEvent(self, a0):
        if self._poller:
            self._poller.cancel()
        super().closeEvent(a0)

    def _set_open_browser(self, a0:Qt.CheckState):
        checked = self.open_browser.isChecked()
        self._open_browser = config.open_browser_for_login = checked