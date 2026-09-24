import logging

from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError as _ConnectionError
from urllib3.util import Retry

from launcher import constants

from .resilient_session import ResilientSession
from .urllib3_wrapped import (
    http,
    make_request,
)

log = logging.getLogger(__name__)

_adapter = HTTPAdapter(
    max_retries=Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        retry_after_max=15,
    )
)


session = ResilientSession()
session.headers["User-Agent"] = constants.USER_AGENT
session.mount("http://", _adapter)
session.mount("https://", _adapter)
