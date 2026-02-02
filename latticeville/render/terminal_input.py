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


_BUFFER = ""
_SEQ_WAIT = 0.02


def read_key() -> InputEvent | None:
    _read_available(0.0)
    if not _BUFFER:
        return None
    event, consumed = _parse_buffer(_BUFFER)
    if event is None and _BUFFER.startswith("\x1b"):
        _read_available(_SEQ_WAIT)
        event, consumed = _parse_buffer(_BUFFER)
    if consumed:
        _consume(consumed)
    return event


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


def _read_available(timeout: float) -> None:
    global _BUFFER
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            break
        chunk = sys.stdin.read(1)
        if chunk == "":
            break
        _BUFFER += chunk
        timeout = 0.0


def _parse_buffer(buffer: str) -> tuple[InputEvent | None, int]:
    if not buffer:
        return None, 0
    if buffer[0] != "\x1b":
        return _parse_single(buffer[0]), 1
    event, consumed = _parse_escape(buffer)
    if event is None and consumed:
        return None, consumed
    if event is None:
        return None, 0
    return event, consumed


def _parse_single(char: str) -> InputEvent | None:
    if char in {"\r", "\n"}:
        return InputEvent(kind="key", key="ENTER")
    if char == "\x7f":
        return InputEvent(kind="key", key="BACKSPACE")
    if char == "\x03":
        return InputEvent(kind="key", key="CTRL_C")
    return InputEvent(kind="key", key=char)


def _parse_escape(buffer: str) -> tuple[InputEvent | None, int]:
    if len(buffer) < 2:
        return None, 0
    if buffer[1] == "[":
        if len(buffer) < 3:
            return None, 0
        if buffer[2] == "<":
            return _parse_mouse(buffer)
        return _parse_csi(buffer)
    if buffer[1] == "O":
        if len(buffer) < 3:
            return None, 0
        event = _parse_ss3(buffer[2])
        return event, 3
    return None, 1


def _parse_csi(buffer: str) -> tuple[InputEvent | None, int]:
    for idx in range(2, len(buffer)):
        char = buffer[idx]
        if char.isalpha() or char == "~":
            seq = buffer[2 : idx + 1]
            return _parse_csi_sequence(seq), idx + 1
    return None, 0


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


def _parse_ss3(seq: str) -> InputEvent | None:
    if seq == "A":
        return InputEvent(kind="key", key="UP")
    if seq == "B":
        return InputEvent(kind="key", key="DOWN")
    if seq == "C":
        return InputEvent(kind="key", key="RIGHT")
    if seq == "D":
        return InputEvent(kind="key", key="LEFT")
    return None


def _parse_mouse(buffer: str) -> tuple[InputEvent | None, int]:
    end_m = buffer.find("m", 3)
    end_M = buffer.find("M", 3)
    end = min([idx for idx in (end_m, end_M) if idx != -1], default=-1)
    if end == -1:
        return None, 0
    payload = buffer[3:end]
    char = buffer[end]
    event = _parse_mouse_payload(payload, char)
    return event, end + 1


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


def _consume(count: int) -> None:
    global _BUFFER
    _BUFFER = _BUFFER[count:]


def _enable_mouse() -> None:
    sys.stdout.write("\x1b[?1000h\x1b[?1006h")
    sys.stdout.flush()


def _disable_mouse() -> None:
    sys.stdout.write("\x1b[?1000l\x1b[?1006l")
    sys.stdout.flush()
