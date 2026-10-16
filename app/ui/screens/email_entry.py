"""Adresse mail : confirmation ou correction de celle de la liste, ou saisie, au clavier virtuel."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from ...core.emails import MSG_INVALID, is_valid_email, normalize_email
from ...core.keyboards import EMAIL_ROWS
from ...core.text_buffer import TextBuffer
from ..widgets.big_button import BigButton
from ..widgets.virtual_keyboard import VirtualKeyboard
from .base import BaseScreen
from ..scale import px


class EmailEntryScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._buffer = TextBuffer(max_length=80, allow_space=False)

        self._heading = QLabel("Ton adresse mail")
        self._heading.setObjectName("heading")
        self._heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note = QLabel("")
        self._note.setObjectName("note")
        self._note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._field = QLabel("")
        self._field.setObjectName("mailfield")
        self._field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error = QLabel("")
        self._error.setObjectName("error")
        self._error.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._keyboard = VirtualKeyboard(EMAIL_ROWS)
        self._keyboard.text_typed.connect(self._on_text)
        self._keyboard.backspace_pressed.connect(self._on_backspace)
        self._keyboard.clear_pressed.connect(self._on_clear)

        back = BigButton("Retour", "secondary")
        back.clicked.connect(lambda: self.nav.go_back())
        self._skip = BigButton("Passer", "secondary")
        self._skip.clicked.connect(lambda: self._on_skip())
        validate = BigButton("Valider")
        validate.clicked.connect(lambda: self._on_validate())
        buttons = QHBoxLayout()
        buttons.setSpacing(px(24))
        buttons.addStretch(1)
        for button in (back, self._skip, validate):
            buttons.addWidget(button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(40), px(24), px(40), px(24))
        layout.setSpacing(px(10))
        layout.addWidget(self._heading)
        layout.addWidget(self._note)
        layout.addWidget(self._field)
        layout.addWidget(self._error)
        layout.addStretch(1)
        layout.addWidget(self._keyboard)
        layout.addLayout(buttons)

    def on_enter(self) -> None:
        first_name = self.session.guest_first_name
        known = bool(self.session.email)
        self._buffer.set(self.session.email)
        self._heading.setText(f"Salut {first_name} !" if first_name else "Ton adresse mail")
        self._note.setText("Vérifie ton adresse mail, et corrige-la si besoin." if known
                           else "Écris ton adresse mail pour recevoir ta photo.")
        self._skip.setVisible(not self.config.mail_obligatoire)
        self._error.setText("")
        self._refresh()

    def _refresh(self) -> None:
        self._field.setText(self._buffer.value + "|")

    def _on_text(self, text: str) -> None:
        self._error.setText("")
        self._buffer.insert(text)
        self._refresh()

    def _on_backspace(self) -> None:
        self._error.setText("")
        self._buffer.backspace()
        self._refresh()

    def _on_clear(self) -> None:
        self._error.setText("")
        self._buffer.clear()
        self._refresh()

    def _on_validate(self) -> None:
        if not is_valid_email(self._buffer.value):
            self._error.setText(MSG_INVALID)
            return
        self.session.email = normalize_email(self._buffer.value)
        self.nav.go_next()

    def _on_skip(self) -> None:
        """Sans adresse : la photo est quand même prise, seul l'organisateur la recevra."""
        self.session.email = ""
        self.nav.go_next()
