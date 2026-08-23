"""
Class/instance of a config loader/saver
"""

from typing import Any, Callable, get_type_hints
from enum import IntEnum, EnumType
import json
import logging

from .paths import paths
from .functions import reswrite

log = logging.getLogger(__name__)


class PostLaunchBehavior(IntEnum):
    KEEP_OPEN = 0
    HIDE = 1
    CLOSE_WHEN_DONE = 2
    CLOSE = 3


class JarRedownloadBehavior(IntEnum):
    NEVER = 0
    REDOWNLOAD = 1
    REDOWNLOAD_ONCE = 2


class ConfigHolder:
    # meta
    active: bool = False

    PostLaunchBehavior = PostLaunchBehavior
    JarRedownloadBehavior = JarRedownloadBehavior

    # config items
    window_size: list[int]
    open_browser_for_login: bool
    copy_code_for_login: bool
    post_launch_option: PostLaunchBehavior
    redownload_option: JarRedownloadBehavior
    """
    Should we re-download assets/executables without a SHA1/SHA256 hash?

    Can check with `if <ConfigHolder>.redownload_option`, since the only option
    to not re-download items is an enum with a value of `0`.
    """
    maximized: bool
    tooltip_icons_enabled: bool
    ignored_messages: set[int]
    jump_list_items: list[str]
    """
    WINDOWS-ONLY: Profiles
    """
    dialog_answers: dict[str, bool]
    show_animation_on_skin_dialog: bool
    show_logs_on_home: bool
    allow_audio: bool
    enforce_json_spec: bool
    show_snapshots: bool
    """
    Whether or not snapshots/pre-releases should be shown in the versions list.
    """
    show_old_releases: bool
    """
    Whether or not old releases (pre-alpha, alpha, beta, etc.) should be shown in
    the versions list.
    """

    def __init__(self):
        # config items
        self.window_size = [1100, 700]
        self.open_browser_for_login = False
        self.copy_code_for_login = True
        self.post_launch_option = PostLaunchBehavior.HIDE
        self.redownload_option = JarRedownloadBehavior.REDOWNLOAD
        self.maximized = False
        self.tooltip_icons_enabled = True
        self.ignored_messages = set()
        self.jump_list_items = []
        self.dialog_answers = {}
        self.show_animation_on_skin_dialog = False
        self.show_logs_on_home = False
        self.allow_audio = True
        self.enforce_json_spec = False
        self.show_snapshots = True
        self.show_old_releases = True

    @classmethod
    def coerce_enum(cls, val: int | str, type_: EnumType):
        return type_(val)

    def load(self):
        log.debug("Loading config file from %r...", paths.config_file)
        with open(paths.config_file) as file:
            text = file.read()
        try:
            obj: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as err:
            log.error("Failed to read config file:", exc_info=err)
            raise RuntimeError(
                f"Failed to read config file! ({type(err)!r})"
            ) from err

        _all = dir(self)
        issues: int = 0
        for key, val in obj.items():
            if key not in _all:
                log.warning(
                    "Skipping unknown config entry %r (value: %r)", key, val
                )
                issues += 1
                continue
            elif isinstance(
                get_type_hints(type(self))[key], EnumType
            ):  # enum hack
                if val in get_type_hints(type(self))[key]:
                    setattr(
                        self,
                        key,
                        self.coerce_enum(val, get_type_hints(type(self))[key]),
                    )
                    continue
                else:
                    log.warning(
                        "Unexpected value for %r: %r",
                        get_type_hints(type(self))[key],
                        val,
                    )
                    continue
            elif isinstance(getattr(self, key), set) and isinstance(val, list):
                val = set(val)  # set() hack
            elif not isinstance(val, type(getattr(self, key))):
                log.warning(
                    "Skipping config entry %r due to mismatching type: "
                    "Expected type %r, got %r",
                    key,
                    type(getattr(self, key)),
                    type(val),
                )
                issues += 1
                continue
            setattr(self, key, val)
        if issues:
            log.warning("Loaded config with %s issues", issues)
        else:
            log.debug("Loaded config with no issues")
        type(self).active = True

    def as_dict(self):
        output = {}
        for key, val in self.__dict__.items():
            if isinstance(val, Callable):
                continue
            elif isinstance(val, set):
                output[key] = [*val]
                output[key].sort()
            else:
                output[key] = val
        return output

    def save(self):
        reswrite(paths.config_file, json.dumps(self.as_dict()))


config = ConfigHolder()
