from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
import base64
import hashlib
import html
import json
import logging
import secrets

from requests.exceptions import HTTPError, JSONDecodeError

from launcher import SESSION, constants
from launcher.offline import offline_man

from .base_login_thread import BaseLoginThread

log = logging.getLogger(__name__)


class RedirectHTTPServer(HTTPServer):
    """HTTPServer subclass for type checking purposes, holds the results."""

    login_code: str | None
    login_state: str | None
    error_description: str | None
    expected_state: str | None

    def __init__(
        self,
        server_address,
        RequestHandlerClass,
        bind_and_activate: bool = True,
        *,
        expected_state: str | None = None,
    ) -> None:
        super().__init__(
            server_address, RequestHandlerClass, bind_and_activate
        )
        self.login_code = None
        self.login_state = None
        self.error_description = None
        self.expected_state = expected_state


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urlparse(self.path).query
        parsed_query = parse_qs(query)

        assert isinstance(self.server, RedirectHTTPServer)

        if "code" in parsed_query:
            code: str | None = parsed_query.get("code", [None])[0]
            state: str | None = parsed_query.get("state", [None])[0]
            if not code:
                log.warning("No code present from auth redirect")
                self.return_failure(
                    "Authentication server redirected with no code"
                )
                self.server.error_description = "No code present in request"
            elif state != self.server.expected_state:
                log.warning("State mismatch! Aborting login")
                self.return_failure(
                    "Login session couldn't be verified, please try again."
                )
                self.server.error_description = (
                    "State mismatch between request and response"
                )
            else:
                self.server.login_code = code
                self.server.login_state = state
                self.return_success()
        else:
            description: str = parsed_query.get(
                "error_description", ["Unknown error"]
            )[0]
            self.return_failure(description)
            self.server.error_description = description

    def log_message(self, *args, **kwargs):
        pass

    def return_success(self):
        assert isinstance(self.server, RedirectHTTPServer)

        content = (
            b"<html><script>window.close();</script><body>"
            b"<h1>Login successful.</h1>"
            b"<p>You may now close this tab/window.</p></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)
        self.wfile.flush()

    def return_failure(self, description: str):
        assert isinstance(self.server, RedirectHTTPServer)

        content = bytes(
            "<html><script>window.close();</script><body>"
            "<h1>Login error</h1>"
            "<p>An error occured while logging in:</p>"
            f"<p>{html.escape(description)}</p>"
            "</body></html>",
            encoding="utf-8",
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)
        self.wfile.flush()


class LoginRedirectWebserver(BaseLoginThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.stop = False

        self.verifier = secrets.token_urlsafe(64)
        sha = hashlib.sha256(self.verifier.encode("ascii")).digest()
        self.challenge = (
            base64.urlsafe_b64encode(sha).decode("ascii").rstrip("=")
        )
        self.state = secrets.token_urlsafe(32)

        self.server = RedirectHTTPServer(
            ("localhost", 0),
            RequestHandler,
            expected_state=self.state,
        )
        self.port: int = self.server.server_address[1]
        self.server.timeout = 0.5
        self.finished.connect(self.server.server_close)
        self.redirect_uri = f"{constants.AZURE_REDIRECT_URL}:{self.port}"

        login_params = {
            "tenant": "consumers",
            "client_id": constants.AZURE_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": constants.AZURE_SCOPE,
            "response_mode": "query",
            "prompt": "select_account",
            "code_challenge": self.challenge,
            "code_challenge_method": "S256",
            "state": self.state,
        }

        url = [*urlparse(constants.MS_WEB_LOGIN_URL)]
        url[4] = urlencode(login_params)
        self.url = urlunparse(url)

    def cancel(self):
        self.stop = True
        log.debug("Cancelling process...")
        return

    def run(self):
        log.debug("Challenge code: %r", self.challenge)

        self.status.emit("Waiting on authorization...")

        while not self.stop:
            try:
                self.server.handle_request()
            except Exception as err:
                self.stop = True
                log.error("Error occured during authentication:", exc_info=err)
                log.info("Stopping server early due to error.")
            else:
                if self.server.error_description:
                    self.on_error(self.server.error_description)
                elif self.server.login_code:
                    self.on_success(
                        self.server.login_code, self.server.login_state
                    )
        return

    def on_error(self, description: str):
        self.error.emit(description)
        self.stop = True

    def on_success(self, code: str, state: str | None):
        self.stop = True
        self.auth_code_received.emit()
        if state:
            log.debug("State: %r", state)

        self.status.emit("Getting account tokens...")

        payload = {
            "client_id": constants.AZURE_CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": self.verifier,
        }

        try:
            resp = SESSION.post(constants.AZURE_TOKEN_URL, data=payload)
            resp.raise_for_status()
        except HTTPError as err:
            offline_man.check_requests_error(err)
            if err.response:
                log.error(
                    "Error occured during authentication: %s", err.response
                )
                try:
                    parsed_error = err.response.json()
                except JSONDecodeError:
                    log.warning(
                        "Failed to parse JSON from web response, "
                        "signalling raw text instead."
                    )
                    self.error.emit(err.response.text)
                else:
                    self.error.emit(
                        parsed_error.get("error_description", "Unknown error")
                    )
            else:
                self.error.emit("An unknown error occured.")
            log.error("Error during authentication:", exc_info=err)
            return
        except Exception as err:
            offline_man.check_requests_error(err)
            log.error("Error occured during authentication:", exc_info=err)
            self.error.emit(f"Unexpected error ({type(err).__name__})")
            return

        try:
            response_json = resp.json()
        except JSONDecodeError:
            log.error("Malformed JSON in response: %r", resp.text)
            self.error.emit("Malformed JSON in response")
            return

        if "error" in response_json:
            log.warning(
                "MSA process returned an error:\n%s",
                json.dumps(response_json, indent=2),
            )
            self.error.emit(
                response_json.get(
                    "error_description", response_json.get("error", "Unknown")
                )
            )
            return

        log.debug("We got a token")
        self.status.emit("Token recieved, authenticating with Xbox/Mojang")
        self.token_received.emit(response_json)
