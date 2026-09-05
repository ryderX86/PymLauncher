from datetime import datetime, timedelta


class TooManyRequestsError(Exception):
    next_request_at: datetime
    wait_timeout: timedelta
    is_continuation: bool

    def __init__(
        self,
        next_request_at: datetime,
        *,
        continuation: bool = False,
    ):
        now = datetime.now()
        self.next_request_at = next_request_at
        self.wait_timeout = next_request_at - now
        self.is_continuation = continuation
        """
        Whether the exception is caused by a 429 cooldown that was already
        happening, or if this is a new one.
        """
        super().__init__(
            "Too many requests to API, next allowed request in "
            f"{self.wait_timeout.total_seconds()}s"
        )
