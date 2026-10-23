"""Défi surprise : consigne et éventuelle image avant le parcours de prise de vue."""
from __future__ import annotations

import logging
import random

from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from ...core import backgrounds, challenges
from ..scale import px
from ..widgets.big_button import BigButton
from .base import BaseScreen

log = logging.getLogger(__name__)


class _FitImageLabel(QLabel):
    """Affiche l'image entière en s'adaptant à la place réellement disponible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source = QPixmap()

    def set_source(self, image: QPixmap) -> None:
        self._source = image
        self._fit_image()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_image()

    def _fit_image(self) -> None:
        if self._source.isNull():
            self.clear()
            return
        available = self.contentsRect().size()
        if available.width() <= 0 or available.height() <= 0:
            return
        self.setPixmap(self._source.scaled(
            available, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))


class ChallengeScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._challenges: list[challenges.Challenge] = []
        self._current: challenges.Challenge | None = None
        self._previous_id = ""

        heading = QLabel("Casting/Audition")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._kind = QLabel("")
        self._kind.setObjectName("badge")
        self._kind.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image = _FitImageLabel()
        self._image.setObjectName("challengeReference")
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setMinimumSize(px(300), px(300))
        self._image.setMaximumSize(px(600), px(600))
        self._title = QLabel("")
        self._title.setObjectName("heading")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        self._instruction = QLabel("")
        self._instruction.setObjectName("note")
        self._instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._instruction.setWordWrap(True)
        self._availability = QLabel("")
        self._availability.setObjectName("summary")
        self._availability.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._back = BigButton("Retour", "secondary")
        self._back.clicked.connect(self._go_back)
        self._another = BigButton("Autre défi", "secondary")
        self._another.clicked.connect(self._choose_another)
        self._start = BigButton("Je relève le défi !", "notListed")
        self._start.clicked.connect(self._start_challenge)

        content = QHBoxLayout()
        content.setSpacing(px(40))
        content.addStretch(1)
        content.addWidget(self._image, 1)
        info = QVBoxLayout()
        info.setSpacing(px(20))
        info.addWidget(self._kind)
        info.addWidget(self._title)
        info.addWidget(self._instruction)
        info.addWidget(self._availability)
        info.addStretch(1)
        content.addLayout(info, 1)
        content.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self._back)
        footer.addWidget(self._another)
        footer.addWidget(self._start)
        footer.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(40), px(24), px(40), px(24))
        layout.setSpacing(px(20))
        layout.addWidget(heading)
        layout.addLayout(content, 1)
        layout.addLayout(footer)

    def on_enter(self) -> None:
        self._challenges = challenges.load_challenges(
            self.config.dossier_theme / "defis.json", allow_gif=self.config.gif_actif)
        if not self._challenges:
            self._current = None
            self._title.setText("Aucun défi disponible")
            self._instruction.setText(
                "Vérifie le fichier defis.json du thème ou active les défis dans config.ini.")
            self._kind.clear()
            self._image.set_source(QPixmap())
            self._image.hide()
            self._availability.clear()
            self._start.setEnabled(False)
            self._another.setEnabled(False)
            return
        self._start.setEnabled(True)
        self._another.setEnabled(len(self._challenges) > 1)
        if self.session.challenge_id:
            selected = next((challenge for challenge in self._challenges
                             if challenge.id == self.session.challenge_id), None)
            if selected is not None:
                self._show_challenge(selected)
                return
        self._choose_another()

    def _choose_another(self) -> None:
        if not self._challenges:
            return
        choices = [challenge for challenge in self._challenges if challenge.id != self._previous_id]
        selected = random.choice(choices or self._challenges)
        log.info("Défi choisi : id=%s | image=%s", selected.id,
                 selected.image if selected.image else "aucune")
        self._show_challenge(selected)

    def _show_challenge(self, challenge: challenges.Challenge) -> None:
        self._current = challenge
        self._previous_id = challenge.id
        self._title.setText(challenge.title)
        self._instruction.setText(challenge.instruction)
        kind = {"single": "PHOTO UNIQUE", "strip": "PHOTOMATON", "gif": "GIF ANIMÉ"}[challenge.photo_format]
        if challenge.background_image is not None:
            kind += " · DÉCOR IMPOSÉ"
        elif challenge.background == "choose":
            kind += " · DÉCOR À CHOISIR"
        elif challenge.background == "random":
            kind += " · DÉCOR SURPRISE"
        self._kind.setText(kind)
        if (challenge.background_image is None and challenge.background != "none"
                and not self._available_backgrounds()):
            self._availability.setText(
                "Aucun décor n’est chargé : le défi reste jouable sans décor. "
                "Ajoute des images dans le dossier fonds pour activer cette option.")
        else:
            self._availability.setText(
                "Les défis réutilisent le compte à rebours, les poses, les décors et les réglages GIF du photobooth.")
        extras = []
        if challenge.mask:
            extras.append(f"Masque proposé : {challenge.mask}")
        if challenge.style:
            extras.append(f"style proposé : {challenge.style.replace('_', ' ')}")
        if extras:
            self._availability.setText(self._availability.text() + "\n" + " · ".join(extras))
        self._image.set_source(QPixmap())
        self._image.hide()
        if challenge.image is not None:
            pixmap = self._load_reference(challenge.image)
            if not pixmap.isNull():
                self._image.set_source(pixmap)
                self._image.show()
            else:
                log.error("Image du défi illisible à l'affichage : id=%s | image=%s",
                          challenge.id, challenge.image)

    @staticmethod
    def _load_reference(path) -> QPixmap:
        if path.suffix.casefold() != ".svg":
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                log.error("Impossible de décoder l'image du défi : %s", path)
            return pixmap
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            log.error("Image SVG du défi invalide : %s", path)
            return QPixmap()
        image = QImage(560, 720, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        return QPixmap.fromImage(image)

    def _start_challenge(self) -> None:
        challenge = self._current
        if challenge is None:
            return
        self.session.challenge_id = challenge.id
        self.session.challenge_title = challenge.title
        self.session.challenge_instruction = challenge.instruction
        self.session.challenge_background_required = False
        self.session.challenge_mask = challenge.mask
        self.session.challenge_style = challenge.style
        self.session.challenge_reference_png = None
        if challenge.image is not None:
            pixmap = self._load_reference(challenge.image)
            if not pixmap.isNull():
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                if pixmap.save(buffer, "PNG"):
                    self.session.challenge_reference_png = bytes(buffer.data())
                buffer.close()
        self.session.photo_format = challenge.photo_format
        self.session.frame_mode = False
        self.session.frame_path = None
        self.session.background_path = None
        self.session.virtual_mask_path = None
        self.session.virtual_mask_paths.clear()

        if challenge.background_image is not None:
            self.session.background_path = challenge.background_image
        elif challenge.background == "random":
            self.session.background_path = backgrounds.random_background(self._available_backgrounds())
        elif challenge.background == "choose" and self._available_backgrounds():
            self.session.challenge_background_required = True
        elif challenge.background == "none":
            self.session.challenge_background_required = False

        if self.session.challenge_background_required:
            self.nav.go_to("background_select")
        elif challenge.photo_format == "gif":
            self.nav.go_to("gif_options")
        else:
            self.nav.go_to("capture")

    def _available_backgrounds(self) -> list[backgrounds.Theme]:
        folder = (self.nav.theme.backgrounds
                  if self.nav.theme and self.nav.theme.backgrounds.exists()
                  else self.config.dossier_fonds)
        themes = backgrounds.scan_backgrounds(folder)
        if not themes and folder != self.config.dossier_fonds:
            themes = backgrounds.scan_backgrounds(self.config.dossier_fonds)
        return themes

    def _go_back(self) -> None:
        self.session.challenge_id = ""
        self.session.challenge_title = ""
        self.session.challenge_instruction = ""
        self.session.challenge_background_required = False
        self.session.challenge_mask = ""
        self.session.challenge_style = ""
        self.session.challenge_reference_png = None
        self.nav.go_to("format_select")
