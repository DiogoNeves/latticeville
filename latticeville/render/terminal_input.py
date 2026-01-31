"""Terminal input helpers shared by Rich viewers."""

from __future__ import annotations

import select
import sys
import termios
import tty
from contextlib import contextmanager


def read_key() -> str | None:
    if not sys.stdin.isatty():
        return None
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if not ready:
        return None
    key = sys.stdin.read(1)
    if key == "\x1b":
        seq = sys.stdin.read(2)
        if seq == "[A":
            return "UP"
        if seq == "[B":
            return "DOWN"
        return None
    if key in {"\r", "\n"}:
        return "ENTER"
    return key


@contextmanager
def raw_terminal():
    if not sys.stdin.isatty():
        yield
        return
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
