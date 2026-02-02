"""Terminal input helpers shared by Rich viewers."""

from __future__ import annotations

import select
import time
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


_INPUT_BUFFER = ""
_ESC_PENDING_AT: float | None = None


def read_key() -> InputEvent | None:
    global _INPUT_BUFFER
    global _ESC_PENDING_AT
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            break
        chunk = sys.stdin.read(1)
        if chunk == "":
            break
        _INPUT_BUFFER += chunk
        if chunk != "\x1b":
            _ESC_PENDING_AT = None

    if not _INPUT_BUFFER:
        return None

    if _INPUT_BUFFER[0] == "\x1b":
        event, consumed = _parse_escape_sequence(_INPUT_BUFFER)
        if event is None:
            return None
        _INPUT_BUFFER = _INPUT_BUFFER[consumed:]
        return event
    _ESC_PENDING_AT = None

    key = _INPUT_BUFFER[0]
    _INPUT_BUFFER = _INPUT_BUFFER[1:]
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


def _parse_escape_sequence(buffer: str) -> tuple[InputEvent | None, int]:
    global _ESC_PENDING_AT
    if buffer == "\x1b":
        if _ESC_PENDING_AT is None:
            _ESC_PENDING_AT = time.monotonic()
            return None, 0
        if time.monotonic() - _ESC_PENDING_AT < 0.05:
            return None, 0
        _ESC_PENDING_AT = None
        return InputEvent(kind="key", key="ESC"), 1
    if buffer.startswith("\x1b["):
        if len(buffer) < 3:
            return None, 0
        if buffer[2] == "<":
            end_m = buffer.find("m", 3)
            end_M = buffer.find("M", 3)
            end = min(
                [idx for idx in (end_m, end_M) if idx != -1],
                default=-1,
            )
            if end == -1:
                return None, 0
            payload = buffer[3:end]
            char = buffer[end]
            event = _parse_mouse_payload(payload, char)
            _ESC_PENDING_AT = None
            return event, end + 1

        for idx in range(2, len(buffer)):
            char = buffer[idx]
            if char.isalpha() or char == "~":
                seq = buffer[2 : idx + 1]
                event = _parse_csi_sequence(seq)
                _ESC_PENDING_AT = None
                return event, idx + 1
        return None, 0
    if buffer.startswith("\x1bO"):
        if len(buffer) < 3:
            return None, 0
        event = _parse_ss3_sequence(buffer[2])
        _ESC_PENDING_AT = None
        return event, 3
    _ESC_PENDING_AT = None
    return InputEvent(kind="key", key="ESC"), 1


def _parse_csi_sequence(seq: str) -> InputEvent | None:
    if seq == "A":
        return InputEvent(kind="key", key="UP")
    if seq == "B":
        return InputEvent(kind="key", key="DOWN")
    if seq == "C":
        return InputEvent(kind="key", key="RIGHT")
    if seq == "D":
        return InputEvent(kind="key", key="LEFT")
    if seq == "3~":
        return InputEvent(kind="key", key="DELETE")
    return None


def _parse_ss3_sequence(seq: str) -> InputEvent | None:
    if seq == "A":
        return InputEvent(kind="key", key="UP")
    if seq == "B":
        return InputEvent(kind="key", key="DOWN")
    if seq == "C":
        return InputEvent(kind="key", key="RIGHT")
    if seq == "D":
        return InputEvent(kind="key", key="LEFT")
    return None


def _parse_mouse_payload(payload: str, char: str) -> InputEvent | None:
    try:
        parts = payload.split(";")
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
