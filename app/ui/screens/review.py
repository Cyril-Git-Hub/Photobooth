"""Aperçu du résultat : l'invité valide sa photo ou recommence."""
from __future__ import annotations

import logging

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout

from ..widgets.big_button import BigButton
from ..widgets.preview_widget import PreviewWidget
from .base import BaseScreen
from ..scale import px

log = logging.getLogger(__name__)


class ReviewScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._preview = PreviewWidget()
        redo = BigButton("Recommencer", "secondary")
        redo.clicked.connect(lambda: self._redo())
        validate = BigButton("Valider")
        validate.clicked.connect(lambda: self.nav.go_next())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(30), px(30), px(30), px(30))
        layout.setSpacing(px(20))
        layout.addWidget(self._preview, 1)
        row = QHBoxLayout()
        row.setSpacing(px(30))
        row.addStretch(1)
        row.addWidget(redo)
        row.addWidget(validate)
        row.addStretch(1)
        layout.addLayout(row)

    def on_enter(self) -> None:
        if not self.session.photos:
            self._preview.set_message("Aucune photo à afficher.")
            return
        image = QImage(str(self.session.photos[-1]))
        if image.isNull():
            log.error("Photo illisible : %s", self.session.photos[-1])
            self._preview.set_message("Impossible d'afficher la photo.")
        else:
            self._preview.set_image(image)

    def _redo(self) -> None:
        """La photo refusée (et, pour une bande, ses poses) est supprimée du disque et de la session,
        puis on reprend la prise de vue."""
        rejected = ([self.session.photos.pop()] if self.session.photos else []) + self.session.poses
        self.session.poses = []
        for path in rejected:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.exception("Suppression impossible : %s", path)
        self.nav.go_to("capture")
