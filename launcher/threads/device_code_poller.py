from json import JSONDecodeError
import logging
import time

from launcher import constants
from launcher.exceptions.network import HTTPStatusCodeError
from launcher.networking import make_request

from .base_login_thread import BaseLoginThread

log = logging.getLogger(__name__)


class DeviceCodePoller(BaseLoginThread):
    """Poller for MSA token endpoint"""

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

    def requestInterruption(self) -> None:
        self._cancelled = True
        return super().requestInterruption()

    def run(self):
        deadline = time.time() + self.expires_in

        while time.time() < deadline and not (
            self._cancelled or self.isInterruptionRequested()
        ):
            time.sleep(self.interval)
            if self._cancelled:
                self.log.info("Login cancelled. Exiting.")
                return

            try:
                resp = make_request(
                    "post",
                    constants.MS_TOKEN_URL,
                    form={
                        "grant_type": constants.AZURE_GRANT_TYPE,
                        "client_id": constants.AZURE_CLIENT_ID,
                        "device_code": self.device_code,
                        "scope": constants.AZURE_SCOPE,
                    },
                    timeout=30,
                )
            except HTTPStatusCodeError as err:
                resp = err.response
                if err.code == 400:
                    try:
                        body = err.response.json()
                    except JSONDecodeError as err2:
                        log.error("Failed parsing JSON from response:", exc_info=err)
                        self.status.emit("Failed to decode server response")
                        raise err2
                    match body.get("error"):
                        case "authorization_pending":
                            self.status.emit("Waiting for authorization...")
                            continue
                        case "authorization_declined":
                            self.status.emit("Login denied")
                            return
                        case "expired_token":
                            self.status.emit("Device code expired. Please try again.")
                            return
                        case "slow_down":
                            log.warning(
                                "Microsoft told us to slow down!"
                                "Interval +=5"
                            )
                            continue
                        case _:
                            self.error.emit(
                                "Unexpected error: "
                                f"{err.response.data.decode("utf-8")}"
                            )
                            return
                else:
                    self.status.emit(f"Connection error: {err}")
                    continue

            data = resp.json()

            if "access_token" in data:
                self.token_received.emit(data)
                return

        if not self._cancelled:
            self.error.emit("Login window timed out.")
