import functools
from collections.abc import Callable
from typing import Concatenate, Generic, ParamSpec, TypeVar, overload
from weakref import WeakKeyDictionary

I = TypeVar("I")
P = ParamSpec("P")
R = TypeVar("R")


class _InstanceSuppressable(Generic[I, P, R]):
    parent: "_Suppressable"
    _instance: I | None
    _suppressed: bool

    def __init__(
        self, parent: "_Suppressable[I, P, R]", instance: I | None = None
    ):
        self._parent = parent
        self._instance = instance
        self._suppressed = False
        functools.update_wrapper(self, self._parent._func)  # type: ignore

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R | None:
        if self._suppressed:
            return None
        return self._parent._func(self._instance, *args, **kwargs)  # type: ignore

    def suppress(self):
        self._suppressed = True

    def unsuppress(self):
        self._suppressed = False

    @property
    def suppressed(self):
        return self._suppressed


class _Suppressable(Generic[I, P, R]):
    _func: Callable[Concatenate[I, P], R] | Callable[P, R]
    _suppressed: bool
    _instances: WeakKeyDictionary[I, _InstanceSuppressable[I, P, R]]

    def __init__(
        self, func: Callable[Concatenate[I, P], R] | Callable[P, R]
    ) -> None:
        self._func = func
        self._suppressed = False
        self._instances = WeakKeyDictionary()
        functools.update_wrapper(self, func)  # type: ignore

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R | None:
        if self._suppressed:
            return None
        return self._func(*args, **kwargs)  # type: ignore

    def suppress(self):
        self._suppressed = True

    def unsuppress(self):
        self._suppressed = False

    @property
    def suppressed(self):
        return self._suppressed

    @overload
    def __get__(
        self, instance: I, owner: type[I] | None = None
    ) -> _InstanceSuppressable[I, P, R]: ...

    @overload
    def __get__(
        self, instance: None, owner: type[I] | None = None
    ) -> "_Suppressable[I, P, R]": ...

    def __get__(
        self, instance: I | None, owner=None
    ) -> "_Suppressable[I, P, R]|_InstanceSuppressable[I, P, R]":
        if instance is None:
            return self
        elif instance in self._instances:
            return self._instances[instance]
        self._instances[instance] = _InstanceSuppressable(self, instance)
        return self._instances[instance]


def suppressable(func: Callable[Concatenate[I, P], R] | Callable[P, R]):
    return _Suppressable(func)
