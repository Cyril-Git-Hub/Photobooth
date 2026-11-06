"""Défi surprise : consigne et éventuelle image avant le parcours de prise de vue."""
from __future__ import annotations

import logging
import random
from html import escape

from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QScroller, QVBoxLayout, QWidget,
)

from ...core import backgrounds, challenges
from ...core.guests import Guest, GuestListError, load_guests
from ..scale import px
from ..widgets.big_button import BigButton
from ..widgets.dance_pose import DancePoseWidget, generate_pose_sequence
from ..widgets.guest_wheel import GuestWheel
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
        self._wheel_guests: list[Guest] = []
        self._wheel_error = ""
        self._winner: Guest | None = None

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
        self._wheel = GuestWheel()
        self._wheel.finished.connect(self._wheel_finished)
        self._wheel_panel = QWidget()
        wheel_layout = QVBoxLayout(self._wheel_panel)
        wheel_layout.setContentsMargins(0, 0, 0, 0)
        wheel_layout.setSpacing(px(4))
        self._wheel.setMaximumHeight(px(340))
        self._wheel_panel.setMaximumHeight(px(340 + 64 + 4))
        wheel_layout.addWidget(self._wheel, 0, Qt.AlignmentFlag.AlignHCenter)
        self._spin = QPushButton("Lancer la roue")
        self._spin.setObjectName("guestWheelSpinButton")
        self._spin.setFixedSize(px(240), px(64))
        self._spin.setCursor(Qt.CursorShape.PointingHandCursor)
        self._spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._spin.clicked.connect(self._spin_wheel)
        wheel_layout.addWidget(self._spin, 0, Qt.AlignmentFlag.AlignHCenter)
        self._wheel_panel.hide()
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
        self._gate_hint = QLabel(
            "Lance le tirage au sort pour activer « Je relève le défi ! ».")
        self._gate_hint.setObjectName("challengeGateHint")
        self._gate_hint.setWordWrap(True)
        self._gate_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gate_hint.hide()
        self._dance_sequence_title = QLabel("Voici les poses à reproduire, dans l'ordre :")
        self._dance_sequence_title.setObjectName("summary")
        self._dance_sequence_title.setWordWrap(True)
        self._dance_sequence = QWidget()
        self._dance_sequence_row = QHBoxLayout(self._dance_sequence)
        self._dance_sequence_row.setContentsMargins(px(4), px(4), px(4), px(4))
        self._dance_sequence_row.setSpacing(px(8))
        self._dance_scroll = QScrollArea()
        self._dance_scroll.setWidgetResizable(True)
        self._dance_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._dance_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._dance_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._dance_scroll.setFixedHeight(px(160))
        self._dance_scroll.setWidget(self._dance_sequence)
        QScroller.grabGesture(
            self._dance_scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        QScroller.grabGesture(
            self._dance_scroll.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        self._dance_sequence_title.hide()
        self._dance_scroll.hide()

        self._back = BigButton("Retour", "secondary")
        self._back.setFixedWidth(px(260))
        self._back.clicked.connect(self._go_back)
        self._another = BigButton("Autre défi", "secondary")
        self._another.setFixedWidth(px(260))
        self._another.clicked.connect(self._choose_another)
        self._start = BigButton("Je relève le défi !", "notListed")
        self._start.setFixedWidth(px(400))
        self._start.setObjectName("challengeStartButton")
        self._start.clicked.connect(self._start_challenge)

        content = QHBoxLayout()
        content.setSpacing(px(40))
        content.addStretch(1)
        content.addWidget(self._image, 1)
        content.addWidget(self._wheel_panel, 1)
        self._info_panel = QWidget()
        info = QVBoxLayout(self._info_panel)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(px(20))
        info.addWidget(self._kind)
        info.addWidget(self._title)
        info.addWidget(self._instruction)
        info.addWidget(self._dance_sequence_title)
        info.addWidget(self._dance_scroll)
        info.addWidget(self._availability)
        info.addWidget(self._gate_hint)
        info.addStretch(1)
        content.addWidget(self._info_panel, 1)
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
        self._spin.hide()
        self._wheel_panel.hide()
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
            self._gate_hint.hide()
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
        retained_name = (self.session.challenge_guest_name
                         if self.session.challenge_id == challenge.id else "")
        self._current = challenge
        self._previous_id = challenge.id
        self._wheel.stop()
        self._winner = None
        self._title.setText(challenge.title)
        self._instruction.setText(challenge.instruction)
        is_guest_wheel = challenge.challenge_type == "guest_wheel"
        is_dance = challenge.challenge_type == "dance"
        kind = ("ROUE DES INVITÉS · PHOTO UNIQUE" if is_guest_wheel else
                "JUST DANCE · GIF ANIMÉ" if is_dance else
                {"single": "PHOTO UNIQUE", "strip": "PHOTOMATON", "gif": "GIF ANIMÉ"}[challenge.photo_format])
        if challenge.background_image is not None:
            kind += " · DÉCOR IMPOSÉ"
        elif challenge.background == "choose":
            kind += " · DÉCOR À CHOISIR"
        elif challenge.background == "random":
            kind += " · DÉCOR SURPRISE"
        self._kind.setText(kind)
        self._dance_sequence_title.setVisible(is_dance)
        self._dance_scroll.setVisible(is_dance)
        if is_dance:
            self.session.gif_capture_mode = "spaced"
            self.session.gif_effect = "loop"
            self.session.gif_hold_last = False
            pose_count = self.config.gif_poses_espacees
            if len(self.session.dance_pose_ids) != pose_count:
                self.session.dance_pose_ids = generate_pose_sequence(pose_count)
            self._show_dance_sequence(self.session.dance_pose_ids)
            self._instruction.setText(
                f"Imite les {pose_count} poses dans l'ordre. Une pose s'affichera pendant "
                "chaque compte à rebours, puis sera aussi visible sur l'image du GIF.")
        if is_guest_wheel:
            self._info_panel.setMinimumWidth(max(px(500), int(self.width() * 0.4)))
            self._availability.setWordWrap(True)
            self._availability.setFixedHeight(px(72))
            self._load_wheel_guests(retained_name)
            self._wheel.set_names([guest.pseudo for guest in self._wheel_guests])
            self._winner = next((guest for guest in self._wheel_guests
                                 if guest.display_name == retained_name), None)
            self._image.hide()
            self._wheel_panel.show()
            self._spin.show()
            self._spin.setEnabled(bool(self._wheel_guests))
            self._start.setEnabled(self._winner is not None)
            self._start.setText("Je relève le défi !")
            self._gate_hint.setVisible(bool(self._wheel_guests))
            self._set_gate_hint(
                "Lance le tirage au sort pour activer « Je relève le défi ! »."
                if self._winner is None else
                "Tirage terminé : tu peux relever le défi !")
            if self._wheel_error:
                self._availability.setText(self._wheel_error)
            elif self._winner is not None:
                self._show_winner(self._winner, "Tu peux refaire la photo avec cette personne.")
            elif self._wheel_guests:
                self._availability.setText(
                    f"{len(self._wheel_guests)} invité(s) dans la roue. "
                    "Lance le tirage, puis retrouve la personne pour faire la photo ensemble.")
            else:
                self._availability.setText(
                    "Aucun autre invité n'est disponible pour le tirage. Vérifie la liste d'invités.")
        elif (challenge.background_image is None and challenge.background != "none"
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
        if not is_guest_wheel:
            self._info_panel.setMinimumWidth(0)
            self._availability.setWordWrap(False)
            self._availability.setMinimumHeight(0)
            self._availability.setMaximumHeight(16777215)
            self._start.setEnabled(True)
            self._start.setText("Je relève le défi !")
            self._gate_hint.hide()
            self._spin.hide()
            self._wheel_panel.hide()
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

    def _load_wheel_guests(self, retained_name: str = "") -> None:
        self._wheel_guests = []
        self._wheel_error = ""
        try:
            guests = load_guests(self.config.fichier_invites)
        except GuestListError as exc:
            self._wheel_error = exc.args[0]
            log.error("Impossible de charger la liste pour la roue des invités : %s",
                      self._wheel_error.replace("\n", " "))
            return

        guests = [guest for guest in guests if guest.pseudo.strip()]
        if self.session.guest_from_list and self.session.guest_pseudo:
            guests = [guest for guest in guests
                      if guest.pseudo.casefold() != self.session.guest_pseudo.casefold()]

        retained = next((guest for guest in guests if guest.pseudo == retained_name), None)
        if retained is not None:
            others = [guest for guest in guests if guest != retained]
            self._wheel_guests = [retained, *random.sample(others, min(9, len(others)))]
        else:
            self._wheel_guests = random.sample(guests, min(10, len(guests)))

    def _spin_wheel(self) -> None:
        if self._wheel_guests:
            self._winner = None
            self._start.setEnabled(False)
            self._spin.setEnabled(False)
            self._set_gate_hint("Tirage en cours…")
            self._availability.setText("La roue tourne…")
            self._wheel.spin()

    def _wheel_finished(self, index: int) -> None:
        if not 0 <= index < len(self._wheel_guests):
            return
        self._winner = self._wheel_guests[index]
        self._show_winner(self._winner, "Va la retrouver pour faire la photo ensemble.")
        self._spin.setEnabled(True)
        self._start.setEnabled(True)
        self._set_gate_hint("Tirage terminé : tu peux relever le défi !")

    def _set_gate_hint(self, text: str) -> None:
        self._gate_hint.setText(text)
        if text:
            self._gate_hint.show()
        else:
            self._gate_hint.hide()

    def _show_winner(self, winner: Guest, instruction: str) -> None:
        pseudo = escape(winner.pseudo)
        self._availability.setText(
            f"Personne tirée au sort : <big><b>{pseudo}</b></big> ! "
            f"{escape(instruction)}")

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
        if challenge.challenge_type == "guest_wheel" and self._winner is None:
            return
        self.session.challenge_id = challenge.id
        self.session.challenge_title = challenge.title
        self.session.challenge_guest_name = self._winner.pseudo if self._winner else ""
        self.session.challenge_type = challenge.challenge_type
        if challenge.challenge_type == "dance":
            self.session.photo_format = "gif"
            self.session.gif_capture_mode = "spaced"
            self.session.gif_effect = "loop"
            self.session.gif_hold_last = False
            self.session.challenge_instruction = challenge.instruction
            self.session.challenge_background_required = False
            self.session.challenge_mask = ""
            self.session.challenge_style = ""
            self.session.challenge_reference_png = None
            self.session.frame_mode = False
            self.session.frame_path = None
            self.session.background_path = None
            self.session.clear_virtual_masks()
            self.nav.go_to("capture")
            return
        self.session.dance_pose_ids = []
        self.session.challenge_instruction = challenge.instruction
        if self.session.challenge_guest_name:
            self.session.challenge_instruction += (
                f"\nPersonne à retrouver : {self.session.challenge_guest_name}")
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
        self.session.clear_virtual_masks()

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

    def _show_dance_sequence(self, pose_ids: list[int]) -> None:
        while self._dance_sequence_row.count():
            item = self._dance_sequence_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for number, pose_id in enumerate(pose_ids, start=1):
            card = QFrame()
            card.setObjectName("dancePoseCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(px(4), px(2), px(4), px(2))
            pose = DancePoseWidget(pose_id)
            pose.setMinimumSize(px(76), px(100))
            label = QLabel(f"Pose {number}")
            label.setObjectName("note")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(pose, 1)
            layout.addWidget(label)
            card.setFixedWidth(px(106))
            self._dance_sequence_row.addWidget(card)
        self._dance_sequence_row.addStretch(1)

    def _go_back(self) -> None:
        self.session.challenge_id = ""
        self.session.challenge_title = ""
        self.session.challenge_instruction = ""
        self.session.challenge_background_required = False
        self.session.challenge_mask = ""
        self.session.challenge_style = ""
        self.session.challenge_reference_png = None
        self.session.challenge_guest_name = ""
        self.session.challenge_type = "photo"
        self.session.dance_pose_ids = []
        self.nav.go_to("format_select")
