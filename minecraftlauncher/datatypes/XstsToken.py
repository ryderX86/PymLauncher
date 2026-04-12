from dataclasses import dataclass
from datetime import datetime
import json
import logging
import time

import requests
import requests.exceptions

from minecraftlauncher.datatypes.JWT import JWT, decode_jwt
from minecraftlauncher.datatypes.MicrosoftAccount import MicrosoftAccount
from minecraftlauncher.datatypes.XboxToken import XboxToken
from minecraftlauncher.constants import (AZURE_CLIENT_ID, AZURE_SCOPE,
                                         XSTS_AUTH_URL, MSA_REFRESH_URL)
from minecraftlauncher import constants
from minecraftlauncher.exceptions.datatypes import XstsAuthError

log = logging.getLogger(__name__)

class XstsToken:
    json:dict
    """
    Full JSON Xbox Live XSTS token
    """
    token:str
    """
    Xbox Live XSTS token (not the raw JSON, use `.as_json()` or `.json` for that)
    """
    def __init__(self, xbl_token:dict):
        if type(xbl_token) is str:
            try:
                xbl_token = json.loads(xbl_token)
            except json.JSONDecodeError:
                raise TypeError("'xbl_jwt' must be valid JSON if str")
            
        self.json = xbl_token
        self.token = self.json['Token']

        self.expires_at = (datetime
                           .fromisoformat(xbl_token["NotAfter"])
                           .timestamp())
        """
        Unix timestamp version of `NotAfter` in the XSTS token
        """
        self.acquired_at = (datetime
                            .fromisoformat(xbl_token["IssueInstant"])
                            .timestamp())
        """
        Unix timestamp version of `IssueInstant` in the XSTS token
        """

    @classmethod
    def auth(cls, xbl_token:XboxToken):
        if xbl_token.expires_in < 20:
            raise ValueError("Xbox Live token expired alredy!")

        payload = {
            "Properties": {
                "SandboxId": "RETAIL",
                "UserTokens": [
                    xbl_token.token
                ]
            },
            "RelyingParty": "rp://api.minecraftservices.com/",
            "TokenType": "JWT"
        }

        connection_attempts = 0
        response = None
        while connection_attempts < 3:
            connection_attempts += 1
            try:
                response = requests.post(XSTS_AUTH_URL, json=payload)
                response.raise_for_status()
                break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ConnectTimeout) as exc:
                log.warning("%s occured while attempting MSA token refresh"
                            % exc.__qualname__)
                if connection_attempts >= 2:
                    constants.offline_mode = True
                    break
                else:
                    pass
                log.info("Waiting 5 seconds before next attempt...")
                time.sleep(5)
            except requests.HTTPError as exc:
                if exc.errno == 401:
                    if response is None:
                        raise TypeError("Response was given but is still none?")
                    raise XstsAuthError(response.json())
                else:
                    log.error("Failed to refresh MSA token; response code %s"
                          % exc.errno)
                    return False
            # TODO: remove this when verified that the loop won't
            # infinitely continue
            if connection_attempts < 4:
                print("WARNING: Why are we still going?")
                print("(.datatypes.MicrosoftAccount....refresh())")

        if response is None:
            raise Exception("Request to XBL unsuccessful?\
                            (Response doesn't exist!)")

        return cls(response.json())
    
    @property
    def expires_in(self):
        return self.expires_at - datetime.now().timestamp()
    
    @property
    def user_hash(self):
        return self.json["DisplayClaims"]["xui"][0]["uhs"]
    
    def as_json(self):
        return self.json