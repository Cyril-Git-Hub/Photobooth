"""Écran de prise de vue : aperçu webcam avec décor, décompte, flash, enregistrement.

Photo unique : un décompte, une photo. Photomaton : une série de poses (décompte avant chacune, aperçu
rapide de la pose prise), assemblées en bande verticale à la fin.
"""
from __future__ import annotations

import logging
from enum import Enum, auto

from datetime import datetime

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from ...core import backgrounds, storage, strip_builder
from ...core.compositor import SceneRenderer
from ...core.qt_image import bgr_to_qimage
from ...core.segmentation import SegmentationError
from ...core.webcam import shrink
from ..widgets.big_button import BigButton
from ..widgets.preview_widget import PreviewWidget
from .base import BaseScreen
from ..scale import px

log = logging.getLogger(__name__)

SAVE_ERROR = "Impossible d'enregistrer la photo.\nVérifie le dossier des photos et l'espace disque."
NO_FRAME_ERROR = "La caméra n'a pas fourni d'image."
BACKGROUND_ERROR = "Impossible de charger le décor choisi.\nReviens en arrière et choisis-en un autre, ou prends la photo sans décor."
PROCESS_ERROR = "Le détourage a échoué.\nRéessaie, ou reviens en arrière et prends la photo sans décor."
FLASH_PAUSE_MS = 700        # on laisse le flash se voir avant de passer à l'aperçu du résultat
POSE_REVIEW_MS = 1600       # photomaton : durée d'affichage de la pose qui vient d'être prise


class State(Enum):
    STARTING = auto()   # la caméra démarre
    READY = auto()      # aperçu en direct, bouton « Prendre la photo »
    COUNTING = auto()   # décompte en cours
    POSE_REVIEW = auto()  # photomaton : la pose prise s'affiche un instant avant la suivante
    SAVING = auto()     # flash + détourage + enregistrement
    ERROR = auto()      # message d'erreur + bouton « Réessayer »


class CaptureScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._state = State.STARTING
        self._active = False
        self._remaining = 0
        self._total = 1                                 # nombre de poses de la séquence en cours
        self._poses: list[np.ndarray] = []              # poses déjà prises (images finales, décor inclus)
        self._error_text = ""
        self._renderer: SceneRenderer | None = None
        self._background_cache: tuple | None = None   # (chemin, image) : évite de relire le décor à chaque reprise

        self._preview = PreviewWidget()
        self._status = QLabel("")
        self._status.setObjectName("note")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._back = BigButton("Retour", "secondary")
        self._back.clicked.connect(lambda: self.nav.go_back())
        self._action = BigButton("Prendre la photo")
        self._action.clicked.connect(lambda: self._on_action())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(30), px(30), px(30), px(30))
        layout.setSpacing(px(16))
        layout.addWidget(self._preview, 1)
        layout.addWidget(self._status)
        row = QHBoxLayout()
        row.setSpacing(px(30))
        row.addStretch(1)
        row.addWidget(self._back)
        row.addWidget(self._action)
        row.addStretch(1)
        layout.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        nav.camera.preview_ready.connect(self._on_preview)
        nav.camera.failed.connect(self._on_camera_failed)

    @property
    def allow_inactivity_reset(self) -> bool:
        # pas de retour automatique à l'accueil au milieu d'une prise
        return self._state not in (State.COUNTING, State.POSE_REVIEW, State.SAVING)

    # ---------- cycle de vie ----------

    def on_enter(self) -> None:
        self._active = True
        self._begin()

    def on_leave(self) -> None:
        self._active = False
        self._timer.stop()
        self._poses = []
        self._preview.overlay.clear()
        camera = self.nav.camera
        camera.set_preview_processor(None)
        camera.set_preview_enabled(False)
        self._renderer = None

    def _begin(self) -> None:
        """Prépare le décor puis démarre (ou reprend) l'aperçu. Appelé à l'arrivée et par « Réessayer »."""
        self._poses = []
        if not self._prepare_scene():
            return
        camera = self.nav.camera
        camera.set_preview_enabled(True)
        camera.start_camera()
        self._set_state(State.READY if camera.has_frame() else State.STARTING)

    def _prepare_scene(self) -> bool:
        camera = self.nav.camera
        camera.set_preview_processor(None)
        self._renderer = None
        path = self.session.background_path
        if path is None:                       # « Sans décor » : photo normale
            return True
        background = self._load_background(path)
        if background is None:
            self._fail(BACKGROUND_ERROR)
            return False
        try:
            segmenter = self.nav.get_segmenter()
        except SegmentationError as exc:
            log.error("Détourage indisponible : %s", exc.args[0])
            self._fail(exc.args[0])
            return False
        self._renderer = SceneRenderer(segmenter, background)
        if self.config.apercu_incruste:
            camera.set_preview_processor(self._renderer.render_preview)
        return True

    def _load_background(self, path):
        if self._background_cache is not None and self._background_cache[0] == path:
            return self._background_cache[1]
        image = backgrounds.load_image(path)
        self._background_cache = (path, image) if image is not None else None
        return image

    # ---------- états ----------

    def _set_state(self, state: State) -> None:
        self._state = state
        busy = state in (State.COUNTING, State.POSE_REVIEW, State.SAVING)
        planned = self._planned_poses()
        self._back.setEnabled(not busy)
        self._action.setEnabled(state in (State.READY, State.ERROR))
        self._action.setText("Réessayer" if state is State.ERROR
                             else "Prendre la photo" if planned == 1 else "Lancer le photomaton")
        self._status.setText("")
        if state is State.STARTING:
            self._preview.set_message("Démarrage de la caméra…")
        elif state is State.READY:
            self._status.setText("Place-toi dans le cadre, puis appuie sur le bouton !" if planned == 1 else
                                 f"Place-toi dans le cadre : {planned} photos vont être prises à la suite !")
        elif state is State.ERROR:
            self._preview.set_message(self._error_text)

    def _planned_poses(self) -> int:
        return self.config.nb_poses if self.session.photo_format == "strip" and self.config.nb_poses >= 2 else 1

    def _fail(self, text: str) -> None:
        self._timer.stop()
        self._poses = []
        self._preview.overlay.clear()
        self._error_text = text
        self._set_state(State.ERROR)

    # ---------- caméra ----------

    def _on_preview(self, image: QImage) -> None:
        try:
            if not self._active or self._state is State.POSE_REVIEW:   # la pose prise reste affichée
                return
            self._preview.set_image(image)
            if self._state is State.STARTING:
                self._set_state(State.READY)
        finally:
            self.nav.camera.preview_consumed()

    def _on_camera_failed(self, message: str) -> None:
        log.error("Caméra en échec : %s", message)
        if self._active:
            self._fail(message)

    # ---------- actions ----------

    def _on_action(self) -> None:
        if self._state is State.READY:
            self._start_sequence()
        elif self._state is State.ERROR:
            self._begin()   # recharge le décor si besoin, relance la caméra si elle est perdue

    def _start_sequence(self) -> None:
        self._total = self._planned_poses()
        self._poses = []
        self._start_countdown(self.config.duree_decompte)

    def _start_countdown(self, seconds: int) -> None:
        self._remaining = max(1, seconds)
        self._set_state(State.COUNTING)
        if self._total > 1:
            self._status.setText(f"Pose {len(self._poses) + 1}/{self._total}")
        self._preview.overlay.show_number(str(self._remaining))
        self._timer.start()

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining > 0:
            self._preview.overlay.show_number(str(self._remaining))
        else:
            self._timer.stop()
            self._capture_pose()

    def _grab_final_frame(self) -> np.ndarray | None:
        """Image finale de la pose (miroir et décor appliqués) ; None si la prise a échoué (erreur déjà affichée)."""
        frame = self.nav.camera.grab_frame()
        if frame is None:
            self._fail(NO_FRAME_ERROR)
            return None
        if self.config.miroir:
            # même inversion que l'aperçu : la photo est exactement ce que l'invité a vu
            frame = cv2.flip(frame, 1)   # avant le décor : le décor n'est jamais inversé
        if self._renderer is not None:
            try:
                frame = self._renderer.render_photo(frame)
            except Exception:
                log.exception("Échec du détourage de la photo")
                self._fail(PROCESS_ERROR)
                return None
        return frame

    def _capture_pose(self) -> None:
        self._set_state(State.SAVING)
        self._preview.overlay.clear()
        self._preview.overlay.flash()
        frame = self._grab_final_frame()
        if frame is None:
            return
        self._poses.append(frame)
        if len(self._poses) < self._total:
            self._show_pose(frame)
        else:
            self._save_and_finish()

    def _show_pose(self, frame: np.ndarray) -> None:
        """Photomaton : la pose qui vient d'être prise reste affichée un instant, puis le décompte reprend."""
        self._set_state(State.POSE_REVIEW)
        self._preview.set_image(bgr_to_qimage(shrink(frame, self.config.apercu_largeur)))
        self._status.setText(f"Pose {len(self._poses)}/{self._total} enregistrée ! Change de position…")
        QTimer.singleShot(POSE_REVIEW_MS, self._next_pose)

    def _next_pose(self) -> None:
        if self._active and self._state is State.POSE_REVIEW:
            self._start_countdown(self.config.pm_decompte_entre_poses)

    def _save_and_finish(self) -> None:
        guest = self.session.display_name
        try:
            if self._total == 1:
                self.session.photos.append(storage.save_photo(self.config, self._poses[0], guest))
            else:
                style = strip_builder.StripStyle(
                    title=self.config.pm_titre, date_text=datetime.now().strftime("%d/%m/%Y"),
                    background=self.config.pm_couleur_fond, text_color=self.config.pm_couleur_texte)
                strip = strip_builder.build_strip(self._poses, style)
                path, pose_paths = storage.save_strip(self.config, strip, self._poses, guest)
                self.session.photos.append(path)
                self.session.poses = pose_paths
        except (OSError, ValueError, cv2.error):
            log.exception("Échec de l'enregistrement de la photo")
            self._fail(SAVE_ERROR)
            return
        self._poses = []
        QTimer.singleShot(FLASH_PAUSE_MS, self._finish)

    def _finish(self) -> None:
        if self._active and self._state is State.SAVING:
            self.nav.go_next()
