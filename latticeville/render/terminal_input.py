"""Deprecated terminal input helpers (Textual now handles input)."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class InputEvent:
    kind: str
    key: str | None = None
    x: int | None = None
    y: int | None = None
    button: int | None = None


def read_key() -> InputEvent | None:
    raise RuntimeError("Terminal input is handled by Textual now.")


@contextmanager
def raw_terminal():
    yield
