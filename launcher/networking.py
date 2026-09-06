import logging
import ctypes

from requests.exceptions import ConnectionError as _ConnectionError
import requests

from . import constants

log = logging.getLogger(__name__)

match constants.OS:
    case "osx":
        unix_dns_lib = ctypes.CDLL("libresolv.dylib")
    case "linux" | "unknown":
        try:
            unix_dns_lib = ctypes.CDLL("libc.so.6")
        except Exception as err:
            log.error("Failed to load libc.so.6:", exc_info=err)
            unix_dns_lib = None
    case _:
        unix_dns_lib = None


class ResilientSession(requests.sessions.Session):
    """
    `requests.Session()` subclass with `send()` overridden to enable recovery
    from offline states
    """

    match constants.OS:
        case "windows":

            def _flush_dns_cache(self):  # type: ignore
                log.debug("Flushing DNS cache...")
                try:
                    ctypes.windll.dnsapi.DnsFlushResolverCache()
                except AttributeError as err:
                    log.error(
                        "Failed to flush DNS resolver cache using "
                        "...dnsapi.DnsFlushResolverCache(); AttributeError:",
                        exc_info=err,
                    )
                    raise
                except Exception as err:
                    log.error(
                        "Failed to flush DNS resolver cache:", exc_info=err
                    )

        case _:
            # try and force DNS reconfiguration (verify source, rn it's gemini)
            assert unix_dns_lib

            def _flush_dns_cache(self):
                try:
                    unix_dns_lib.res_init()  # type: ignore
                    return True
                except Exception as err:
                    log.error(
                        "Failed to refresh process's DNS config:", exc_info=err
                    )

    def send(self, request, **kwargs):
        try:
            return super().send(request, **kwargs)
        except (ConnectionError, _ConnectionError) as err:
            if "getaddrinfo" in str(err):
                log.debug("DNS error occured, trying to remediate it...")
                self.close()
                self._flush_dns_cache()
            raise  # re-raise for retry logic
