"""Choix du format : une seule photo, ou photomaton (bande de plusieurs photos)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from ..widgets.big_button import BigButton
from .base import BaseScreen


class FormatSelectScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        heading = QLabel("Quel format ?")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._single = BigButton("Une seule photo")
        self._single.setMinimumSize(420, 220)
        self._single.clicked.connect(lambda: self._choose("single"))
        self._strip = BigButton("Photomaton")
        self._strip.setMinimumSize(420, 220)
        self._strip.clicked.connect(lambda: self._choose("strip"))

        self._hint = QLabel("")
        self._hint.setObjectName("note")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setWordWrap(True)
        back = BigButton("Retour", "secondary")
        back.clicked.connect(lambda: self.nav.go_back())

        choices = QHBoxLayout()
        choices.setSpacing(40)
        choices.addStretch(1)
        choices.addWidget(self._single)
        choices.addWidget(self._strip)
        choices.addStretch(1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(back)
        footer.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(30)
        layout.addWidget(heading)
        layout.addStretch(1)
        layout.addLayout(choices)
        layout.addWidget(self._hint)
        layout.addStretch(1)
        layout.addLayout(footer)

    def on_enter(self) -> None:
        poses = self.config.nb_poses
        has_strip = poses >= 2             # un « photomaton » d'une seule pose n'aurait pas de sens
        self._strip.setText(f"Photomaton\n{poses} photos en bande")
        self._strip.setVisible(has_strip)
        self._hint.setText(f"Le photomaton prend {poses} photos à la suite : change de position à chaque fois !"
                           if has_strip else "")

    def _choose(self, photo_format: str) -> None:
        self.session.photo_format = photo_format
        self.nav.go_next()
