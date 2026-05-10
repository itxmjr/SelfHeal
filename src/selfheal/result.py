from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar, cast

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")

_MISSING = object()


@dataclass(frozen=True)
class Result(Generic[T, E]):
    _value: T | object = _MISSING
    _error: E | object = _MISSING

    @classmethod
    def ok(cls, value: T) -> Result[T, E]:
        return cls(_value=value)

    @classmethod
    def err(cls, error: E) -> Result[T, E]:
        return cls(_error=error)

    def is_ok(self) -> bool:
        return self._error is _MISSING

    def is_err(self) -> bool:
        return not self.is_ok()

    @property
    def value(self) -> T:
        if self.is_err():
            raise ValueError("cannot access value on an error Result")
        return self._value  # type: ignore[return-value]

    @property
    def error(self) -> E:
        if self.is_ok():
            raise ValueError("cannot access error on an ok Result")
        return self._error  # type: ignore[return-value]

    def map(self, func: Callable[[T], U]) -> Result[U, E]:
        if self.is_err():
            return Result.err(self.error)
        return Result.ok(func(self.value))

    def flat_map(self, func: Callable[[T], Result[U, F]]) -> Result[U, E | F]:
        if self.is_err():
            return Result.err(self.error)
        return cast(Result[U, E | F], func(self.value))
