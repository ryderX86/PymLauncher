from enum import StrEnum
from typing import Literal


class AuthStep(StrEnum):
    MSA = "microsoft"
    XBL = "xbox"
    XSTS = "xsts"
    GTG = "xsts_2"
    MOJ = "moj"


class AuthError:
    __slots__ = ("step", "err", "description")

    def __init__(self, failure_step: AuthStep, errno: int | str, err_desc: str):
        self.step = failure_step
        self.err = errno
        self.description = err_desc

    def __bool__(self) -> Literal[False]:
        return False

    def __eq__(self, a):
        if isinstance(a, type(self)):
            return True
        return False

    def __ne__(self, a):
        return True

    @property
    def error_code(self) -> str:
        match self.err:
            case AuthStep.MSA:
                return "Microsoft authentication"
            case AuthStep.XBL:
                return "Xbox Live authentication"
            case AuthStep.XSTS:
                return "Xbox Secure Token Services"
            case AuthStep.GTG:
                return "Xbox Secure Token Services (rp: http://xboxlive.com)"
            case AuthStep.MOJ:
                return "Mojang authentication"
            case _:
                return "Unknown"

    def err_string(self):
        return (
            "Authentication error occured:\n"
            f" Authentication step: {self.step}\n"
            "Error code: {self.error_code}\n"
            f' Error description: "self.description"'
        )
