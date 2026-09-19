from typing import assert_never
import json
import logging

from .rules import GameRule, OSRule, RuleActionString

log = logging.getLogger(__name__)


class JVMLaunchArg:
    __slots__ = ("value", "rules")
    value: list[str]
    rules: list[OSRule]

    def __init__(self, value: list[str], rules: list[OSRule]):
        self.value = value
        self.rules = rules

    def allowed(self):
        if not self.rules:
            return True
        result = False
        for rule in self.rules:
            if rule.matches:
                result = rule.allow_on_match
        return result

    def __str__(self):
        return " ".join(a.strip() for a in self.value)

    def __repr__(self):
        return json.dumps(self.dict())

    def dict(self):
        return {"rules": [r.dict() for r in self.rules], "value": self.value}

    @classmethod
    def parse_dict(cls, arg: dict | str) -> "JVMLaunchArg|str":
        if isinstance(arg, dict) and "value" not in arg:
            raise ValueError(f"Invalid argument: {arg!r}")
        if isinstance(arg, str):
            return arg.strip()
        elif isinstance(arg, dict) and "rules" not in arg:
            arg_list: str | list = arg["value"]
            if isinstance(arg_list, list):
                args_out = []
                for a in arg_list:
                    match a:
                        case list():
                            sublist = []
                            for x in arg:
                                if x.startswith("-Xms") or x.startswith(
                                    "-Xmx"
                                ):
                                    continue
                                sublist.append(x)
                            args_out.append(sublist)
                        case str() if not (
                            a.startswith("-Xmx") or a.startswith("-Xms")
                        ):
                            args_out.append(a)
                return " ".join(arg_list)
            return arg_list
        value: str | list[str] = arg.get("value", [])
        if isinstance(value, str):
            value = [value.strip()]
        else:
            value = [a.strip() for a in value]
        if not value:
            log.warning("Parsed JVM argument %r has no value!", arg)
            return ""
        elif "rules" not in arg:
            return " ".join(value)
        rules: list[OSRule] = []
        for rule in arg.get("rules", []):
            if not isinstance(rule, dict):
                log.warning(
                    "Unexpected JVM argument rule type: %r",
                    type(rule).__name__,
                )
                continue
            action = rule.get("action", "<null>")
            if action not in {"allow", "disallow"}:
                log.warning("Unexpected rule action: %r", action)
                continue
            if "os" not in rule or not rule.get("os"):
                log.warning("No OS parameter for JVM argument rule!")
                continue
            os = rule["os"]
            if not isinstance(os, dict):
                log.warning(
                    "Unexpected type for 'os' in JVM argument rule: %r",
                    type(os).__name__,
                )
                continue
            rules.append(OSRule(action, os))
        if not rules:
            log.warning(
                "No rules to be checked for %r; returning string.", arg
            )
            return " ".join(value)
        return cls(value, rules)

    def string(self):
        return str(self)


class GameLaunchArg:
    __slots__ = ("value", "rules", "_allowed")
    value: list[str]
    rules: list[GameRule]
    _allowed: bool | None

    def __init__(self, value: str | list[str], rules: list[GameRule]):
        if isinstance(value, str):
            self.value = [value]
        else:
            self.value = value

        self.rules = rules
        self._allowed = None

    def get_result(self, current_features: dict[str, bool] | list[str]):
        if not self.rules:
            return True
        result = False
        for rule in self.rules:
            if rule.get_result(current_features):
                result = True
        return result

    @classmethod
    def parse(cls, arg: dict | str):
        if isinstance(arg, str):
            return arg
        elif "value" not in arg:
            log.warning("No value in argument %r!", arg)
            return ""
        rules: list[GameRule] = []
        for r in arg.get("rules", []):
            if not isinstance(r, dict):
                log.warning(
                    "Unexpected game argument rule type: %r", type(r).__name__
                )
                continue
            action: RuleActionString = r.get("action", "<null>")
            if action not in {"allow", "disallow"}:
                log.warning("Unexpected game argument rule action: %r", action)
                continue
            features: dict | None = r.get("features")
            if not features:
                log.warning("Game argument rule has no features required")
                continue
            rules.append(GameRule(action, features))
        if not rules:
            log.warning(
                "No rules were able to be parsed for dict %r, "
                "returning as string.",
                arg,
            )
            value: str | list[str] = arg["value"]
            match value:
                case list():
                    return " ".join(value)
                case str():
                    return value
                case _:
                    assert_never(value)
        return cls(arg["value"], rules)

    def string(self):
        return " ".join(self.value)
