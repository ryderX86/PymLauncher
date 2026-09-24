# pylint: disable=redefined-builtin
from typing import Literal, overload
import json
import logging
import time

from PySide6.QtCore import QCoreApplication, QThread
from urllib3.exceptions import HTTPError as UL3HTTPError
from urllib3.response import BaseHTTPResponse
from urllib3.util import Retry
import urllib3

from launcher import constants
from launcher.exceptions.network import (
    HTTPStatusCodeError,
    WrappedUL3Exception,
)
from launcher.offline import offline_man

from .dns import flush_dns_cache

log = logging.getLogger(__name__)
http = urllib3.PoolManager(
    maxsize=constants.CPU_THREADS + 1,
    headers={"User-Agent": constants.USER_AGENT},
    timeout=30,
)
retry = Retry(
    # don't retry on anything error-related
    connect=False,
    read=False,
    other=False,
    # counts
    total=None,
    redirect=5,
)

type FormData = tuple[str, bytes, str] | tuple[str, bytes] | tuple[
    str, str
] | str


def _sleep(time_: int | float):
    qapp = QCoreApplication.instance()
    t = QThread.currentThread()
    if qapp and qapp.thread() == t:
        log.warning(
            "GUI thread will be blocked for %fs, "
            "move this to a different thread",
            time_,
        )
    time.sleep(time_)


@overload
def make_request(
    type_: Literal["get"],
    url: str,
    headers: dict[str, str] | None = None,
    body: None = None,
    *,
    mgr=http,
    preload_response: bool = True,
    retries: int = 3,
    timeout: int = 30,
) -> BaseHTTPResponse: ...


@overload
def make_request(
    type_: Literal["post"],
    url: str,
    headers: dict[str, str] | None = None,
    body: str | bytes | dict | None = None,
    form: dict[str, FormData] | None = None,
    *,
    mgr=http,
    preload_response: bool = True,
    retries: int = 3,
    timeout: int = 30,
) -> BaseHTTPResponse: ...


@overload
def make_request(
    type_: Literal["put"],
    url: str,
    headers: dict[str, str] | None = None,
    body: str | bytes | dict | None = None,
    *,
    mgr=http,
    preload_response: bool = True,
    retries: int = 3,
    timeout: int = 30,
) -> BaseHTTPResponse: ...


@overload
def make_request(
    type_: Literal["delete"],
    url: str,
    headers: dict[str, str] | None = None,
    *,
    mgr=http,
    preload_response: bool = True,
    retries: int = 3,
    timeout: int = 30,
) -> BaseHTTPResponse: ...


def make_request(
    type_: Literal["get", "post", "put", "delete"],
    url: str,
    headers: dict[str, str] | None = None,
    body: str | bytes | dict | None = None,
    form: dict[str, FormData] | None = None,
    *,
    mgr=http,
    preload_response: bool = True,
    retries: int = 3,
    timeout: int = 30,
) -> BaseHTTPResponse:
    if type_ == "get" and bool(body or form):
        raise ValueError("Cannot add body/form fields to GET requests")
    if isinstance(body, dict):
        body = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        body = body.encode("utf-8")
    for attempt in range(1, max(retries + 1, 2)):
        try:
            resp = mgr.request(
                type_,
                url,
                body,
                form,
                headers,
                preload_content=preload_response,
                retries=retry,
                timeout=timeout,
            )
        except UL3HTTPError as err:
            new = WrappedUL3Exception.from_exc(err, url)
            error = new
            if attempt > retries:
                pass
            elif new.dns_related:
                log.debug("Flushing DNS cache to see if we can try again")
                flush_dns_cache()
                _sleep(0.5 * attempt)
                log.debug("Trying again (attempt %d/%d)", attempt + 1, retries)
                continue
            elif new.should_retry and not offline_man.offline:
                _sleep(0.5 * attempt)
                log.debug(
                    "Request to %r failed, trying again. (attempt %d/%d)",
                    url,
                    attempt + 1,
                    retries,
                )
                continue
            raise new from err

        if resp.status in range(200, 300):
            return resp
        error = HTTPStatusCodeError(resp.status, resp)
        if error.retry_after:
            _sleep(error.retry_after)
            log.debug(
                "Request to %r failed, trying again (attempt %d/%d)",
                url,
                attempt + 1,
                retries,
            )
            continue
        else:
            break
    raise error  # type: ignore
