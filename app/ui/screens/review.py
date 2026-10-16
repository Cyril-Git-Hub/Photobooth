"""Aperçu du résultat : l'invité valide sa photo ou recommence."""
from __future__ import annotations

import logging
import time

import cv2
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QMovie
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout,
)

from ...core import photo_styles, storage
from ...core.qt_image import bgr_to_qimage
from ..scale import px
from ..widgets.big_button import BigButton
from ..widgets.preview_widget import PreviewWidget
from .base import BaseScreen

log = logging.getLogger(__name__)


class ReviewScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._preview = PreviewWidget()
        self._styles = QComboBox()
        self._subject_mask_cache = None
        self._movie: QMovie | None = None
        for key, label in photo_styles.STYLE_NAMES.items():
            self._styles.addItem(label, key)
        self._styles.currentIndexChanged.connect(self._show_selection)
        self._person_only = QCheckBox("Appliquer uniquement à la personne")
        self._person_only.toggled.connect(self._show_selection)
        self._note = QLabel("")
        self._note.setObjectName("note")
        self._note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        redo = BigButton("Recommencer", "secondary")
        redo.clicked.connect(self._redo)
        validate = BigButton("Valider")
        validate.clicked.connect(self._validate)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(30), px(30), px(30), px(30))
        layout.setSpacing(px(10))
        controls = QHBoxLayout()
        controls.addStretch(1)
        self._style_label = QLabel("Style :")
        controls.addWidget(self._style_label)
        controls.addWidget(self._styles)
        controls.addSpacing(px(20))
        controls.addWidget(self._person_only)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(self._note)
        layout.addWidget(self._preview, 1)
        row = QHBoxLayout()
        row.setSpacing(px(30))
        row.addStretch(1)
        row.addWidget(redo)
        row.addWidget(validate)
        row.addStretch(1)
        layout.addLayout(row)

    def on_enter(self) -> None:
        self._stop_movie()
        self._subject_mask_cache = None
        self._styles.blockSignals(True)
        self._styles.setCurrentIndex(0)
        self._styles.blockSignals(False)
        self._person_only.blockSignals(True)
        self._person_only.setChecked(False)
        self._person_only.setEnabled(self.session.photo_source_frame is not None)
        self._person_only.blockSignals(False)
        if not self.session.photos:
            self._preview.set_message("Aucune photo à afficher.")
            return

        path = self.session.photos[-1]
        is_gif = path.suffix.lower() == ".gif"
        self._style_label.setVisible(not is_gif)
        self._styles.setVisible(not is_gif)
        self._person_only.setVisible(not is_gif)
        if is_gif:
            self._note.setText("Aperçu du GIF animé.")
            movie = QMovie(str(path))
            if movie.isValid():
                self._movie = movie
                movie.frameChanged.connect(lambda _frame: self._preview.set_image(movie.currentImage()))
                movie.start()
            else:
                self._preview.set_message("Impossible d'afficher le GIF.")
            return

        self._note.setText("Compare les rendus ; l'original reste intact jusqu'à la validation.")
        image = QImage(str(path))
        if image.isNull():
            log.error("Photo illisible : %s", path)
            self._preview.set_message("Impossible d'afficher la photo.")
            return
        self._preview.set_image(image)
        self._show_selection()

    def _show_selection(self, *_args) -> None:
        if not self.session.photos or self.session.photos[-1].suffix.lower() == ".gif":
            return
        style = self._styles.currentData()
        self.session.photo_style = style
        self.session.photo_style_person_only = self._person_only.isChecked()
        if style == "original":
            self._note.setText("Originale — aucun effet appliqué.")
            image = QImage(str(self.session.photos[-1]))
            if not image.isNull():
                self._preview.set_image(image)
            return
        try:
            self._note.setText(f"Préparation de l'aperçu {photo_styles.STYLE_NAMES[style]}…")
            QApplication.processEvents()
            source = storage.load_photo(self.session.photos[-1])
            preview_source = self._fit_preview(source)
            started = time.perf_counter()
            styled = photo_styles.apply_style(preview_source, style)
            if self._person_only.isChecked():
                mask = self._subject_mask(source)
                if mask is None:
                    return
                preview_mask = cv2.resize(mask, (preview_source.shape[1], preview_source.shape[0]),
                                          interpolation=cv2.INTER_AREA)
                styled = photo_styles.apply_to_subject(preview_source, styled, preview_mask)
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.info("Aperçu du style %s : %.0f ms à %dx%d", style, elapsed_ms,
                     preview_source.shape[1], preview_source.shape[0])
            self._note.setText(f"Aperçu {photo_styles.STYLE_NAMES[style]} — rendu final en haute résolution.")
            self._preview.set_image(bgr_to_qimage(styled))
        except Exception as exc:
            log.exception("Aperçu du style impossible")
            self._note.setText(f"Impossible d'afficher ce style : {exc}")

    @staticmethod
    def _fit_preview(image):
        height, width = image.shape[:2]
        if width <= 900:
            return image
        target_height = round(height * 900 / width)
        return cv2.resize(image, (900, target_height), interpolation=cv2.INTER_AREA)

    def _subject_mask(self, original):
        if self._subject_mask_cache is not None:
            return self._subject_mask_cache
        source = self.session.photo_source_frame
        if source is None:
            self._note.setText("Le détourage du sujet n'est pas disponible pour ce format.")
            self._person_only.setEnabled(False)
            return None
        try:
            mask = self.nav.get_segmenter().segment(source)
            self._subject_mask_cache = cv2.resize(
                mask, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_LINEAR)
            return self._subject_mask_cache
        except Exception as exc:
            log.warning("Détourage indisponible pour le style photo : %s", exc)
            self._person_only.blockSignals(True)
            self._person_only.setChecked(False)
            self._person_only.setEnabled(False)
            self._person_only.blockSignals(False)
            self.session.photo_style_person_only = False
            self._note.setText(f"Détourage indisponible ; le style s'applique à toute la photo. {exc}")
            return None

    def _validate(self) -> None:
        if not self.session.photos:
            self.nav.go_next()
            return
        path = self.session.photos[-1]
        if path.suffix.lower() == ".gif":
            self.nav.go_next()
            return
        style = self._styles.currentData()
        self.session.photo_style = style
        self.session.photo_style_person_only = self._person_only.isChecked()
        if style != "original":
            try:
                self._note.setText("Calcul du rendu final en haute résolution…")
                QApplication.processEvents()
                original = storage.load_photo(path)
                started = time.perf_counter()
                styled = photo_styles.apply_style(original, style)
                if self._person_only.isChecked():
                    mask = self._subject_mask(original)
                    if mask is None:
                        return
                    styled = photo_styles.apply_to_subject(original, styled, mask)
                storage.replace_photo(path, styled)
                log.info("Rendu final %s : %.0f ms à %dx%d", style,
                         (time.perf_counter() - started) * 1000, original.shape[1], original.shape[0])
            except Exception as exc:
                log.exception("Rendu final du style impossible")
                QMessageBox.warning(self, "Style photo", f"Le style n'a pas pu être appliqué :\n{exc}")
                return
        self.nav.go_next()

    def on_leave(self) -> None:
        self._stop_movie()

    def _stop_movie(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie = None

    def _redo(self) -> None:
        """Supprime le résultat refusé et reprend la prise de vue."""
        rejected = ([self.session.photos.pop()] if self.session.photos else []) + self.session.poses
        self.session.poses = []
        self.session.photo_source_frame = None
        self.session.photo_style = "original"
        self.session.photo_style_person_only = False
        for path in rejected:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.exception("Suppression impossible : %s", path)
        self.nav.go_to("capture")
