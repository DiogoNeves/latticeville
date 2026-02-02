"""Textual app wrapper for Latticeville screens."""

from __future__ import annotations

from textual.app import App
from textual.screen import Screen


class LatticevilleApp(App):
    """Run a single screen in a minimal Textual app."""

    def __init__(self, screen: Screen, *, title: str = "Latticeville") -> None:
        super().__init__()
        self._initial_screen = screen
        self.title = title

    def on_mount(self) -> None:
        self.push_screen(self._initial_screen)
