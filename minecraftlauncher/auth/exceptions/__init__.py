import logging

import requests

from minecraftlauncher import constants

from .name_change_error import NameChangeError
from .too_many_requests_error import TooManyRequestsError

log = logging.getLogger(__name__)


class BaseAuthenticationException(Exception):
    response: requests.Response | None

    _msg = "Failed to authenticate due to an unknown error."

    def __init__(
        self, response: requests.Response | None = None, msg: str | None = None
    ):
        if msg:
            super().__init__(msg)
        else:
            super().__init__(self._msg)
        self.response = response


class XstsAuthError(BaseAuthenticationException):
    comment: str
    xerr: int
    redirect: str

    def __init__(self, xsts_err: dict):
        xerr_num = xsts_err.get("XErr", -1)
        if len(xsts_err.get("Message", "")) < 1:
            match xerr_num:
                case 2148916227:
                    reason = "This account is banned from Xbox Live."
                case 2148916233:
                    reason = (
                        "This account doesn't have an Xbox Live account."
                        "\nPlease go to minecraft.net and sign in to create "
                        "one."
                    )
                case 2148916235:
                    reason = (
                        "Xbox Live is not available in the account's region"
                    )
                case 2148916236:
                    reason = "Xbox Live needs adult verification in SK."
                case 2148916237:
                    reason = "Xbox Live needs adult verification in SK."
                case 2148916238:
                    reason = (
                        "This account must be added to a Microsoft Family "
                    )
                    reason += "by an adult to proceed."
                case 2148916262:
                    reason = "Error 2148916262"
                case _:
                    reason = (
                        "Unknown error occured while authenticating with XSTS."
                    )
        else:
            reason = xsts_err["Message"]

        self.comment = reason
        self.xerr = xerr_num
        self.redirect = xsts_err.get("Redirect", "https://minecraft.net")

        super().__init__(None, f"XSTS authentication failed: {self.comment}")


class NoConnectionError(BaseAuthenticationException):
    _msg = "There appears to be a problem with your internet connection."

    # instance attributes
    original_request: requests.Request | requests.PreparedRequest | None
    url: str
    """The URL that a connection attempt failed to"""
    cause: BaseException
    """The original exception that this was raised from"""

    def __init__(
        self,
        url: str,
        cause: BaseException,
        msg: str | None = None,
        original_request: (
            requests.Request | requests.PreparedRequest | None
        ) = None,
    ):
        if msg:
            super().__init__(msg=msg)
        else:
            super().__init__()
        self.cause = cause
        self.url = url
        self.original_request = original_request


class UnauthorizedError(BaseAuthenticationException):
    _msg = "An issue has occured while authenticating. Please log in again."


class MSABaseAuthenticationException(BaseAuthenticationException):
    default_errcode: str | list[str] | set[str] = "<unknown>"
    """
    The error code that should result in use of this exception.

    Used for automatic retrieval of the proper error type in
    `get_exception_type()`
    """

    error_codes: list[int]
    error_primary: str
    description: str
    error_uri: str
    trace_id: str
    correlation_id: str
    original_response: requests.Response
    trigger: str
    """What triggered the raising of this error"""

    def __init__(
        self, response: requests.Response, trigger: str | None = None
    ):
        super().__init__(response)
        try:
            resp_json: dict = response.json()
        except Exception as err:
            log.warning(
                "Failed to parse response JSON from MS API error: %r",
                type(err).__name__,
            )
            resp_json = {}
        self.error_codes = resp_json.get("error_codes", [-1])
        self.error_primary = resp_json.get("error", "N/A")
        self.description = resp_json.get(
            "error_description", "<Couldn't get error description>"
        )
        self.error_uri = resp_json.get("error_uri", "N/A")
        self.trace_id = resp_json.get("trace_id", "N/A")
        self.correlation_id = resp_json.get("correlation_id", "N/A")
        self.original_response = response
        self.trigger = trigger or "Unknown"

    @classmethod
    def get_exception_type(
        cls,
        response: requests.Response,
    ) -> type:
        try:
            j: dict = response.json()
        except Exception as err:
            err.add_note("Failed to get JSON for get_exception_type()")
            raise err
        primary: str = j.get("error", "N/A")
        subclasses = cls.__subclasses__()
        for subclass in subclasses:
            if (
                isinstance(subclass.default_errcode, str)
                and subclass.default_errcode == primary
            ):
                return subclass
            elif isinstance(subclass.default_errcode, (list, set)) and any(
                a == primary for a in subclass.default_errcode
            ):
                return subclass
        log.warning(
            "Couldn't get proper subclass for error code %r, "
            "returning default.",
            primary,
        )
        return cls

    def __str__(self):
        return f"{self._msg} (error code: {self.error_primary})"


class MSAInvalidRequestError(MSABaseAuthenticationException):
    default_errcode = "invalid_request"
    _msg = "A protocol error has occured. Please submit a bug report."


class MSAInvalidSessionError(MSABaseAuthenticationException):
    default_errcode = {"interaction_required", "invalid_grant"}
    _msg = "Session expired. Please log in again."


class MSAInvalidScopeError(MSABaseAuthenticationException):
    default_errcode = {"invalid_scope", "unsupported_grant_type"}
    _msg = (
        "The launcher provided the API with invalid information. "
        f"Please submit a bug report. (Scope: {constants.AZURE_SCOPE!r})"
    )


class MSAServerUnavailableError(MSABaseAuthenticationException):
    default_errcode = "temporarily_unavailable"
    _msg = (
        "The Microsoft authentication server is currently unavailable, "
        "retrying after some time..."
    )


class MSAAccessDeniedError(MSABaseAuthenticationException):
    default_errcode = {
        "consent_required",
        "unauthorized_client",
        "invalid_client",
    }
    _msg = "Access denied. Please log in again."
