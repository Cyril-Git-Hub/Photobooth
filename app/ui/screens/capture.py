"""Écran de prise de vue : aperçu webcam avec décor, décompte, flash, enregistrement.

Photo unique : un décompte, une photo. Photomaton : une série de poses (décompte avant chacune, aperçu
rapide de la pose prise), assemblées en bande verticale à la fin.
"""
from __future__ import annotations

import logging
from enum import Enum, auto
from pathlib import Path

from datetime import datetime

import cv2
import numpy as np
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QImage, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QScroller, QStyle, QToolButton, QVBoxLayout, QWidget,
)

from ...core import backgrounds, frames, gif_builder, storage, strip_builder, virtual_masks
from ...core.challenge_stamp import stamp_challenge_title
from ...core.compositor import SceneRenderer
from ...core.qt_image import bgr_to_qimage
from ...core.segmentation import SegmentationError
from ...core.webcam import shrink
from ...paths import resource_path
from ..widgets.big_button import BigButton
from ..widgets.preview_widget import PreviewWidget
from .base import BaseScreen
from ..scale import px

log = logging.getLogger(__name__)

SAVE_ERROR = "Impossible d'enregistrer la photo.\nVérifie le dossier des photos et l'espace disque."
NO_FRAME_ERROR = "La caméra n'a pas fourni d'image."
BACKGROUND_ERROR = "Impossible de charger le décor choisi.\nReviens en arrière et choisis-en un autre, ou prends la photo sans décor."
PROCESS_ERROR = "Le détourage a échoué.\nRéessaie, ou reviens en arrière et prends la photo sans décor."
NO_FRAMES_ERROR = "Aucun cadre utilisable trouvé.\nAjoute des images PNG/WebP transparentes dans le dossier configuré, puis reviens ici."
FRAME_ERROR = "Impossible de charger ce cadre.\nChoisis-en un autre ou reviens à l'écran précédent."
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
        self._last_source_frame: np.ndarray | None = None
        self._background_cache: tuple | None = None   # (chemin, image) : évite de relire le décor à chaque reprise
        self._frame_overlay: np.ndarray | None = None
        self._frame_buttons: dict[Path, QToolButton] = {}
        self._mask_assets: dict[Path, virtual_masks.MaskAsset] = {}
        self._mask_buttons: dict[Path | None, QToolButton] = {}
        self._mask_processor: virtual_masks.FaceMaskRenderer | None = None
        self._mask_error = ""

        self._preview = PreviewWidget()
        self._frame_panel = QWidget()
        frame_layout = QVBoxLayout(self._frame_panel)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        self._frame_host = QWidget()
        self._frame_row = QHBoxLayout(self._frame_host)
        self._frame_row.setContentsMargins(px(4), px(2), px(4), px(2))
        self._frame_row.setSpacing(px(6))
        self._frame_scroll = QScrollArea()
        self._frame_scroll.setWidgetResizable(True)
        self._frame_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._frame_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._frame_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._frame_scroll.setFixedHeight(px(70))
        self._frame_scroll.setWidget(self._frame_host)
        QScroller.grabGesture(self._frame_scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        QScroller.grabGesture(self._frame_scroll.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        frame_layout.addWidget(self._frame_scroll)
        self._frame_panel.setVisible(False)

        self._mask_panel = QWidget()
        mask_layout = QVBoxLayout(self._mask_panel)
        mask_layout.setContentsMargins(0, 0, 0, 0)
        mask_layout.setSpacing(0)
        self._mask_host = QWidget()
        self._mask_row = QHBoxLayout(self._mask_host)
        self._mask_row.setContentsMargins(px(4), px(2), px(4), px(2))
        self._mask_row.setSpacing(px(6))
        self._mask_scroll = QScrollArea()
        self._mask_scroll.setWidgetResizable(True)
        self._mask_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._mask_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._mask_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Une bande compacte laisse davantage de hauteur à l'aperçu caméra.
        # La rangée reste défilante horizontalement, au doigt ou avec la barre.
        self._mask_scroll.setFixedHeight(px(70))
        self._mask_scroll.setWidget(self._mask_host)
        QScroller.grabGesture(self._mask_scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        QScroller.grabGesture(self._mask_scroll.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        mask_layout.addWidget(self._mask_scroll)
        self._mask_panel.setVisible(False)

        self._status = QLabel("")
        self._status.setObjectName("note")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._back = BigButton("Retour", "secondary")
        self._back.clicked.connect(self._go_back)
        self._action = BigButton("Prendre la photo")
        self._action.clicked.connect(lambda: self._on_action())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(30), px(30), px(30), px(30))
        layout.setSpacing(px(16))
        layout.addWidget(self._preview, 1)
        layout.addWidget(self._frame_panel)
        layout.addWidget(self._mask_panel)
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
        self.nav.capture_display.clear_countdown()
        self._timer.stop()
        self._poses = []
        self._frame_overlay = None
        self._preview.overlay.clear()
        camera = self.nav.camera
        camera.set_preview_processor(None)
        camera.set_preview_enabled(False)
        self._renderer = None
        self._mask_processor = None

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
        self._frame_overlay = None
        self._mask_processor = None
        self._mask_error = ""
        self._prepare_mask_gallery()
        if self.session.frame_mode:
            self._frame_panel.setVisible(True)
            return self._prepare_frame()
        self._frame_panel.setVisible(False)
        path = self.session.background_path
        if path is None:                       # « Sans décor » : photo normale
            self._update_preview_processor()
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
        self._update_preview_processor()
        return True

    def _prepare_mask_gallery(self) -> None:
        """Construit la rangée de masques fournis et ceux ajoutés dans masques/."""
        while self._mask_row.count():
            widget = self._mask_row.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self._mask_buttons.clear()
        defaults = resource_path("assets/masques")
        assets = virtual_masks.scan_masks([defaults, self.config.dossier_masques])
        self._mask_assets = {asset.path: asset for asset in assets}
        self._mask_panel.setVisible(bool(assets))
        if not assets:
            self.session.virtual_mask_path = None
            self.session.virtual_mask_paths.clear()
            return

        none = QToolButton()
        none.setObjectName("virtualMaskButton")
        none.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
        none.setIconSize(QSize(px(30), px(30)))
        none.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        none.setToolTip("Aucun masque")
        none.setAccessibleName("Aucun masque")
        none.setCheckable(True)
        none.setFixedSize(px(52), px(52))
        none.clicked.connect(lambda _checked=False: self._select_masks([]))
        self._mask_row.addWidget(none)
        self._mask_buttons[None] = none
        icon_size = QSize(px(40), px(40))
        for asset in assets:
            rgba = cv2.cvtColor(asset.image, cv2.COLOR_BGRA2RGBA)
            height, width = rgba.shape[:2]
            image = QImage(rgba.data, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
            thumbnail = image.scaled(icon_size, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
            button = QToolButton()
            button.setObjectName("virtualMaskButton")
            button.setIcon(QIcon(QPixmap.fromImage(thumbnail)))
            button.setIconSize(icon_size)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setToolTip(asset.name)
            button.setAccessibleName(asset.name)
            button.setCheckable(True)
            button.setFixedSize(px(52), px(52))
            button.clicked.connect(lambda checked=False, p=asset.path: self._toggle_mask(p, checked))
            self._mask_row.addWidget(button)
            self._mask_buttons[asset.path] = button
        selected = list(self.session.virtual_mask_paths)
        if not selected and self.session.virtual_mask_path is not None:
            selected = [self.session.virtual_mask_path]
        if not selected and self.session.challenge_mask:
            wanted = self.session.challenge_mask.casefold()
            match = next((asset.path for asset in assets
                          if asset.path.stem.casefold() == wanted), None)
            selected = [match] if match is not None else []
        self._select_masks([path for path in selected if path in self._mask_assets])

    def _toggle_mask(self, path: Path, checked: bool) -> None:
        selected = set(self.session.virtual_mask_paths)
        if checked:
            selected.add(path)
        else:
            selected.discard(path)
        self._select_masks(sorted(selected, key=lambda item: item.name.casefold()))

    def _select_masks(self, paths: list[Path]) -> None:
        paths = list(dict.fromkeys(path for path in paths if path in self._mask_assets))
        self.session.virtual_mask_paths = paths
        self.session.virtual_mask_path = paths[0] if paths else None
        self._mask_processor = None
        self._mask_error = ""
        assets = [self._mask_assets[path] for path in paths]
        if assets:
            try:
                self._mask_processor = virtual_masks.FaceMaskRenderer(assets)
            except Exception as exc:
                log.warning("Détection des visages indisponible : %s", exc)
                self._mask_error = "Détection visage indisponible : masque désactivé."
                self.session.virtual_mask_paths = []
                self.session.virtual_mask_path = None
                paths = []
        for button_path, button in self._mask_buttons.items():
            button.setChecked((button_path is None and not paths) or button_path in paths)
        self._update_preview_processor()
        if self._state is State.READY:
            self._update_mask_status()

    def _update_preview_processor(self) -> None:
        """Compose décor/cadre et masque dans cet ordre, pour l'aperçu webcam."""
        scene_processor = self._renderer.render_preview if self._renderer and self.config.apercu_incruste else None
        frame_overlay = self._frame_overlay if self.session.frame_mode else None
        mask_processor = self._mask_processor
        if scene_processor is None and frame_overlay is None and mask_processor is None:
            self.nav.camera.set_preview_processor(None)
            return

        def process(frame: np.ndarray) -> np.ndarray:
            rendered = scene_processor(frame) if scene_processor is not None else frame
            if frame_overlay is not None:
                rendered = frames.apply_frame(rendered, frame_overlay)
            if mask_processor is not None:
                rendered = mask_processor.process_preview(frame, rendered)
            return rendered

        self.nav.camera.set_preview_processor(process)

    def _update_mask_status(self) -> None:
        if self._state is not State.READY:
            return
        if self._mask_error:
            self._status.setText(self._challenge_status(self._mask_error))
        elif self._mask_processor is not None:
            if self._mask_processor.disabled:
                message = "Masque désactivé : la détection était trop lente. La photo reste disponible."
            elif self._mask_processor.last_face_count == 0:
                message = "Place ton visage face à la caméra pour afficher le masque."
            else:
                message = f"{len(self.session.virtual_mask_paths)} masque(s) actif(s) · {self._mask_processor.last_face_count} visage(s) détecté(s)."
            self._status.setText(self._challenge_status(message))
        else:
            self._status.setText(self._ready_status_text())

    def _ready_status_text(self) -> str:
        planned = self._planned_poses()
        message = ("Place-toi et prends la photo !" if self.session.frame_mode else
                   f"Prépare-toi : {planned} images pour ton GIF animé !" if self.session.photo_format == "gif" else
                   "Place-toi dans le cadre, puis appuie sur le bouton !" if planned == 1 else
                   f"Place-toi dans le cadre : {planned} photos vont être prises à la suite !")
        return self._challenge_status(message)

    def _challenge_status(self, message: str) -> str:
        if self.session.challenge_instruction:
            return f"Défi : {self.session.challenge_instruction}\n{message}"
        return message

    def _prepare_frame(self) -> bool:
        """Construit le choix de cadres et démarre l'aperçu avec le cadre sélectionné."""
        while self._frame_row.count():
            widget = self._frame_row.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self._frame_buttons.clear()
        icon_size = QSize(px(40), px(40))
        frame_folder = self.nav.theme.frames if self.nav.theme and self.nav.theme.frames.exists() else self.config.dossier_cadres
        available_frames = [(path, frames.load_frame(path)) for path in frames.scan_frames(frame_folder)]
        available_frames = [(path, overlay) for path, overlay in available_frames if overlay is not None]
        if not available_frames and frame_folder != self.config.dossier_cadres:
            frame_folder = self.config.dossier_cadres
            available_frames = [(path, frames.load_frame(path)) for path in frames.scan_frames(frame_folder)]
            available_frames = [(path, overlay) for path, overlay in available_frames if overlay is not None]
        for path, overlay in available_frames:
            rgba = cv2.cvtColor(overlay, cv2.COLOR_BGRA2RGBA)
            height, width = rgba.shape[:2]
            image = QImage(rgba.data, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
            thumbnail = image.scaled(icon_size, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
            button = QToolButton()
            button.setObjectName("captureChoiceButton")
            button.setIcon(QIcon(QPixmap.fromImage(thumbnail)))
            button.setIconSize(icon_size)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setToolTip(path.stem)
            button.setAccessibleName(path.stem)
            button.setCheckable(True)
            button.setFixedSize(px(52), px(52))
            button.clicked.connect(lambda _checked=False, p=path: self._select_frame(p))
            self._frame_row.addWidget(button)
            self._frame_buttons[path] = button
        if not self._frame_buttons:
            self._fail(f"{NO_FRAMES_ERROR}\n({frame_folder})")
            return False

        selected = self.session.frame_path if self.session.frame_path in self._frame_buttons else next(iter(self._frame_buttons))
        return self._select_frame(selected)

    def _select_frame(self, path: Path) -> bool:
        overlay = frames.load_frame(path)
        if overlay is None:
            self._frame_overlay = None
            self._fail(FRAME_ERROR)
            return False
        self._frame_overlay = overlay
        self.session.frame_path = path
        self._update_preview_processor()
        for button_path, button in self._frame_buttons.items():
            button.setChecked(button_path == path)
        if self._state is State.ERROR:
            self._set_state(State.ERROR)  # recalcule l'état du bouton « Réessayer » après un changement de cadre
        return True

    def _go_back(self) -> None:
        if self.session.challenge_id:
            self.nav.go_to("challenge")
        elif self.session.photo_format == "gif":
            self.nav.go_to("gif_options")
        elif self.session.frame_mode:
            self.nav.go_to("format_select")
        else:
            self.nav.go_back()

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
        for button in self._frame_buttons.values():
            button.setEnabled(not busy)
        for button in self._mask_buttons.values():
            button.setEnabled(not busy)
        frame_ready = not self.session.frame_mode or self._frame_overlay is not None
        self._action.setEnabled(state in (State.READY, State.ERROR) and frame_ready)
        action_text = "Lancer le GIF" if self.session.photo_format == "gif" else "Lancer le photomaton"
        self._action.setText("Réessayer" if state is State.ERROR
                             else "Prendre la photo" if planned == 1 else action_text)
        self._status.setText("")
        if state is State.STARTING:
            self._preview.set_message("Démarrage de la caméra…")
        elif state is State.READY:
            self._status.setText(self._ready_status_text())
            self._update_mask_status()
        elif state is State.ERROR:
            self._preview.set_message(self._error_text)

    def _planned_poses(self) -> int:
        if self.session.photo_format == "gif":
            return (self.config.gif_poses_rafale if self.session.gif_capture_mode == "burst"
                    else self.config.gif_poses_espacees)
        return self.config.nb_poses if self.session.photo_format == "strip" and self.config.nb_poses >= 2 else 1

    def _fail(self, text: str) -> None:
        self._timer.stop()
        self.nav.capture_display.clear_countdown()
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
            elif self._state is State.READY:
                self._update_mask_status()
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
        active_event = self.nav.events.active_event()
        self.session.event_id = active_event.id if active_event is not None else ""
        self._start_countdown(self.config.duree_decompte)

    def _start_countdown(self, seconds: int) -> None:
        self._remaining = max(1, seconds)
        self._set_state(State.COUNTING)
        self.nav.sounds.play("countdown")
        if self._total > 1:
            self._status.setText(f"Pose {len(self._poses) + 1}/{self._total}")
        self._preview.overlay.show_number(str(self._remaining))
        self.nav.capture_display.set_countdown(str(self._remaining))
        self._timer.start()

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining > 0:
            self.nav.sounds.play("countdown")
            self._preview.overlay.show_number(str(self._remaining))
            self.nav.capture_display.set_countdown(str(self._remaining))
        else:
            self._timer.stop()
            self.nav.capture_display.clear_countdown()
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
        self._last_source_frame = frame.copy()
        if self._renderer is not None:
            try:
                frame = self._renderer.render_photo(frame)
            except Exception:
                log.exception("Échec du détourage de la photo")
                self._fail(PROCESS_ERROR)
                return None
        elif self.session.frame_mode and self._frame_overlay is not None:
            try:
                frame = frames.apply_frame(frame, self._frame_overlay)
            except Exception:
                log.exception("Échec de l'incrustation du cadre")
                self._fail(FRAME_ERROR)
                return None
        if self._mask_processor is not None:
            frame = self._mask_processor.apply_photo(self._last_source_frame, frame)
        return frame

    def _capture_pose(self) -> None:
        self._set_state(State.SAVING)
        self.nav.capture_display.clear_countdown()
        self.nav.sounds.play("shutter")
        self._preview.overlay.clear()
        self._preview.overlay.flash()
        frame = self._grab_final_frame()
        if frame is None:
            return
        self._poses.append(frame)
        if len(self._poses) < self._total:
            if self.session.photo_format == "gif" and self.session.gif_capture_mode == "burst":
                self._status.setText(f"Image {len(self._poses)}/{self._total}…")
                QTimer.singleShot(self.config.gif_intervalle_rafale_ms, self._capture_burst_frame)
            else:
                self._show_pose(frame)
        else:
            self._save_and_finish()

    def _capture_burst_frame(self) -> None:
        if self._active and self._state is State.SAVING:
            self._capture_pose()

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
        challenge_title = self.session.challenge_title.strip()
        try:
            if self.session.photo_format == "gif":
                gif_frames = [stamp_challenge_title(frame, challenge_title) for frame in self._poses]
                path = gif_builder.save_gif(
                    self.config, gif_frames, guest,
                    effect=self.session.gif_effect, hold_last=self.session.gif_hold_last,
                )
                self.session.photos.append(path)
                self.session.photo_source_frame = None
                self.session.photo_style = "original"
                self.session.photo_style_person_only = False
            elif self._total == 1:
                photo = stamp_challenge_title(self._poses[0], challenge_title)
                path = storage.save_photo(self.config, photo, guest)
                self.session.photos.append(path)
                self.session.photo_source_frame = self._last_source_frame
                self.session.photo_style = "original"
                self.session.photo_style_person_only = False
            else:
                style = strip_builder.StripStyle(
                    title=self.config.pm_titre, date_text=datetime.now().strftime("%d/%m/%Y"),
                    background=self.config.pm_couleur_fond, text_color=self.config.pm_couleur_texte)
                strip = strip_builder.build_strip(self._poses, style)
                strip = stamp_challenge_title(strip, challenge_title)
                path, pose_paths = storage.save_strip(self.config, strip, self._poses, guest)
                self.session.photos.append(path)
                self.session.poses = pose_paths
                self.session.photo_source_frame = None
                self.session.photo_style = "original"
                self.session.photo_style_person_only = False
        except (OSError, ValueError, cv2.error):
            log.exception("Échec de l'enregistrement de la photo")
            self._fail(SAVE_ERROR)
            return
        self._poses = []
        QTimer.singleShot(FLASH_PAUSE_MS, self._finish)

    def _finish(self) -> None:
        if self._active and self._state is State.SAVING:
            self.nav.go_next()
