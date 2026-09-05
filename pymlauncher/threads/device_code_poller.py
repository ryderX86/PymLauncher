import logging
import time

from PySide6.QtCore import QThread, Signal
from requests.exceptions import RequestException

from pymlauncher import SESSION, constants

log = logging.getLogger(__name__)


class DeviceCodePoller(QThread):
    """Poller for MSA token endpoint"""

    token_recieved = Signal(dict)
    error = Signal(str)
    status = Signal(str)
    log = log.getChild("DeviceCodePoller")

    def __init__(
        self,
        device_code: str,
        interval: int = 5,
        expires_in: int = 900,
        parent=None,
    ):
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
                resp = SESSION.post(
                    constants.MS_TOKEN_URL,
                    data={
                        "grant_type": constants.AZURE_GRANT_TYPE,
                        "client_id": constants.AZURE_CLIENT_ID,
                        "device_code": self.device_code,
                        "scope": constants.AZURE_SCOPE,
                    },
                    timeout=30,
                )
            except RequestException as exc:
                self.status.emit(f"Connection error: {exc}")
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
                    self.error.emit(
                        "Unexpected error: {error}\n%s" f"{data.get(
                            "error_description",
                            "(no description provided)"
                        )}"
                    )
                    log.error("Login error occured: %s", str(error))
                    if data.get("error_description"):
                        log.error("Details: %s", data["error_description"])
                    return

        if not self._cancelled:
            self.error.emit("Login window timed out.")
