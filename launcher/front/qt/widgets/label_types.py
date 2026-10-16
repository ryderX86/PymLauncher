from PySide6.QtWidgets import QLabel


class SecondaryLabel(QLabel):
    """
    Stub class, used to enact the QSS rules for `QLabel[secondary="true"]`
    """


class Header1(QLabel):
    """
    Stub class, used to enact the QSS rules for `QLabel[heading="true"]`
    """

    def __init__(self, text: str, parent=None):
        super().__init__(f"<h1>{text}</h1>", parent)


class Header2(QLabel):
    """
    Stub class, used to enact the QSS rules for `QLabel[h2="true"]`
    """

    def __init__(self, text: str, parent=None):
        super().__init__(f"<h2>{text}</h2>", parent)


class Subheading(QLabel):
    """
    Stub class, used to enact the QSS rules for `QLabel[subheading="true"]`
    """


class SectionLabel(QLabel):
    """
    Stub class, used to enact the QSS rules for `QLabel[section="true"]`
    """
