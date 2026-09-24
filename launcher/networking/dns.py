import ctypes
import logging

from launcher import constants

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

match constants.OS:
    case "windows":

        def flush_dns_cache():  # type: ignore
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
                log.error("Failed to flush DNS resolver cache:", exc_info=err)

    case _:
        # try and force DNS reconfiguration (verify source, rn it's gemini)
        assert unix_dns_lib

        def flush_dns_cache():
            try:
                unix_dns_lib.res_init()  # type: ignore
                return True
            except Exception as err:
                log.error(
                    "Failed to refresh process's DNS config:", exc_info=err
                )
