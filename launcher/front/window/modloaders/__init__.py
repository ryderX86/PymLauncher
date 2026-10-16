from .fabric_install_window import FabricInstallWindow
from .neoforge_install_window import NeoForgeInstallWindow

RELEASE_REGEX = r"[0-9]+\.[0-9]+(\.[0-9]+)?"
SNAPSHOT_REGEX = (
    r"([0-9]+\.[0-9]+(\.[0-9]+)?-((snapshot)|(rc)|(pre))(-?)"
    r"([0-9]+))|([0-9]{1,2}w[0-9]{1,2}[a-z])"
)
OLD_VERSION_REGEX = (
    r"(((rd)|(inf))-[0-9]+)"
    r"|(c[0-9]{1,2}\.[0-9]{1,2}(\.[0-9]{1,2})?[a-c]?(_[0-9]{1,2})?)[a-f]?"
    r"|((a|b)[0-9]{1}\.[0-9]{1,2}(\.[0-9]{1,2})?(_[0-9]{2})?)"
)
