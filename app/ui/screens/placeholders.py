"""Écrans provisoires : ils seront remplacés un par un (un fichier par écran) aux étapes suivantes.

Ils servent à valider dès maintenant la navigation, la session et le retour automatique.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from ..widgets.big_button import BigButton
from .base import BaseScreen
from ..scale import px


class PlaceholderScreen(BaseScreen):
    title = "Écran"
    note = ""
    show_back = True
    next_label = "Suivant"

    def __init__(self, nav) -> None:
        super().__init__(nav)
        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(px(60), px(60), px(60), px(60))
        layout.setSpacing(px(24))

        self._title = self._label(self.title, "title")
        self._note = self._label(self.note, "note")

        layout.addStretch(1)
        for label in (self._title, self._note):
            layout.addWidget(label)
        layout.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(px(30))
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
        self._forward = forward
        forward.clicked.connect(lambda: self.nav.go_next())
        row.addWidget(forward)

class HomeScreen(PlaceholderScreen):
    title = "Photo Booth"
    note = "Prêt à créer un souvenir ?"
    show_back = False
    next_label = "Commencer"

    def __init__(self, nav) -> None:
        super().__init__(nav)
        self.apply_theme(nav.theme)

    def apply_theme(self, theme) -> None:
        if theme is None:
            return
        self._title.setText(theme.welcome_title)
        self._note.setText(theme.welcome_message)
        self._forward.setText(theme.start_button)
        image_path = theme.welcome_image or theme.logo
        existing = getattr(self, "_welcome_visual", None)
        if existing is not None:
            existing.deleteLater()
            self._welcome_visual = None
        if image_path is not None:
            image = QPixmap(str(image_path))
            if not image.isNull():
                visual = QLabel()
                visual.setAlignment(Qt.AlignmentFlag.AlignCenter)
                visual.setPixmap(image.scaled(px(600), px(260), Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
                self._layout.insertWidget(1, visual)
                self._welcome_visual = visual
