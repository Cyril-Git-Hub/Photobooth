"""Clavier virtuel intégré à l'application (n'utilise pas le clavier Windows)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ...core.keyboards import Key
from ..scale import px


class KeyButton(QPushButton):
    def __init__(self, label: str, parent=None, compact: bool = False) -> None:
        super().__init__(label, parent)
        self.setProperty("variant", "key")
        if compact:
            self.setObjectName("compactKeyButton")
        self.setMinimumHeight(px(54 if compact else 76))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # le clavier ne vole jamais le focus
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


class VirtualKeyboard(QWidget):
    """Émet ce que l'invité tape ; c'est l'écran qui décide quoi en faire (voir TextBuffer)."""

    text_typed = pyqtSignal(str)
    backspace_pressed = pyqtSignal()
    clear_pressed = pyqtSignal()

    def __init__(self, rows: list[list[Key]], parent=None, compact: bool = False) -> None:
        super().__init__(parent)
        self.buttons: list[tuple[Key, KeyButton]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(0), px(0), px(0), px(0))
        layout.setSpacing(px(5 if compact else 10))
        if compact:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for row in rows:
            line = QHBoxLayout()
            line.setSpacing(px(5 if compact else 10))
            for key in row:
                button = KeyButton(key.label, compact=compact)
                button.clicked.connect(lambda _checked=False, k=key: self.press(k))
                line.addWidget(button, key.weight)
                self.buttons.append((key, button))
            layout.addLayout(line)

    def press(self, key: Key) -> None:
        if key.action == "backspace":
            self.backspace_pressed.emit()
        elif key.action == "clear":
            self.clear_pressed.emit()
        else:
            self.text_typed.emit(key.insert_text)
