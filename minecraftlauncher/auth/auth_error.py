from enum import StrEnum
from typing import Literal

class AuthStep(StrEnum):
    MSA = "microsoft"
    XBL = "xbox"
    XSTS = "xsts"
    GTG = "xsts_2"
    MOJ = "moj"

class AuthError:
    def __init__(self, failure_step:AuthStep, errno:int|str, err_desc:str):
        self.step = failure_step
        self.err = errno
        self.description = err_desc

    def __bool__(self) -> Literal[False]:
        return False
    
    def __eq__(self, a):
        if type(self) == type(a):
            return True
        return False
    
    def __ne__(self, a):
        return True
    
    @property
    def error_code(self):
        match self.err:
            case AuthStep.MSA:
                "Microsoft authentication"
            case AuthStep.XBL:
                "Xbox Live authentication"
            case AuthStep.XSTS:
                "Xbox Secure Token Services"
            case AuthStep.GTG:
                "Xbox Secure Token Services (rp: http://xboxlive.com)"
            case AuthStep.MOJ:
                "Mojang authentication"
            case _:
                "Unknown"
    
    def __str__(self):
        return "Authentication error occured:\n" \
               " Authentication step: %s\n Error code: %s\n" \
               " Error description: \"%s\"" \
               % (self.step, self.error_code, self.description)