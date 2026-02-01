"""Terminal input helpers shared by Rich viewers."""

from __future__ import annotations

import select
import sys
import termios
import tty
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
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if not ready:
        return None
    key = sys.stdin.read(1)
    if key == "":
        return None
    if key == "\x1b":
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return InputEvent(kind="key", key="ESC")
        seq = sys.stdin.read(1)
        if seq == "[":
            return _parse_csi()
        return None
    if key in {"\r", "\n"}:
        return InputEvent(kind="key", key="ENTER")
    if key == "\x7f":
        return InputEvent(kind="key", key="BACKSPACE")
    return InputEvent(kind="key", key=key)


@contextmanager
def raw_terminal():
    if not sys.stdin.isatty():
        yield
        return
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        _enable_mouse()
        tty.setcbreak(fd)
        new_settings = termios.tcgetattr(fd)
        new_settings[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
        yield
    finally:
        _disable_mouse()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _parse_csi() -> InputEvent | None:
    seq = sys.stdin.read(1)
    if seq == "A":
        return InputEvent(kind="key", key="UP")
    if seq == "B":
        return InputEvent(kind="key", key="DOWN")
    if seq == "C":
        return InputEvent(kind="key", key="RIGHT")
    if seq == "D":
        return InputEvent(kind="key", key="LEFT")
    if seq == "3":
        end = sys.stdin.read(1)
        if end == "~":
            return InputEvent(kind="key", key="DELETE")
    if seq == "<":
        return _parse_mouse_sgr()
    return None


def _parse_mouse_sgr() -> InputEvent | None:
    buffer = ""
    while True:
        char = sys.stdin.read(1)
        if char in {"m", "M"}:
            break
        buffer += char
    try:
        parts = buffer.split(";")
        button = int(parts[0])
        x = int(parts[1])
        y = int(parts[2])
    except (IndexError, ValueError):
        return None
    if char == "m":
        return None
    return InputEvent(kind="mouse", x=x, y=y, button=button)


def _enable_mouse() -> None:
    sys.stdout.write("\x1b[?1000h\x1b[?1006h")
    sys.stdout.flush()


def _disable_mouse() -> None:
    sys.stdout.write("\x1b[?1000l\x1b[?1006l")
    sys.stdout.flush()
