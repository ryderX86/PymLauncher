from enum import StrEnum

class GameVersionType(StrEnum):
    RELEASE = "release"
    SNAPSHOT = "snapshot"
    ALPHA = "old_alpha"
    BETA = "old_beta"