import requests
import time
import logging

def try_request(log:logging.Logger, url:str|bytes, *args, **kwargs):
    max_retries = 3
    resp = None
    if isinstance(url, bytes):
        url_ = url.decode()
    else:
        url_ = url
    while max_retries > 0:
        try:
            resp = requests.get(url, *args, **kwargs)
            resp.raise_for_status()
        except (requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError) as err:
            log.error("Failed to connect to '%s':" % url, exc_info=err)
            log.info("Waiting 5 seconds and trying again...")
            time.sleep(5)
        except requests.HTTPError as err:
            log.error("Failed to fetch from URL:")
            err.add_note("Failed to fetch from URL '%s'" % url_)
            raise
        except Exception as err:
            log.error("Unknown error occured while fetching from URL:")
            err.add_note("Failed to fetch from URL '%s'" % url_)
            raise
        else:
            break
        max_retries -= 1
    if not resp:
        raise RuntimeError("Failed to get response from URL '%s' (timeout)"
                           % url_)
    return resp