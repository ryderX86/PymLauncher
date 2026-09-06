"""
Device code flow window
"""

import logging

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import requests

from launcher.auth import MicrosoftAccount, auth_flow
from launcher.auth.exceptions import (
    NoConnectionError,
)
from launcher.config import config
from launcher.constants import (
    AZURE_CLIENT_ID,
    AZURE_SCOPE,
    MS_DEVICE_CODE_URL,
)
from launcher.front.resources import link_to_qrcode
from launcher.front.styles import ACCENT, TEXT_SECONDARY
from launcher.functions import (
    error_box,
)
from launcher.threads.device_code_poller import DeviceCodePoller
from launcher.threads.login_redirect_webserver import (
    LoginRedirectWebserver,
)

log = logging.getLogger(__name__)

# DEVICE_CODE_SCOPE = "openid email XboxLive.signin XboxLive.offline_access"


class LoginWindow(QDialog):
    """
    Dialog window for the login process.

    On complete, emits `login_complete` with full auth chain result.
    """

    login_complete = Signal(object)
    login_aborted = Signal()

    def __init__(self, parent=None, *, reason: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sign in with Microsoft")
        self.setFixedWidth(420)
        self.setSizeGripEnabled(False)
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.setModal(True)
        self._poller: DeviceCodePoller | None = None
        self._thread: LoginRedirectWebserver | None = None
        self._open_browser = config.open_browser_for_login
        self._build_ui()
        if reason:
            self.status_label.setText(reason)
            self.status_label.setVisible(True)

    def _build_ui(self):  # TODO: turn this into a QStackedWidget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.setSpacing(16)

        title = QLabel("Sign in with Microsoft")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {ACCENT}"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.instruction_label = QLabel(
            "Click the button below to start the sign-in process.",
            alignment=Qt.AlignmentFlag.AlignCenter,
            wordWrap=True,
        )
        self.instruction_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
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

        self.code_label = QLabel("", alignment=Qt.AlignmentFlag.AlignCenter)
        self.code_label.setStyleSheet(
            "font-size: 28px; font-weight: 700; "
            f"color: {ACCENT}; letter-spacing: 4px; padding: 12px;"
        )
        self.code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.code_label)

        self.status_label = QLabel(
            "", wordWrap=True, alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.status_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px;"
        )
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
        self.start_button.clicked.connect(self._start_login_process)
        layout.addWidget(self.start_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self._cancel)
        layout.addWidget(cancel_button)

    def _start_login_process(self):
        if self._open_browser:
            return self._start_web_login()
        else:
            return self._start_device_code()

    def _start_web_login(self):
        self.start_button.setEnabled(False)
        self.open_browser.setHidden(True)
        self.status_label.setText("Spinning up web server...")
        self._thread = LoginRedirectWebserver()
        self._thread.token_recieved.connect(self._on_token)
        self._thread.error.connect(self._on_error)
        self._thread.status.connect(self.status_label.setText)
        self._thread.start()
        QDesktopServices.openUrl(QUrl(self._thread.url))
        log.debug("Opened login URL in default web browser...")

    def _start_device_code(self):
        self.start_button.setEnabled(False)
        self.open_browser.setHidden(True)
        self.status_label.setText("Requesting device code...")

        try:
            resp = requests.post(
                MS_DEVICE_CODE_URL,
                data={
                    "client_id": AZURE_CLIENT_ID,
                    "scope": AZURE_SCOPE,
                    "response_type": "device_code",
                },
                timeout=15,
            )
        except requests.RequestException as err:
            log.error("Device code request raised an exception:", exc_info=err)
            self.status_label.setText(
                f"An unexpected {type(err).__name__} error occured."
            )
            self.start_button.setEnabled(True)
            self.open_browser.setHidden(False)
            return

        if resp.status_code < 200 or resp.status_code > 299:
            err = resp.json() if resp.text else {}
            desc = err.get(
                "error_description", err.get("error", resp.text[:50])
            )
            log.error(
                "Device code request failed: %d\n%s\n%s",
                resp.status_code,
                resp.text,
                desc,
            )
            self.status_label.setText(f"HTTP {resp.status_code}")
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

        # if verification_uri == "https://www.microsoft.com/link":
        #     verification_uri = "".join([verification_uri, "?otc=", user_code])

        qr = link_to_qrcode(verification_uri)
        # self.code_qr_w.load(qr)
        self.code_qr_w.setPixmap(qr)
        self.code_qr_w.setFixedSize(qr.size())
        self.setMinimumHeight(
            self.minimumHeight() + qr.height()
        )  # qt complains a lot
        self.code_qr_w.setHidden(False)

        if error:
            self.status_label.setText(
                f"Failed to start authentication: {error}\n"
                f"Description: {error_desc}\n"
                f'<a href="{error_uri}">More info</a>'
            )
            self.open_browser.setHidden(False)
            self.start_button.setEnabled(True)
            self.code_qr_w.setHidden(True)
            return

        self.code_label.setText(user_code)
        self.instruction_label.setText(
            f'Go to <a href="{verification_uri}">{display_uri}</a>'
            " or scan the QR code\n "
            "and enter the code above to sign in."
        )
        self.instruction_label.setOpenExternalLinks(True)
        self.status_label.setText("Waiting for sign-in to complete...")

        if display_uri == verification_uri:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(user_code)
                log.debug(
                    "Verification code (%r) should be in clipboard.", user_code
                )
            else:
                log.warning("Couldn't get clipboard!")

        if self._open_browser:
            QDesktopServices.openUrl(QUrl(verification_uri))
            log.debug("Opened URL in default browser.")

        log.debug("Starting up poller")
        self._poller = DeviceCodePoller(device_code, interval, expires_in)
        self._poller.token_recieved.connect(self._on_token)
        self._poller.error.connect(self._on_error)
        self._poller.status.connect(self.status_label.setText)
        self._poller.start()

    def _on_token(self, token_data: dict):
        self.status_label.setText("Authenticating with Xbox Live...")

        msa = MicrosoftAccount(token_data)
        try:
            lp = auth_flow(msa)
        except NoConnectionError as err:
            error_box(str(err))
            return self.reject()
        except Exception as err:
            log.error("Auth chain failed! Details:\n%s", str(err))
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
            log.info("Logged in as %s", lp.gamertag)
            self.login_complete.emit(lp)
            self.start_button.setEnabled(True)
            self.open_browser.setHidden(False)
            self.code_qr_w.setHidden(True)
            self.accept()

    def _on_error(self, message: str):
        log.error("Login error: %s", message)
        self.status_label.setText(message)
        self.start_button.setEnabled(True)
        self.open_browser.setHidden(False)
        self.code_qr_w.setHidden(True)

    def _cancel(self):
        if self._poller:
            self._poller.cancel()
            self._poller.deleteLater()
            self._poller = None
        if self._thread:
            self._thread.cancel()
            self._thread.deleteLater()
        self.reject()

    def closeEvent(self, a0):
        if self._poller:
            self._poller.cancel()
            self._poller.wait()
            self._poller.deleteLater()
            self._poller = None
        if self._thread:
            self._thread.cancel()
            self._thread.wait()
            self._thread.deleteLater()
            self._thread = None
        super().closeEvent(a0)

    def _set_open_browser(self, a0: Qt.CheckState):
        checked = self.open_browser.isChecked()
        self._open_browser = config.open_browser_for_login = checked
