import json
import logging

from PySide6.QtCore import QThread, Signal
import requests

from launcher import SESSION

MIN_POLL_TIME = 30  # seconds

XBOX_STATUS_URL = "https://xnotify.xboxlive.com/servicestatusv6/US/en-US"
MOJANG_STATUS_URL = "https://api.mojang.com/users/profiles/minecraft/jeb_"
# we have no actual "status" endpoint for mojang so we can just query a
# public profile instead

XBL_NO_ISSUE = "None"


class OfflineModeCheckerThread(QThread):
    back_online = Signal()

    cause_changed = Signal(bool, bool, bool)
    """
    What caused the offline mode.
    
    Arguments in order:
    1. DNS issue/user has no internet connection
    2. Xbox API issue
    3. Mojang API issue
    """

    log: logging.Logger
    has_run: bool

    def __init__(self):
        super().__init__()
        self.log = logging.getLogger(type(self).__qualname__)
        self.has_run = False

    def run(self):
        self.has_run = True
        dns_issue: bool = False
        xbl_issue: bool = False
        moj_issue: bool = False

        timeout_xbl: bool = False
        timeout_moj: bool = False
        while True:
            dns_issue = False
            timeout_xbl = False
            timeout_moj = False
            # check XBL status
            try:
                resp = SESSION.get(XBOX_STATUS_URL)
                resp.raise_for_status()
                xbl_status = resp.json()
            except requests.exceptions.ConnectTimeout:
                timeout_xbl = True
            except requests.ConnectionError as err:
                if (
                    "[Errno 11001]" in str(err)
                    or "[Errno -2]" in str(err)
                    or "[Errno 8]" in str(err)
                ):
                    dns_issue = True
            except Exception:
                xbl_issue = True
            else:
                try:  # temporary, remove this after confirming it works
                    xbl_issue = not self._xbl_status_parser(xbl_status)
                except Exception as err:
                    self.log.error(
                        "Issue checking API response:", exc_info=err
                    )
                    xbl_issue = True

            # check Mojang status
            try:
                resp = SESSION.get(MOJANG_STATUS_URL)
                resp.raise_for_status()
                moj_status = resp.json()
            except requests.exceptions.ConnectTimeout:
                timeout_moj = True
            except requests.ConnectionError as err:
                if (
                    "[Errno 11001]" in str(err)
                    or "[Errno -2]" in str(err)
                    or "[Errno 8]" in str(err)
                ):
                    dns_issue = True
            except Exception:
                moj_issue = True
            else:
                moj_issue = moj_status != {
                    "id": "853c80ef3c3749fdaa49938b674adae6",
                    "name": "jeb_",
                }

            if timeout_xbl and timeout_moj:
                self.log.warning(
                    "Timeout for both XBL API and Mojang API, no internet "
                    "connection."
                )
                dns_issue = True
                xbl_issue = False
                moj_issue = False

            # update signal
            self.cause_changed.emit(dns_issue, xbl_issue, moj_issue)
            if all({not dns_issue, not xbl_issue, not moj_issue}):
                self.log.info(
                    "No further issues detected, we're back online, baby!"
                )
                break

            self.sleep(MIN_POLL_TIME)
        self.log.debug("Emitting back_online signal")
        self.back_online.emit()
        return

    def _xbl_status_check_json(self, status: dict):
        """
        Check the API response for the proper JSON structure
        """
        if (
            "Status" not in status
            or "Overall" not in status["Status"]
            or "SelectedScenarios" not in status["Status"]
            or "CoreServices" not in status
            or "Titles" not in status
        ):
            return {}

        repl_coreservice = []
        repl_titles = []

        for svc in status["CoreServices"]:
            if (
                "Id" not in svc
                or "Name" not in svc
                or "Status" not in svc
                or "Name" not in svc["Status"]
            ):
                self.log.warning(
                    "Skipping malformed CoreService item in API response "
                    "(JSON: %r)",
                    json.dumps(svc),
                )
                continue
            repl_coreservice.append(svc)

        for title in status["Titles"]:
            if (
                "Id" not in title
                or "Name" not in title
                or "Status" not in title
                or "Name" not in title["Status"]
            ):
                self.log.warning(
                    "Skipping malformed title item in API response (JSON: %r)",
                    json.dumps(title),
                )
                continue
            repl_titles.append(title)

        status["CoreServices"] = repl_coreservice
        status["Titles"] = repl_titles

        return status

    def _xbl_status_parser(self, status: dict):
        """
        Take a Xbox API status response and check for any observable issues

        Returns `False` if issues are found, `True` if we're good to go online
        again.
        """
        status = self._xbl_status_check_json(status)
        if not status:
            self.log.warning(
                "Malformed API response, ignoring and treating as an API issue"
            )
            return False

        if status["Status"]["Overall"]["State"] != XBL_NO_ISSUE:
            return False
        elif status["Status"]["SelectedScenarios"]["State"] != XBL_NO_ISSUE:
            return False
        for svc in status["CoreServices"]:
            if svc["Status"]["Name"] != XBL_NO_ISSUE:
                self.log.debug(
                    "Xbox Core Service (%r) issue detected. Status: %r",
                    svc["Name"],
                    svc["Status"]["Name"],
                )
                return False
        for title in status["Titles"]:
            if title["Status"]["Name"] != XBL_NO_ISSUE:
                self.log.debug(
                    "Potential issue with %r. Status: %r",
                    title["Name"],
                    title["Status"]["Name"],
                )
                return False
        return True
