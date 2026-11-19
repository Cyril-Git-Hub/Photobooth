"""Adresse mail : confirmation ou correction de celle de la liste, ou saisie, au clavier virtuel."""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QVBoxLayout

from ...core.emails import MSG_INVALID, is_valid_email, normalize_email
from ...core.guests import GuestListError, update_guest_emails
from ...core.keyboards import EMAIL_ROWS
from ...core.text_buffer import TextBuffer
from ..widgets.big_button import BigButton
from ..widgets.virtual_keyboard import VirtualKeyboard
from .base import BaseScreen
from ..scale import px

log = logging.getLogger(__name__)


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

        self._keyboard = VirtualKeyboard(EMAIL_ROWS, compact=True)
        self._keyboard.text_typed.connect(self._on_text)
        self._keyboard.backspace_pressed.connect(self._on_backspace)
        self._keyboard.clear_pressed.connect(self._on_clear)

        back = BigButton("Retour", "secondary")
        back.clicked.connect(lambda: self.nav.go_back())
        self._skip = BigButton("Passer", "secondary")
        self._skip.clicked.connect(lambda: self._on_skip())
        validate = BigButton("Valider")
        validate.clicked.connect(self._on_validate)
        for button in (back, self._skip, validate):
            button.setObjectName("emailNavButton")
            button.setMinimumSize(px(180), px(60))
        buttons = QHBoxLayout()
        buttons.setSpacing(px(12))
        buttons.addStretch(1)
        for button in (back, self._skip, validate):
            buttons.addWidget(button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(24), px(12), px(24), px(12))
        layout.setSpacing(px(5))
        layout.addWidget(self._heading)
        layout.addWidget(self._note)
        layout.addWidget(self._field)
        layout.addWidget(self._error)
        layout.addStretch(1)
        layout.addWidget(self._keyboard)
        layout.addLayout(buttons)

    def on_enter(self) -> None:
        first_name = self.session.guest_pseudo or self.session.guest_first_name
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
        log.info("Validation du mail demandée")
        if not is_valid_email(self._buffer.value):
            QMessageBox.warning(self, "Adresse mail invalide", MSG_INVALID)
            return
        email = normalize_email(self._buffer.value)
        if self.session.guest_from_list:
            try:
                update_guest_emails(
                    self.config.fichier_invites,
                    {self.session.guest_pseudo: email},
                )
            except GuestListError as exc:
                # Une erreur d'accès/format de la liste ne doit pas bloquer la séance.
                # L'adresse reste disponible pour cette photo, même si elle ne peut
                # pas être mémorisée pour les prochaines visites.
                QMessageBox.warning(
                    self, "Adresse non mémorisée",
                    f"{exc}\n\nLa séance continue avec cette adresse, mais elle ne sera pas conservée dans la liste.",
                )
            except Exception as exc:
                log.exception("Erreur inattendue pendant l'enregistrement du mail invité")
                QMessageBox.warning(
                    self, "Adresse non mémorisée",
                    f"Impossible d'enregistrer cette adresse dans la liste ({exc}).\n\n"
                    "La séance continue avec cette adresse, mais elle ne sera pas conservée dans la liste.",
                )
        self.session.email = email
        self.nav.go_next()

    def _on_skip(self) -> None:
        """Sans adresse : la photo est quand même prise, seul l'organisateur la recevra."""
        self.session.email = ""
        self.nav.go_next()
