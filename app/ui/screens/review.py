"""Galerie tactile de styles et aperçu du résultat."""
from __future__ import annotations

import logging
import time

import cv2
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QMovie, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
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
        self.setObjectName("reviewScreen")
        self._preview = PreviewWidget()
        self._source = None
        self._subject_mask_cache = None
        self._rendered_cache: dict[str, object] = {}
        self._movie: QMovie | None = None
        self._selected_style = "original"

        self._title = QLabel("Choisis ton style")
        self._title.setObjectName("heading")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note = QLabel("")
        self._note.setObjectName("note")
        self._note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note.setWordWrap(True)

        preview_column = QVBoxLayout()
        preview_column.setSpacing(px(8))
        preview_column.addWidget(self._preview, 1)
        self._person_only = QCheckBox("Appliquer le style uniquement à la personne")
        self._person_only.setMinimumHeight(px(54))
        self._person_only.setEnabled(False)
        self._person_only.toggled.connect(self._show_selection)
        preview_column.addWidget(self._person_only, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_host = QWidget()
        preview_host.setLayout(preview_column)

        self._gallery_panel = QWidget()
        gallery_layout = QVBoxLayout(self._gallery_panel)
        gallery_layout.setContentsMargins(0, 0, 0, 0)
        gallery_layout.setSpacing(px(8))
        gallery_title = QLabel("TOUCHE POUR COMPARER")
        gallery_title.setObjectName("styleGalleryTitle")
        gallery_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gallery_layout.addWidget(gallery_title)
        self._cards: dict[str, QPushButton] = {}
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(px(10))
        grid.setVerticalSpacing(px(10))
        for index, (style, label) in enumerate(photo_styles.STYLE_NAMES.items()):
            card = self._make_style_card(style, label)
            self._cards[style] = card
            grid.addWidget(card, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)
        gallery_layout.addLayout(grid, 1)

        body = QHBoxLayout()
        body.setSpacing(px(18))
        body.addWidget(preview_host, 3)
        body.addWidget(self._gallery_panel, 2)

        redo = BigButton("Recommencer", "secondary")
        redo.clicked.connect(self._redo)
        validate = BigButton("Valider la photo")
        validate.clicked.connect(self._validate)
        actions = QHBoxLayout()
        actions.setSpacing(px(24))
        actions.addStretch(1)
        actions.addWidget(redo)
        actions.addWidget(validate)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(24), px(16), px(24), px(16))
        layout.setSpacing(px(8))
        layout.addWidget(self._title)
        layout.addWidget(self._note)
        layout.addLayout(body, 1)
        layout.addLayout(actions)

    def _make_style_card(self, style: str, label: str) -> QPushButton:
        card = QPushButton()
        card.setObjectName("styleCard")
        card.setCheckable(True)
        card.setMinimumSize(px(180), px(140))
        card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        card.setAccessibleName(label)
        card.setAccessibleDescription(f"Afficher l'aperçu : {label}")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        content = QVBoxLayout(card)
        content.setContentsMargins(px(7), px(6), px(7), px(6))
        content.setSpacing(px(4))
        thumbnail = QLabel()
        thumbnail.setObjectName("styleThumbnail")
        thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumbnail.setFixedSize(px(190), px(82))
        caption = QLabel(label)
        caption.setObjectName("styleCardLabel")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setWordWrap(True)
        for child in (thumbnail, caption):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        content.addWidget(thumbnail, 1, alignment=Qt.AlignmentFlag.AlignCenter)
        content.addWidget(caption)
        card.clicked.connect(lambda _checked=False, key=style: self._select_style(key))
        return card

    def on_enter(self) -> None:
        self._stop_movie()
        self._source = None
        self._subject_mask_cache = None
        self._rendered_cache.clear()
        self._person_only.blockSignals(True)
        self._person_only.setChecked(False)
        self._person_only.setEnabled(False)
        self._person_only.blockSignals(False)
        if not self.session.photos:
            self._preview.set_message("Aucune photo à afficher.")
            return

        path = self.session.photos[-1]
        is_gif = path.suffix.lower() == ".gif"
        self._gallery_panel.setVisible(not is_gif)
        self._person_only.setVisible(not is_gif)
        if is_gif:
            self._title.setText("Ton GIF animé")
            self._note.setText("Vérifie l'animation, puis valide ou recommence.")
            movie = QMovie(str(path))
            if movie.isValid():
                self._movie = movie
                movie.frameChanged.connect(lambda _frame: self._preview.set_image(movie.currentImage()))
                movie.start()
            else:
                self._preview.set_message("Impossible d'afficher le GIF.")
            return

        self._title.setText("Choisis ton style")
        self._note.setText("Touche un aperçu pour le voir en grand. L'original reste intact jusqu'à validation.")
        image = QImage(str(path))
        if image.isNull():
            log.error("Photo illisible : %s", path)
            self._preview.set_message("Impossible d'afficher la photo.")
            return

        try:
            self._source = storage.load_photo(path)
        except Exception:
            log.exception("Photo illisible pour la galerie de styles : %s", path)
            self._preview.set_image(image)
            return

        self._person_only.setEnabled(self.session.photo_source_frame is not None)
        self._prepare_thumbnails()
        suggested = self.session.challenge_style if self.session.challenge_id else "original"
        self._select_style(suggested if suggested in self._cards else "original")

    def _prepare_thumbnails(self) -> None:
        if self._source is None:
            return
        thumbnail_source = self._fit_width(self._source, 240)
        for style, card in self._cards.items():
            try:
                preview = thumbnail_source if style == "original" else photo_styles.apply_style(thumbnail_source, style)
                pixmap = QPixmap.fromImage(bgr_to_qimage(preview)).scaled(
                    self._cards[style].findChild(QLabel, "styleThumbnail").size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                card.findChild(QLabel, "styleThumbnail").setPixmap(pixmap)
            except Exception:
                log.exception("Vignette indisponible pour le style %s", style)
                card.findChild(QLabel, "styleThumbnail").setText("Aperçu indisponible")
            QApplication.processEvents()

    def _select_style(self, style: str) -> None:
        if style not in self._cards:
            return
        self._selected_style = style
        self.session.photo_style = style
        self.session.photo_style_person_only = self._person_only.isChecked() and style != "original"
        for key, card in self._cards.items():
            card.setChecked(key == style)
        self._person_only.setEnabled(
            style != "original" and self.session.photo_source_frame is not None
        )
        self._show_selection()

    def _show_selection(self, *_args) -> None:
        if self._source is None:
            return
        style = self._selected_style
        self.session.photo_style = style
        self.session.photo_style_person_only = self._person_only.isChecked() and style != "original"
        preview_source = self._fit_width(self._source, 900)
        if style == "original":
            result = preview_source
            self._note.setText("Originale — aucun effet appliqué.")
        else:
            try:
                self._note.setText(f"Préparation de l'aperçu {photo_styles.STYLE_NAMES[style]}…")
                QApplication.processEvents()
                started = time.perf_counter()
                styled = self._rendered_cache.get(style)
                if styled is None:
                    styled = photo_styles.apply_style(preview_source, style)
                    self._rendered_cache[style] = styled
                result = styled
                if self._person_only.isChecked():
                    mask = self._subject_mask(self._source)
                    if mask is None:
                        return
                    preview_mask = cv2.resize(mask, (preview_source.shape[1], preview_source.shape[0]),
                                              interpolation=cv2.INTER_AREA)
                    result = photo_styles.apply_to_subject(preview_source, styled, preview_mask)
                elapsed_ms = (time.perf_counter() - started) * 1000
                log.info("Aperçu du style %s : %.0f ms à %dx%d", style, elapsed_ms,
                         preview_source.shape[1], preview_source.shape[0])
                self._note.setText(
                    f"{photo_styles.STYLE_NAMES[style]} · aperçu prêt · rendu final haute résolution à la validation."
                )
            except Exception as exc:
                log.exception("Aperçu du style impossible")
                self._note.setText(f"Impossible d'afficher ce style : {exc}")
                return
        self._preview.set_image(bgr_to_qimage(result))

    @staticmethod
    def _fit_width(image, width: int):
        height, source_width = image.shape[:2]
        if source_width <= width:
            return image
        target_height = round(height * width / source_width)
        return cv2.resize(image, (width, target_height), interpolation=cv2.INTER_AREA)

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
            self.nav.sounds.play("success")
            self.nav.go_next()
            return
        style = self._selected_style
        self.session.photo_style = style
        self.session.photo_style_person_only = self._person_only.isChecked() and style != "original"
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
        self.nav.sounds.play("success")
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
