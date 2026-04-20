class XstsAuthError(Exception):
    comment:str
    xerr:int
    redirect:str
    def __init__(self, xsts_err:dict):
        xerr_num = xsts_err.get("XErr", -1)
        if len(xsts_err.get("Message", "")) < 1:
            match xerr_num:
                case 2148916227:
                    reason = "This account is banned from Xbox Live."
                case 2148916233:
                    reason = (
                        "This account doesn't have an Xbox Live account."
                        "\nPlease go to minecraft.net and sign in to create "
                        "one.")
                case 2148916235:
                    reason = "Xbox Live is not available in the account's region"
                case 2148916236:
                    reason = "Xbox Live needs adult verification in SK."
                case 2148916237:
                    reason = "Xbox Live needs adult verification in SK."
                case 2148916238:
                    reason = "This account must be added to a Microsoft Family "
                    reason += "by an adult to proceed."
                case 2148916262:
                    reason = "Error 2148916262"
                case _:
                    reason = "Unknown error occured while authenticating with XSTS."
        else:
            reason = xsts_err["Message"]

        self.comment = reason
        self.xerr = xerr_num
        self.redirect = xsts_err.get("Redirect", "https://minecraft.net")

        super().__init__("XSTS authentication failed: %s" % self.comment)