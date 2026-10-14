"""Écrans provisoires : ils seront remplacés un par un (un fichier par écran) aux étapes suivantes.

Ils servent à valider dès maintenant la navigation, la session et le retour automatique.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from ..widgets.big_button import BigButton
from .base import BaseScreen


class PlaceholderScreen(BaseScreen):
    title = "Écran"
    note = ""
    show_back = True
    next_label = "Suivant"

    def __init__(self, nav) -> None:
        super().__init__(nav)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 60, 60, 60)
        layout.setSpacing(24)

        self._title = self._label(self.title, "title")
        self._note = self._label(self.note, "note")
        self._summary = self._label("", "summary")

        layout.addStretch(1)
        for label in (self._title, self._note, self._summary):
            layout.addWidget(label)
        layout.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(30)
        row.addStretch(1)
        self._build_buttons(row)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _build_buttons(self, row: QHBoxLayout) -> None:
        if self.show_back:
            back = BigButton("Retour", "secondary")
            back.clicked.connect(lambda: self.nav.go_back())
            row.addWidget(back)
        forward = BigButton(self.next_label)
        forward.clicked.connect(lambda: self.nav.go_next())
        row.addWidget(forward)

    def on_enter(self) -> None:
        s = self.session
        decor = s.background_path.name if s.background_path else "—"
        self._summary.setText(
            f"Invité : {s.display_name or '—'}   |   Mail : {s.email or '—'}   |   "
            f"Format : {s.photo_format}   |   Décor : {decor}   |   Photos : {len(s.photos)}"
        )


class HomeScreen(PlaceholderScreen):
    title = "Photo Booth"
    note = "Accueil : gros bouton « Commencer » (visuel thématique à venir)."
    show_back = False
    next_label = "Commencer"
