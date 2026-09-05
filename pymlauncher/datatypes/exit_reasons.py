import logging
import sys
from enum import StrEnum
from typing import Literal, Never, overload

log = logging.getLogger(__name__)


class ExitReasons(StrEnum):
    """
    Exit code meanings, where we attach descriptions
    and internal values together to give in a separate function.
    """

    SUCCESS = (
        "This shouldn't ever be shown. "
        "Please file a bug report and include your launcher logs."
    )
    """
    This shouldn't ever be shown to a user unless something gets screwed up
    with the Qt signals
    """

    UNKNOWN = (
        "An unknown error occured. "
        "Check your game logs for more information."
    )

    NORMAL_GAME_CRASH = "A game crash occured. Read below for more details."

    DAMAGED_GAME_FILES = (
        "The game files may be corrupted, or invalid settings were applied "
        "to the game."
    )

    SIGSEGV = (
        "The Minecraft process attempted to access a memory address "
        "belonging to another program, and was shut down by the system."
    )

    UNKNOWN_255 = "An unknown error occured. (Exit code >=255)"

    MISUSE_BUILTINS = "Misuse of OS builtins."

    COMMAND_CANNOT_EXECUTE = "Command could not execute."

    COMMAND_NOT_FOUND = "The Java executable couldn't be found."

    INVALID_ARGUMENT = "An invalid launch argument was provided."

    JVM_FATAL_ERROR = "The Java Virtual Machine ran into an unexpected error."

    JVM_HS_ERROR = (
        "The Java Virtual Machine ran into an unexpected error.\n"
        'Check for a file called "hs_err_pid<...>.log" for more details.'
    )
    """
    When this comes up, the file 'hs_err_pid<process id>.log' should be checked
    for in the game directory, and the user's desktop, and shown to the user in
    this message if it can be found, otherwise use a visible
    placeholder/instructions to find it.
    
    (Use `ExitReasons.JVM_HS_ERROR.formatted()` for this.)
    """

    NO_EXECUTE_PERMISSIONS = (
        "You don't have permissions to execute the binary at {}.\nPlease make "
        "sure it is marked as executable and accessible by your user."
    )
    """
    When this comes up, format it with
    `ExitReasons.NO_EXECUTE_PERMISSIONS.formatted()`
    """

    INTENTIONAL_CRASH = "It appears you intentionally crashed the game."

    NVIDIA_CRASH = (
        "An error occured with your Nvidia drivers, please ensure "
        "they're up to date."
    )

    OUT_OF_MEMORY = (
        "The game ran out of memory. Please check and ensure you have "
        "allocated enough memory to Minecraft."
    )

    SHOULD_NEVER_HAPPEN_ERRORS = "This shouldn't be possible."
    """System shutdown termination (win32 only); std::abort; etc."""

    ACCESS_VIOLATION = "The JVM encountered a fatal error (access violation)."

    STACK_BUFFER_OVERRUN = "The JVM encountered a fatal error (buffer overrun)"

    HEAP_CORRUPTION = "The JVM encountered a fatal error (heap corruption)"

    MALFORMED_JAVA_INSTALL = (
        "The Java installation may be corrupted or your Windows installation "
        "may have a corrupted registry."
    )

    OUTDATED_OSX_ERROR = (
        "Your verison of macOS is too old for this version of Minecraft."
    )

    D3DGEAR_CRASH = (
        "Check any third party software (especially screen video "
        'recording software) for settings regarding "hooking" into processes'
    )

    WIN32_TERMINATED = "Windows terminated the program."

    SIGINT = (
        "The operating system has killed the process associated with the game."
    )

    @overload
    def formatted(
        self: Literal[
            ExitReasons.JVM_HS_ERROR, ExitReasons.NO_EXECUTE_PERMISSIONS
        ],
        filepath: str,
        /,
    ) -> str: ...

    @overload
    def formatted(self, *args: str) -> Never: ...

    def formatted(self, *args: str):
        cls = type(self)
        match self:
            case cls.JVM_HS_ERROR:
                ln1 = str(self).splitlines()[0]
                ln2 = f"Check {args[0]} for more information."
                return "\n".join((ln1, ln2))
            case cls.NO_EXECUTE_PERMISSIONS:
                return self.format(*args)
            case _:
                raise NotImplementedError()

    @classmethod
    def from_exit_code(cls, code: int):
        if sys.platform == "linux" and -64 <= code < 0:
            code = code + 128
        elif sys.platform == "win32" and code != abs(code):
            # simplify the list by wrapping codes to positive/signed numbers
            code = code & 0xFFFFFFFF
        elif code < -1:
            log.warning(
                "Can't determine what this error code is supposed to be! (%d)",
                code,
            )
        match code:
            case 0:
                log.warning(
                    "Checking against exit code 0, something went wrong "
                    "somewhere."
                )
                return cls.SUCCESS
            case 1:
                return cls.NORMAL_GAME_CRASH
            case 2:
                return cls.INVALID_ARGUMENT
            case 126 if sys.platform != "win32":
                return cls.NO_EXECUTE_PERMISSIONS
            case 127:
                return cls.COMMAND_NOT_FOUND
            case 130 | 143 | 15:
                # Java normally adds +128 to exit codes, so
                # it should always be 143 for a SIGINT, but
                # just in case we'll keep 15 for now.
                return cls.SIGINT
            case 134 if sys.platform == "darwin":
                return cls.ACCESS_VIOLATION
            case 134:
                return cls.JVM_HS_ERROR
            case 3 | 137 | 3489660927:
                # 3: -XX:+ExitOnOutOfMemoryError
                return cls.OUT_OF_MEMORY
            case 139 if sys.platform == "darwin":
                return cls.OUTDATED_OSX_ERROR
            case 139:
                return cls.SIGSEGV
            case 225:
                return cls.DAMAGED_GAME_FILES
            case 255 if sys.platform == "win32":
                return cls.WIN32_TERMINATED
            case 255:
                return cls.UNKNOWN_255
            # windows-only: (POSIX exit codes can't be >255)
            case 805306369 | 1073807364:
                # 0x30000001 & 0x40010004
                return cls.WIN32_TERMINATED
            case 2147483651:  # 0x80000003
                return cls.MALFORMED_JAVA_INSTALL
            case 3221226505:  # 0xC0000409
                return cls.STACK_BUFFER_OVERRUN
            case 3221226519:  # 0xC0000417
                return cls.D3DGEAR_CRASH
            case 3221225477:  # 0xC0000005
                return cls.ACCESS_VIOLATION
            case 3221226356:  # 0xC0000374
                return cls.HEAP_CORRUPTION
            case 1073741845:  # 0x40000015
                log.warning(
                    "Checking against exit code %d, something went wrong.",
                    code,
                )
                return cls.SHOULD_NEVER_HAPPEN_ERRORS
            case 4294967295:  # 0xFFFFFFFF
                return cls.INTENTIONAL_CRASH
            # NVIDIA drivers
            case 0x6E760038 | 0x6E76003B | 0x6E760034:
                # fun fact: "\x6e\x76" decodes from utf-8 to "nv"
                return cls.NVIDIA_CRASH
            case _:
                return cls.UNKNOWN
