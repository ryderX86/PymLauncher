from PySide6.QtCore import QThread, Signal


class BaseLoginThread(QThread):
    token_received = Signal(dict)
    error = Signal(str)
    status = Signal(str)
    auth_code_received = Signal()
    """
    We received an auth *code*, not the actual token.
    Close the WebView window if it's open, but we're not done yet.
    """

    def cancel(self):
        raise NotImplementedError
