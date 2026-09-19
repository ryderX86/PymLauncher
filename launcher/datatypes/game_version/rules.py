from typing import Literal, assert_never
import json
import logging

from packaging.version import Version, parse

from launcher import constants

log = logging.getLogger(__name__)

type RuleActionString = Literal["allow", "disallow"]


class OSRule:
    _instances: dict[str, "OSRule"] = {}

    __slots__ = ("allow_on_match", "os", "initialized", "_is_match")
    allow_on_match: bool
    os: dict | None
    initialized: bool
    _is_match: bool | None

    def __new__(cls, action: RuleActionString, os: dict | None = None):
        if not action and not os:
            raise RuntimeError("No arguments provided!")
        args_string = "--".join((action, json.dumps(os)))
        if args_string in cls._instances:
            return cls._instances[args_string]
        new = object.__new__(cls)
        new.initialized = False
        return new

    def __init__(self, action: RuleActionString, os: dict | None = None):
        if self.initialized:
            return
        match action:
            case "allow":
                self.allow_on_match = True
            case "disallow":
                self.allow_on_match = False
            case _:
                assert_never(action)

        self.os = os
        self._is_match = None
        self._instances["--".join((action, json.dumps(os)))] = self
        self.initialized = True

    @property
    def _nomatch(self):
        return not self.allow_on_match

    @property
    def _match(self):
        return self.allow_on_match

    def is_match(self) -> bool:
        if not self.os:
            return True
        name_matches: bool = True
        arch_matches: bool = True
        version_matches: bool = True
        if "name" in self.os:
            name_matches = self.os["name"] == constants.OS
        if "arch" in self.os:
            arch_matches = self.os["arch"] == constants.ARCH
        if "versionRange" in self.os:
            version_matches = self.version_in_allowed_range()

        # check for anything assigned here being false and return nomatch,
        # otherwise at the very end we return match. check for false/none
        # specifically since some rules have only os, some only arch, some both
        # so none is set to prevent NameErrors

        # OS name
        return bool(name_matches and arch_matches and version_matches)

    @property
    def matches(self):
        if self._is_match is not None:
            return self._is_match
        self._is_match = self.is_match()
        return self._is_match

    def version_in_allowed_range(self):
        if not self.os:
            return True
        if "versionRange" not in self.os:
            return True
        elif not isinstance(self.os["versionRange"], dict):
            log.warning("versionRange in rule is not a dict!")
            return True
        match constants.OS:
            case "windows" | "linux":
                ver = parse(constants.OS_VER)
                try:
                    min_ver: Version = parse(
                        self.os["versionRange"].get("min", "0.0.0.0")
                    )
                except Exception as err:
                    log.error(
                        "Error parsing version '%s' to packaging.Version:",
                        self.os["versionRange"].get("min", "0.0.0.0"),
                        exc_info=err,
                    )
                    log.info("Minimum version range set to 0.0.0.0")
                    min_ver = parse("0.0.0.0")
                try:
                    max_ver: Version = parse(
                        self.os["versionRange"].get("max", "999.9.9.9")
                    )
                except Exception as err:
                    log.error(
                        "Error parsing version '%s' to packaging.Version:",
                        self.os["versionRange"].get("max", "999.9.9.9"),
                        exc_info=err,
                    )
                    log.info("Maximum version range set to 999.9.9.9")
                    max_ver = parse("999.9.9.9")
                if "min" in self.os["versionRange"]:
                    mode = "min"
                elif set(self.os["versionRange"].keys()) == {
                    "min",
                    "max",
                }:
                    mode = "minmax"
                elif "max" in self.os["versionRange"]:
                    mode = "max"
                else:
                    log.warning(
                        "Can't determine version rule, downloading for safety."
                    )
                    mode = "skip"
                match mode:
                    case "min":
                        ver_match = ver >= min_ver
                    case "max":
                        ver_match = ver <= max_ver
                    case "minmax":
                        ver_match = max_ver >= ver >= min_ver
                    case _:
                        ver_match = True
            case _:
                log.debug("Unknown version rule, skipping")
                ver_match = True
        return ver_match

    def __repr__(self):
        return json.dumps(self.dict())

    def dict(self):
        return {
            "action": "allow" if self.allow_on_match else "disallow",
            "os": self.os,
        }


class GameRule:
    __slots__ = (
        "allow_on_match",
        "features",
        "_result",
        "args_hash",
    )
    args_hash: str
    allow_on_match: bool
    features: dict[str, bool]
    _result: bool | None

    def __init__(
        self,
        action: RuleActionString,
        features: dict[str, bool],
        current_features: dict[str, bool] | None = None,
    ):
        self._result = None
        match action:
            case "allow":
                self.allow_on_match = True
            case "disallow":
                self.allow_on_match = False
            case _:
                assert_never(action)

        self.features = features
        if current_features:
            self.get_result(current_features)

    def get_result(self, current_features: dict[str, bool] | list[str]):
        if self._result is not None:
            return self._result

        self._result = True
        if isinstance(current_features, dict):
            features = [n for n, v in current_features.items() if v is True]
        else:
            features = current_features

        for name, expected in self.features.items():
            if bool(name in features) is not bool(expected):
                self._result = False
        return self._result

    def dict(self):
        return {
            "action": "allow" if self.allow_on_match else "disallow",
            "features": self.features,
        }

    def repr(self):
        return json.dumps(self.dict())
