from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
import base64
import hashlib
import json
import logging
import secrets

from PySide6.QtCore import QThread, Signal
from requests.exceptions import HTTPError, JSONDecodeError

from pymlauncher import SESSION, constants
from pymlauncher.offline import offline_man


class ParentedHTTPServer(HTTPServer):
    def __init__(
        self,
        parent: "LoginRedirectWebserver",
        server_address: (
            tuple[str | bytes | bytearray, int]
            | tuple[str | bytes | bytearray, int, int, int]
        ),
        RequestHandlerClass,
        bind_and_activate: bool = True,
    ) -> None:
        super().__init__(
            server_address, RequestHandlerClass, bind_and_activate
        )
        self.parent = parent


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urlparse(self.path).query
        parsed_query = parse_qs(query)

        assert isinstance(self.server, ParentedHTTPServer)

        if "error" in parsed_query:
            self.server.parent.on_error(parsed_query["error_description"][0])
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                bytes(
                    "<html><script>window.close();</script><body>"
                    "<h1>Login error</h1>"
                    "<p>An error occured while logging in:</p>"
                    f"<p>{parsed_query["error_description"][0]}</p>"
                    "</body></html>",
                    encoding="utf-8",
                )
            )
        else:
            self.server.parent.on_success(
                parsed_query["code"][0], parsed_query.get("state", [None])[0]
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><script>window.close();</script><body>"
                b"<h1>Login successful.</h1>"
                b"<p>You may now close this tab/window.</p></body></html>"
            )

    def log_message(self, *args, **kwargs):
        pass


class LoginRedirectWebserver(QThread):
    token_recieved = Signal(dict)
    error = Signal(str)
    status = Signal(str)
    log = logging.getLogger(__name__)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stop = False
        redirect_uri = constants.AZURE_REDIRECT_URL

        self.verifier = secrets.token_urlsafe(64)
        sha = hashlib.sha256(self.verifier.encode("ascii")).digest()
        self.challenge = (
            base64.urlsafe_b64encode(sha).decode("ascii").rstrip("=")
        )

        login_params = {
            "tenant": "consumers",
            "client_id": constants.AZURE_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": constants.AZURE_SCOPE,
            "response_mode": "query",
            "prompt": "select_account",
            "code_challenge": self.challenge,
            "code_challenge_method": "S256",
        }

        url = [*urlparse(constants.MS_WEB_LOGIN_URL)]
        url[4] = urlencode(login_params)
        self.url = urlunparse(url)

    def cancel(self):
        self.stop = True
        self.log.debug("Cancelling process...")
        self.server.server_close()
        return

    def run(self):
        self.log.debug(
            "Verifier: %r; challenge code: %r", self.verifier, self.challenge
        )
        self.server = ParentedHTTPServer(
            self, ("localhost", constants.AZURE_REDIRECT_PORT), RequestHandler
        )

        self.status.emit("Waiting on authorization...")

        while not self.stop:
            self.server.handle_request()
        self.server.server_close()
        return

    def on_error(self, description: str):
        self.error.emit(description)

    def on_success(self, code: str, state: str | None):
        self.stop = True
        if state:
            self.log.debug("State: %r", state)

        self.status.emit("Getting account tokens...")

        payload = {
            "client_id": constants.AZURE_CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": constants.AZURE_REDIRECT_URL,
            "code_verifier": self.verifier,
        }

        try:
            resp = SESSION.post(constants.AZURE_TOKEN_URL, data=payload)
            resp.raise_for_status()
        except HTTPError as err:
            offline_man.check_requests_error(err)
            if err.response:
                self.log.error(
                    "Error occured during authentication: %s", err.response
                )
                try:
                    parsed_error = err.response.json()
                except:
                    self.error.emit(err.response)
                else:
                    self.error.emit(
                        parsed_error.get("error_description", "Unknown error")
                    )
            else:
                self.error.emit("An unknown error occured.")
            self.log.error("Error during authentication:", exc_info=err)
            return
        except Exception as err:
            offline_man.check_requests_error(err)
            self.log.error(
                "Error occured during authentication:", exc_info=err
            )
            self.error.emit("Unknown error (%r)", type(err).__name__)
            return

        try:
            response_json = resp.json()
        except JSONDecodeError:
            self.log.error("Malformed JSON in response: %r", resp.text)
            self.error.emit("Malformed JSON in response")
            return

        if "error" in response_json:
            self.log.warning(
                "MSA process returned an error:\n%s",
                json.dumps(response_json, indent=2),
            )
            self.error.emit(
                response_json.get(
                    "error_description", response_json.get("error", "Unknown")
                )
            )
            return

        self.log.debug("We got a token")
        self.status.emit("Token recieved, authenticating with Xbox/Mojang")
        self.token_recieved.emit(response_json)
