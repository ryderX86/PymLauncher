"""
Functions for handling offline mode stuff
"""

__all__ = ["offline_man"]
from collections.abc import Callable
import logging

import requests

from launcher.threads.offline import OfflineModeCheckerThread

log = logging.getLogger(__name__)


class _OfflineModeManager:
    _offline: bool
    _offline_hooks: list[Callable[[bool], None]]

    def __init__(self):
        self._offline = False
        self._offline_hooks = []

    @property
    def offline(self):
        return self._offline

    @offline.setter
    def offline(self, is_offline: bool):
        if self._offline and is_offline:
            log.warning("Status set to offline twice!")
            return
        elif not self._offline and not is_offline:
            log.warning("Status set to online twice!")
            return
        self._offline = is_offline
        log.debug(
            "Connection status set: %s", "Offline" if is_offline else "Online"
        )
        for func in self._offline_hooks:
            func(is_offline)
        log.debug("Called %s hook functions", len(self._offline_hooks))
        if is_offline:
            _start_status_checker_thread(self._back_online)

    def add_hook(self, func: Callable[[bool], None], idx: int | None = None):
        if func in self._offline_hooks:
            raise ValueError(
                f"Function {func.__name__!r}() already registered as a hook"
            )
        if idx is None:
            self._offline_hooks.append(func)
        else:
            self._offline_hooks.insert(idx, func)

    def remove_hook(self, func: Callable[[bool], None]):
        if func not in self._offline_hooks:
            raise AttributeError(
                f"Function {func.__name__!r}() not yet registered as a hook"
            )

        self._offline_hooks.remove(func)

    def check_requests_error(self, err: BaseException):
        """
        Take any `BaseException` derivitive and check if 1. it's a
        `requests.ConnectionError`, and 2. if the error number coorelates to
        a DNS issue (`11001`, `-2`, or `8`)

        If it's a DNS issue, this function will set offline mode to True.
        Otherwise, it'll do nothing.

        Returns the new lack-of-connection status (`True` for offline,
        `False` for online)
        """
        if not isinstance(err, requests.ConnectionError):
            return False
        if (
            "[Errno 11001]" in str(err)
            or "[Errno -2]" in str(err)
            or "[Errno 8]" in str(err)
        ):
            log.warning("DNS error occured, setting offline mode.")
            self.offline = True
            log.error("Exception traceback:", exc_info=err)
        return self.offline

    @property
    def cause(self):
        return _current_status

    def _back_online(self):
        log.info("Connectivity to Xbox Live and Mojang has been restored")
        self.offline = False


offline_man = _OfflineModeManager()
connectivity_poller = OfflineModeCheckerThread()
_current_status = "Unknown"


def _status_update(dns_issue: bool, xbl_issue: bool, moj_issue: bool):
    global _current_status
    if dns_issue:
        _current_status = "No internet connection"
    elif xbl_issue and moj_issue:
        _current_status = "Both Xbox and Mojang are experiencing issues"
    elif xbl_issue:
        _current_status = "Xbox Live is currently experiencing issues"
    elif moj_issue:
        _current_status = "Mojang is currently experiencing issues"
    else:
        _current_status = "Unknown"


def _start_status_checker_thread(callback: Callable):
    global connectivity_poller, _current_status
    if connectivity_poller.has_run:
        connectivity_poller.terminate()
        connectivity_poller.deleteLater()
        connectivity_poller = OfflineModeCheckerThread()
    _current_status = "Unknown"

    connectivity_poller.cause_changed.connect(_status_update)
    connectivity_poller.back_online.connect(callback)
    log.debug("Starting OfflineModeCheckerThread()")
    connectivity_poller.start()
