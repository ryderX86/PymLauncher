import logging

from requests.exceptions import ConnectionError as ConnectionError_
from requests.sessions import Session

from .dns import flush_dns_cache

log = logging.getLogger(__name__)


class ResilientSession(Session):
    """
    `requests.session()` subclass with `send()` overridden to enable recovery
    from offline states
    """

    def send(self, request, **kwargs):
        try:
            return super().send(request, **kwargs)
        except (ConnectionError, ConnectionError_) as err:
            if "getaddrinfo" in str(err):
                log.debug("DNS error occured, trying to remediate it...")
                self.close()
                flush_dns_cache()
            raise  # re-raise for retry logic
