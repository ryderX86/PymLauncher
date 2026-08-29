"""
minecraftlauncher.constants

Probably a better way to do this, but this is
where constant variables that need to be
globally referenced will remain (like the
Azure Client ID)
"""

import os
import platform
import sys
from typing import Literal

DEV = not bool(globals().get("__compiled__", False))

LAUNCHER_NAME = "minecraftlauncher-python"
# LAUNCHER_VERSION is replaced at compile-time
LAUNCHER_VERSION = "dev"
AUTHOR_USR = "ryderX86"
EMAIL = "ryder@r86.me"
APP_SLUG = f"{AUTHOR_USR}.{LAUNCHER_NAME}"

# Authentication URLs
MOJANG_CLIENT_ID = "00000000402B5328"  # Official MC launcher client ID
# "000000004C12AE6F" ?
AZURE_CLIENT_ID = MOJANG_CLIENT_ID
# AZURE_CLIENT_ID = "1c1a9297-d019-48d4-9417-85ea36cf4c1f"
AZURE_SCOPE = "XboxLive.signin XboxLive.offline_access"
if AZURE_CLIENT_ID != MOJANG_CLIENT_ID:
    MS_DEVICE_CODE_URL = (
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
    )
else:
    MS_DEVICE_CODE_URL = "https://login.live.com/oauth20_connect.srf"
if AZURE_CLIENT_ID != MOJANG_CLIENT_ID:
    MS_TOKEN_URL = (
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    )
else:
    MS_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
MSA_REFRESH_URL = "https://login.live.com/oauth20_token.srf"

XBOX_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"

MOJ_AUTH_URL = (
    "https://api.minecraftservices.com/authentication/login_with_xbox"
)
MOJ_AUTH_URL_ALT = "https://api.minecraftservices.com/launcher/login"

WANT_ENCRYPTION = True

# Mojang API URLs
LAUNCH_ENTITLEMENTS_URL = (
    "https://api.minecraftservices.com/entitlements/mcstore"
)
MOJ_PROF_URL = "https://api.minecraftservices.com/minecraft/profile"
SKIN_CHANGE_URL = "https://api.minecraftservices.com/minecraft/profile/skins"
CAPE_URL = "https://api.minecraftservices.com/minecraft/profile/capes/active"
NAME_CHANGE_INFO_URL = (
    "https://api.minecraftservices.com/minecraft/profile/namechange"
)
USERNAME_CHECK_URL = (
    "https://api.minecraftservices.com/minecraft/profile/name/%s/available"
)
"""`%s`"""
USERNAME_CHANGE_URL = (
    "https://api.minecraftservices.com/minecraft/profile/name/%s"
)
"""`%s`"""

# Game assets URLs
VERSION_MANIFEST_URL = (
    "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
)
RESOURCES_URL = "https://resources.download.minecraft.net"
LIBRARIES_URL = "https://libraries.minecraft.net"
JAVA_MANIFEST_URL = (
    "https://launchermeta.mojang.com/v1/products/java-runtime"
    "/2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"
)

PLATFORM = platform.system()
_friendly_plat = " ".join([PLATFORM, platform.version()])

USER_AGENT = (
    f"{AUTHOR_USR}/{LAUNCHER_NAME} {LAUNCHER_VERSION} ({_friendly_plat}) "
    f"(contact: {EMAIL})"
)

# architecture stuff, should get almost all turned into constants by nuitka
OS: Literal["windows", "osx", "linux", "unknown"]
OS_PATH_DELIM: Literal["\\", "/"] = "/"
OS_VER: str = platform.version()
match PLATFORM:
    case "Windows":
        OS = "windows"
        OS_PATH_DELIM = "\\"
    case "Darwin":
        OS = "osx"
    case "Linux":
        OS = "linux"
        OS_VER = platform.release()
    case _:
        OS = "unknown"

ARCH: Literal["x86_64", "x86", "arm64", "unknown"]
if OS != "osx":
    _machine = platform.machine().lower()
else:
    # python docs mention intel macs can give mixed results due to binary diffs
    _machine = "x86_64" if sys.maxsize > 2**32 else "x86"
match _machine:
    case "amd64" | "x86_64":
        ARCH = "x86_64"
    case "aarch64" | "arm64":
        ARCH = "arm64"
    case "i386" | "i686" | "x86" | "x86_32":
        ARCH = "x86"
    case _:
        ARCH = "unknown"

match OS, ARCH:
    case "windows", "x86_64":
        JAVA_OS = "windows-x64"
    case "windows", "arm64":
        JAVA_OS = "windows-arm64"
    case "windows", "x86":
        JAVA_OS = "windows-x86"
    case "osx", "x86_64":
        JAVA_OS = "mac-os"
    case "osx", "arm64":
        JAVA_OS = "mac-os-arm64"
    case "linux", "x86_64":
        JAVA_OS = "linux"
    case "linux", "x86":
        JAVA_OS = "linux-i386"
    case _:
        JAVA_OS = "gamecore"


CLASSPATH_SEPARATOR = ";" if OS == "windows" else ":"

# profile stuff
DEFAULT_JVM_ARGS = (
    "-XX:+UnlockExperimentalVMOptions "
    "-XX:+UseG1GC "
    "-XX:G1NewSizePercent=20 "
    "-XX:G1ReservePercent=20 "
    "-XX:MaxGCPauseMillis=50 "
    "-XX:G1HeapRegionSize=32M "
)

LOG4J_FIX_TIME = "2023-06-07T10:50:16+00:00"
LOG4J_116_5_FIX_MAX_TIME = "2021-06-08T11:00:39+00:00"
LOG4J_17_112_FIX_MAX_TIME = "2017-06-02T13:50:27+00:00"
LOG4J_VULN_MIN_TIME = "2013-09-26T15:11:19+00:00"

LATEST_VERSION_TEXT = "latest-release"
LATEST_SNAPSHOT_TEXT = "latest-snapshot"
LATEST_VERSIONS_SET = {LATEST_VERSION_TEXT, LATEST_SNAPSHOT_TEXT}

# uuids
PROFILE_MHF_STEVE = "c06f89064c8a49119c29ea1dbd1aab82"
STEVE_SKIN_URL = (
    "http://textures.minecraft.net/texture/31f477eb1a7be"
    "ee631c2ca64d06f8f68fa93a3386d04452ab27f43acdf1b60cb"
)
SKIN_URL_BASE = "http://textures.minecraft.net/texture/"

# UI stuff
CHECKMARK_DELAY = 1500  # milliseconds


# feature flags
FLAG_ENABLE_EXPORTING = DEV  # not ready for prod
FLAG_ENABLE_JUMP_LISTS: bool = (
    OS == "windows" and float(OS_VER[:5].rstrip(".")) >= 6.1
)

# other

# average CPU has 4 cores now and most post-2010 CPUs have 2 threads per core
CPU_THREADS = os.cpu_count() or 8
