"""
Class/instance of a config loader/saver
"""

from enum import EnumType, IntEnum, StrEnum
from typing import Any, Callable, Union, get_args, get_type_hints
import json
import logging
import os
import re

from launcher import constants
from launcher.functions import reswrite
import launcher._paths

# pylint: disable-next=protected-access
paths = launcher._paths.paths

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


_PERCENT_RE = r"(\B(%\(([^{}]+)\)s))+"
_FSTRING_RE = r"(\B(\{([^{}]+)\}))+"
VALID_FORMAT_NAMES = {"timestamp", "logger", "thread", "level", "message"}


class ConfigHolder:
    class ConfigHolderAttrManager:
        parent_anno: None | dict[str, type]

        def __new__(cls, *args, **kwargs):
            if cls.parent_anno is None:
                cls.parent_anno = get_type_hints(ConfigHolder)
            return super().__new__(cls)

        def __init__(
            self, parent: ConfigHolder, attr_name: str, expected_type: type
        ):
            self._parent = parent
            self._attr = attr_name
            assert self.parent_anno
            if expected_type != self.parent_anno[attr_name]:
                if issubclass(expected_type, self.parent_anno[attr_name]):
                    pass
                else:
                    log.warning(
                        "ConfigHolderAttrManager: Attribute %r has type "
                        "%s annotated, got %s.",
                        attr_name,
                        expected_type.__name__,
                        self.parent_anno[attr_name].__name__,
                    )

        def set(self, value: Any):
            setattr(self._parent, self._attr, value)
            return

        def get(self) -> Any | None:
            getattr(self._parent, self._attr, None)

    class GameLogTemplateType(StrEnum):
        PERCENT = "%s"
        FORMAT = "{}"
        UNKNOWN = "<unknown>"
        DEFAULT = "\x00"

        @classmethod
        def _missing_(cls, value: object):
            return cls.UNKNOWN

    # meta
    active: bool = False

    PostLaunchBehavior = PostLaunchBehavior
    JarRedownloadBehavior = JarRedownloadBehavior

    # config items
    window_size: list[int]
    use_device_code_for_logins: bool
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
    Whether or not old releases (pre-alpha, alpha, beta, etc.) should be shown
    in the versions list.
    """
    use_webview_for_login: bool
    """
    Whether or not to use a webview for login dialogs. If `True`, the default
    web browser won't be opened, and a pop-up window with a QWebView will be
    used instead.
    """
    lock_profile_order: bool
    theme: str
    icon_theme: str
    always_show_debug_options: bool
    disable_lzma_downloads: bool
    logging_template: str | None

    def __init__(self):
        # config items; defaults
        self.window_size = [1100, 700]
        self.use_device_code_for_logins = False
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
        self.use_webview_for_login = constants.FLAG_ENABLE_WEBVIEW
        self.lock_profile_order = False
        self.theme = "default"
        self.always_show_debug_options = False
        self.disable_lzma_downloads = False
        self.icon_theme = "\x00"  # see launcher.front.qt.icon_helpers:261
        self.logging_template = None

    @classmethod
    def coerce_enum(cls, val: int | str, type_: EnumType):
        return type_(val)  # type: ignore

    def load(self):
        if not os.path.isfile(paths.config_file):
            log.info("Config file doesn't exist, creating it.")
            if not os.path.isdir(os.path.dirname(paths.config_file)):
                os.makedirs(os.path.dirname(paths.config_file), exist_ok=True)
            self.save()
            type(self).active = True
            return

        log.debug("Loading config file from %r...", paths.config_file)
        with open(paths.config_file) as file:
            text = file.read()
        try:
            obj: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as err:
            log.error("Failed to read config file:", exc_info=err)
            raise RuntimeError(
                f"Failed to read config file! ({type(err).__name__!r})"
            ) from err

        _all = dir(self)
        issues: int = 0
        self_hints = get_type_hints(type(self))
        for key, val in obj.items():
            if key not in _all:
                log.warning(
                    "Skipping unknown config entry %r (value: %r)", key, val
                )
                issues += 1
                continue
            elif isinstance(self_hints[key], EnumType):  # enum hack
                if val in self_hints[key]:
                    setattr(
                        self,
                        key,
                        self.coerce_enum(val, self_hints[key]),
                    )
                    continue
                else:
                    log.warning(
                        "Unexpected value for %r: %r",
                        self_hints[key],
                        val,
                    )
                    continue
            elif isinstance(getattr(self, key), set) and isinstance(val, list):
                val = set(val)  # set() hack
            elif (
                isinstance(self_hints[key], Union)
                and (not get_args(a) for a in get_args(self_hints[key]))
                and type(val) in get_args(self_hints[key])
            ):
                pass
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
        reswrite(paths.config_file, json.dumps(self.as_dict(), indent=2))

    def get_mgr(self, attr_name: str, type_: Any):
        return self.ConfigHolderAttrManager(self, attr_name, type_)

    @classmethod
    def determine_log_template_format(cls, template: str):
        if not template:
            return (cls.GameLogTemplateType.DEFAULT,)
        percent_matches = re.findall(_PERCENT_RE, template)
        fstring_mathces = re.findall(_FSTRING_RE, template)
        invalid_matches = []
        percent_match_count = 0
        fstring_match_count = 0
        for _, _, name in percent_matches:
            if name not in VALID_FORMAT_NAMES:
                invalid_matches.append(name)
            else:
                percent_match_count += 1
        for _, _, name in fstring_mathces:
            if name not in VALID_FORMAT_NAMES:
                invalid_matches.append(name)
            else:
                fstring_match_count += 1

        if percent_match_count > fstring_match_count:
            type_ = cls.GameLogTemplateType.PERCENT
        elif percent_match_count < fstring_match_count:
            type_ = cls.GameLogTemplateType.FORMAT
        else:
            type_ = cls.GameLogTemplateType.UNKNOWN

        return (type_, *invalid_matches)


config = ConfigHolder()
