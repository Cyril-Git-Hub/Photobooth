"""Choix du format : une seule photo, ou photomaton (bande de plusieurs photos)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from ..widgets.big_button import BigButton
from .base import BaseScreen
from ..scale import px


class FormatSelectScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        heading = QLabel("Quel format ?")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._single = BigButton("Photo unique", "notListed")
        self._single.setObjectName("formatOptionButton")
        self._single.setMinimumSize(px(255), px(90))
        self._single.clicked.connect(lambda: self._choose("single"))
        self._strip = BigButton("Photomaton", "notListed")
        self._strip.setObjectName("formatOptionButton")
        self._strip.setMinimumSize(px(255), px(90))
        self._strip.clicked.connect(lambda: self._choose("strip"))
        self._gif = BigButton("GIF animé", "notListed")
        self._gif.setObjectName("formatOptionButton")
        self._gif.setMinimumSize(px(255), px(90))
        self._gif.clicked.connect(self._choose_gif)
        self._challenge = BigButton("Casting/Audition", "notListed")
        self._challenge.setObjectName("formatOptionButton")
        self._challenge.setMinimumSize(px(255), px(90))
        self._challenge.clicked.connect(lambda: self.nav.go_to("challenge"))
        self._guestbook = BigButton("Livre d'or vidéo", "guestbook")
        self._guestbook.setObjectName("formatOptionButton")
        self._guestbook.setMinimumSize(px(255), px(90))
        self._guestbook.clicked.connect(self._choose_guestbook)

        self._email_note = QLabel("")
        self._email_note.setObjectName("summary")
        self._email_note.setAlignment(Qt.AlignmentFlag.AlignCenter)

        back = BigButton("Retour", "secondary")
        back.clicked.connect(lambda: self.nav.go_to("guest_select"))

        choices = QHBoxLayout()
        choices.setSpacing(px(40))
        choices.addStretch(1)
        choices.addWidget(self._single)
        choices.addWidget(self._strip)
        choices.addStretch(1)
        framed_row = QHBoxLayout()
        framed_row.addStretch(1)
        framed_row.addWidget(self._gif)
        framed_row.addStretch(1)
        challenge_row = QHBoxLayout()
        challenge_row.addStretch(1)
        challenge_row.addWidget(self._challenge)
        challenge_row.addSpacing(px(20))
        challenge_row.addWidget(self._guestbook)
        challenge_row.addStretch(1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(back)
        footer.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(60), px(40), px(60), px(40))
        layout.setSpacing(px(30))
        layout.addWidget(heading)
        layout.addStretch(1)
        layout.addLayout(choices)
        layout.addLayout(framed_row)
        layout.addLayout(challenge_row)
        layout.addStretch(1)
        layout.addWidget(self._email_note)
        layout.addLayout(footer)

    def on_enter(self) -> None:
        email = self.session.email.strip()
        self._email_note.setText(f"La photo sera envoyée sur ton mail : {email}" if email else "")
        self._email_note.setVisible(bool(email))
        poses = self.config.nb_poses
        has_strip = poses >= 2             # un « photomaton » d'une seule pose n'aurait pas de sens
        self._strip.setText("Photomaton")
        self._strip.setVisible(has_strip)
        self._gif.setVisible(self.config.gif_actif)
        self._challenge.setVisible(self.config.defis_actifs)
        self._guestbook.setVisible(
            self.config.livre_or_actif and self.nav.events.active_event() is not None
        )

    def _choose(self, photo_format: str) -> None:
        self.session.photo_format = photo_format
        self.session.background_path = None
        self.session.frame_mode = False
        self.session.frame_path = None
        self._clear_challenge()
        self.nav.go_to("background_select")

    def _choose_gif(self) -> None:
        self.session.photo_format = "gif"
        self.session.background_path = None
        self.session.frame_mode = False
        self.session.frame_path = None
        self._clear_challenge()
        self.nav.go_to("gif_options")

    def _choose_guestbook(self) -> None:
        if not self.config.livre_or_actif:
            return
        event = self.nav.events.active_event()
        if event is None:
            self._guestbook.hide()
            return
        self.session.event_id = event.id
        self._clear_challenge()
        self.nav.go_to("guestbook")

    def _clear_challenge(self) -> None:
        self.session.challenge_id = ""
        self.session.challenge_title = ""
        self.session.challenge_instruction = ""
        self.session.challenge_background_required = False
        self.session.challenge_mask = ""
        self.session.challenge_style = ""
        self.session.challenge_reference_png = None
