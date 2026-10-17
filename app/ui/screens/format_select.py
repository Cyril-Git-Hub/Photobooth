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

        self._single = BigButton("Une seule photo")
        self._single.setObjectName("formatOptionButton")
        self._single.setMinimumSize(px(255), px(90))
        self._single.clicked.connect(lambda: self._choose("single"))
        self._strip = BigButton("Photomaton")
        self._strip.setObjectName("formatOptionButton")
        self._strip.setMinimumSize(px(255), px(90))
        self._strip.clicked.connect(lambda: self._choose("strip"))
        self._framed = BigButton("Photo avec cadre")
        self._framed.setObjectName("formatOptionButton")
        self._framed.setMinimumSize(px(255), px(90))
        self._framed.clicked.connect(self._choose_framed)
        self._gif = BigButton("GIF animé")
        self._gif.setObjectName("formatOptionButton")
        self._gif.setMinimumSize(px(255), px(90))
        self._gif.clicked.connect(self._choose_gif)
        self._challenge = BigButton("Défi surprise")
        self._challenge.setObjectName("formatOptionButton")
        self._challenge.setMinimumSize(px(255), px(90))
        self._challenge.clicked.connect(lambda: self.nav.go_to("challenge"))

        back = BigButton("Retour", "secondary")
        back.clicked.connect(lambda: self.nav.go_back())

        choices = QHBoxLayout()
        choices.setSpacing(px(40))
        choices.addStretch(1)
        choices.addWidget(self._single)
        choices.addWidget(self._strip)
        choices.addStretch(1)
        framed_row = QHBoxLayout()
        framed_row.addStretch(1)
        framed_row.addWidget(self._framed)
        framed_row.addSpacing(px(20))
        framed_row.addWidget(self._gif)
        framed_row.addStretch(1)
        challenge_row = QHBoxLayout()
        challenge_row.addStretch(1)
        challenge_row.addWidget(self._challenge)
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
        layout.addLayout(footer)

    def on_enter(self) -> None:
        poses = self.config.nb_poses
        has_strip = poses >= 2             # un « photomaton » d'une seule pose n'aurait pas de sens
        self._strip.setText("Photomaton")
        self._strip.setVisible(has_strip)
        self._gif.setVisible(self.config.gif_actif)
        self._challenge.setVisible(self.config.defis_actifs)

    def _choose(self, photo_format: str) -> None:
        self.session.photo_format = photo_format
        self.session.background_path = None
        self.session.frame_mode = False
        self.session.frame_path = None
        self._clear_challenge()
        self.nav.go_next()

    def _choose_framed(self) -> None:
        self.session.photo_format = "single"
        self.session.background_path = None
        self.session.frame_mode = True
        self.session.frame_path = None
        self._clear_challenge()
        self.nav.go_to("capture")

    def _choose_gif(self) -> None:
        self.session.photo_format = "gif"
        self.session.background_path = None
        self.session.frame_mode = False
        self.session.frame_path = None
        self._clear_challenge()
        self.nav.go_to("gif_options")

    def _clear_challenge(self) -> None:
        self.session.challenge_id = ""
        self.session.challenge_title = ""
        self.session.challenge_instruction = ""
        self.session.challenge_background_required = False
        self.session.challenge_mask = ""
        self.session.challenge_style = ""
