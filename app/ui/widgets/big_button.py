"""Gros bouton tactile. `variant` : primary, secondary ou danger (voir theme.py)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton


class BigButton(QPushButton):
    def __init__(self, text: str, variant: str = "primary", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("variant", variant)
        self.setMinimumSize(260, 90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # pas de cadre de focus au doigt
