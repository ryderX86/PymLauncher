# pylint: disable=redefined-builtin
__all__ = [
    "WrappedUL3Exception",
    "ReadError",
    "ConnectError",
    "HTTPStatusCodeError",
    "BaseNetworkingError",
]
from collections.abc import Iterable, Mapping
from email.utils import parsedate_to_datetime
from http.client import responses
from string import digits
import logging
import time

from urllib3.exceptions import (
    ConnectTimeoutError,
    DecodeError,
    HeaderParsingError,
)
from urllib3.exceptions import HTTPError as HTTPError_
from urllib3.exceptions import (
    IncompleteRead,
    InvalidChunkLength,
    InvalidHeader,
    MaxRetryError,
    NameResolutionError,
    NewConnectionError,
    ProtocolError,
    ProxyError,
    ReadTimeoutError,
    ResponseNotChunked,
    SSLError,
    TimeoutError,
)
from urllib3.response import BaseHTTPResponse

log = logging.getLogger(__name__)
_RETRY_DEFAULT = 5.0


class BaseNetworkingError(Exception):
    @property
    def should_retry(self) -> bool:
        return False

    @property
    def dns_related(self) -> bool:
        return False


class HTTPStatusCodeError(BaseNetworkingError):
    body: str | None
    url: str
    code: int
    headers: Mapping[str, str]
    response: BaseHTTPResponse

    def __init__(self, code: int, resp: BaseHTTPResponse):
        assert resp.url
        self.url = resp.url
        self.code = code
        self.headers = resp.headers
        self.response = resp
        if not resp.closed:
            try:
                resp.read()
                self.body = resp.data.decode("utf-8")
            except Exception as err:
                log.warning(
                    "Ignoring exception reading failed response body:",
                    exc_info=err,
                )
                self.body = None
            finally:
                if resp.length_remaining:
                    resp.drain_conn()
                else:
                    resp.release_conn()
        else:
            self.body = resp.data.decode("utf-8")

    @property
    def retry_after(self):
        if self.code not in {429, 503}:
            return None
        if "Retry-After" in self.headers:
            ra = self.headers["Retry-After"]
            if not all(a in digits for a in ra):
                try:
                    ts = parsedate_to_datetime(ra).timestamp()
                except Exception as err:
                    log.warning(
                        "Couldn't get datetime from 'Retry-After' header:",
                        exc_info=err,
                    )
                    ts = _RETRY_DEFAULT
                else:
                    t = time.time()
                    if ts > t:
                        ts -= t
            else:
                try:
                    ts = float(ra)
                except ValueError as err:
                    log.error(
                        "Couldn't get timestamp from %r in 'Retry-After' "
                        "header:",
                        ra,
                        exc_info=err,
                    )
                    ts = _RETRY_DEFAULT
        else:
            ts = _RETRY_DEFAULT
        if ts < 1:
            ts = _RETRY_DEFAULT
        elif ts > 30:
            return None
        return round(ts)

    @property
    def desc(self):
        return responses.get(self.code, "Unknown")

    @property
    def should_retry(self) -> bool:
        return self.code in {429, 503} and bool(self.retry_after)


class WrappedUL3Exception(BaseNetworkingError):
    handles: set[type[HTTPError_]] = set()
    cause: Exception
    resp: BaseHTTPResponse | None
    url: str

    def __init__(
        self, exc: Exception, url: str, resp: BaseHTTPResponse | None = None
    ):
        self.cause = exc
        self.resp = resp
        self.url = url
        super().__init__(self._super_args())

    def _super_args(self) -> str:
        return f"{type(self.cause)} occured connecting to {self.url!r}"

    def __init_subclass__(cls, handles: Iterable[type[HTTPError_]], **kwargs):
        super().__init_subclass__(**kwargs)
        match handles:
            case set():
                cls.handles = handles
            case _:
                cls.handles = set(handles)

    @classmethod
    def from_exc(
        cls, exc: HTTPError_, url: str, resp: BaseHTTPResponse | None = None
    ):
        if isinstance(exc, MaxRetryError):
            if exc.reason and isinstance(exc.reason, HTTPError_):
                log.debug(
                    "%s() -> %s()",
                    type(exc).__name__,
                    type(exc.reason).__name__,
                )
                exc = exc.reason
        exc_t = type(exc)
        for bt in exc_t.__mro__:
            for sub in cls.__subclasses__():
                if bt in sub.handles:
                    return sub(exc, url, resp)
        log.warning(
            "Couldn't get the proper exception for HTTPError type %s()",
            exc_t.__name__,
        )
        log.debug("MRO: %r", (t.__name__ for t in exc_t.__mro__))
        return cls(exc, url, resp)


class ConnectError(
    WrappedUL3Exception,
    handles={
        TimeoutError,
        ConnectTimeoutError,
        NameResolutionError,
        NewConnectionError,
        ProxyError,
        SSLError,
        ReadTimeoutError,
        MaxRetryError,
    },
):
    _retry_for = {NewConnectionError, ConnectTimeoutError, ReadTimeoutError}

    def _get_exc_string(self):
        url_noscheme = self.url.replace("https://", "").replace("http://", "")
        url_path = url_noscheme.split("/")
        if isinstance(self.cause, NameResolutionError):
            return f"Failed to resolve hostname {url_path[0]}"
        if isinstance(self.cause, NewConnectionError):
            return f"Failed to connect to {url_path[0]}"
        return f"Failed to connect to {url_path[0]}"

    def _super_args(self):
        return self._get_exc_string()

    @property
    def dns_related(self):
        return isinstance(self.cause, (NameResolutionError, type(self)))

    @property
    def should_retry(self):
        return type(self.cause) in self._retry_for and not self.dns_related


class ReadError(
    WrappedUL3Exception,
    handles={
        ResponseNotChunked,
        DecodeError,
        HeaderParsingError,
        IncompleteRead,
        ProtocolError,
        InvalidChunkLength,
        InvalidHeader,
    },
):
    def _super_args(self):
        url_noscheme = self.url.replace("https://", "").replace("http://", "")
        url_path = url_noscheme.split("/")
        if isinstance(self.cause, (IncompleteRead, InvalidChunkLength)):
            if self.resp:
                length = self.resp.headers.get("Content-Length", "<unknown>")
            else:
                length = "<unknown>"
            return (
                "Response was cut-off/didn't match expected "
                f"'Content-Length' of {length}"
            )
        elif isinstance(self.cause, ResponseNotChunked):
            return "Response is not chunked."
        elif isinstance(
            self.cause, (DecodeError, HeaderParsingError, InvalidHeader)
        ):
            return "Failed to decode data returned by server."
        return f"Connection to {url_path[0]} was interrupted."
        # pylint: disable-next=misplaced-bare-raise

    @property
    def should_retry(self) -> bool:
        return True
