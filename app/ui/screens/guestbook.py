"""Consentement tactile et enregistrement facultatif d'un message vidéo de soirée."""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from pathlib import Path

import cv2
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from ...core.video_guestbook import VideoGuestbookRecorder, event_folder
from ...core.qt_image import bgr_to_qimage
from ..scale import px
from ..widgets.big_button import BigButton
from .base import BaseScreen

log = logging.getLogger(__name__)


class GuestbookScreen(BaseScreen):
    allow_inactivity_reset = False

    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._title = QLabel("Livre d'or")
        self._title.setObjectName("heading")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hero_image = QLabel()
        self._hero_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hero_image.setMaximumHeight(px(420))
        self._hero_image.setMinimumHeight(px(220))
        self._hero_pixmap = QPixmap()
        self._invitation_title = QLabel("🎬 À VOUS DE JOUER !")
        self._invitation_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._invitation_title.setObjectName("heading")
        self._invitation_title.setStyleSheet("font-size: 46px; font-weight: 700;")
        self._invitation = QLabel(
            "Lola fête ses 18 ans… laissez votre réplique !\n"
            "Prenez la caméra, faites passer un message, racontez une anecdote ou souhaitez-lui le meilleur. "
            "Le clap est lancé pour 15 secondes !"
        )
        self._invitation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._invitation.setWordWrap(True)
        self._invitation.setObjectName("note")
        self._message = QLabel()
        self._message.setObjectName("note")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(px(640), px(360))
        self._preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._preview.setScaledContents(False)
        self._preview_pixmap = QPixmap()
        self._preview.hide()
        self._countdown_label = QLabel(self._preview)
        self._countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._countdown_label.setStyleSheet(
            "background: transparent; font-size: 88px; font-weight: 700; color: #ffd166;"
        )
        self._countdown_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._countdown_label.hide()
        self._timer_label = QLabel()
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._actions = QHBoxLayout()
        self._actions.setSpacing(px(20))
        self._back = BigButton("Retour", "secondary")
        self._back.clicked.connect(lambda: self.nav.go_to("format_select"))
        self._start = BigButton("Continuer", "notListed")
        self._start.clicked.connect(self._accept)
        self._record = BigButton("Action !", "notListed")
        self._record.clicked.connect(self._begin_recording)
        self._stop = BigButton("Terminer l'enregistrement", "secondary")
        self._stop.clicked.connect(self._stop_recording)
        self._done = BigButton("Terminer", "secondary")
        self._done.clicked.connect(self._finish)
        self._cancel = BigButton("Annuler", "secondary")
        self._cancel.clicked.connect(self._cancel_action)
        self._validate_video = BigButton("Valider et enregistrer", "notListed")
        self._validate_video.clicked.connect(self._save_pending_video)
        self._retry_video = BigButton("Refaire la vidéo", "secondary")
        self._retry_video.clicked.connect(self._retry_recording)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh_remaining)
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._countdown_tick)
        self._countdown_remaining = 0
        self._recorder: VideoGuestbookRecorder | None = None
        self._pending_video: Path | None = None
        self._pending_folder: Path | None = None
        self._final_video: Path | None = None
        self._video_capture: cv2.VideoCapture | None = None
        self._video_preview_timer = QTimer(self)
        self._video_preview_timer.setInterval(50)
        self._video_preview_timer.timeout.connect(self._show_video_preview_frame)
        self._recording_started_at = 0.0
        self._event_id = ""
        self._camera_error_message = ""
        self._showing_video_review = False
        self.nav.camera.preview_ready.connect(self._on_preview)
        self.nav.camera.failed.connect(self._on_camera_failed)
        self.apply_theme(nav.theme)

    def apply_theme(self, theme) -> None:
        if theme is None:
            return
        self._title.setText(theme.guestbook_title)
        self._invitation_title.setText(theme.guestbook_invitation_title)
        self._invitation.setText(theme.guestbook_invitation)
        accent = theme.colors.get("accent", "#ffd166")
        self._countdown_label.setStyleSheet(
            f"background: transparent; font-size: 88px; font-weight: 700; color: {accent};"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(36), px(24), px(36), px(24))
        layout.setSpacing(px(10))
        layout.addWidget(self._invitation_title)
        layout.addWidget(self._hero_image)
        layout.addWidget(self._title)
        layout.addWidget(self._invitation)
        layout.addWidget(self._message)
        layout.addWidget(self._preview, 1)
        layout.addWidget(self._timer_label)
        layout.addLayout(self._actions)

    def on_enter(self) -> None:
        self.nav.capture_display.set_live_preview(False)
        self._event_id = self.session.event_id
        self._preview.clear()
        self._preview_pixmap = QPixmap()
        self._preview.hide()
        self._countdown_timer.stop()
        self._countdown_label.clear()
        self._countdown_label.hide()
        self._hero_image.show()
        self._invitation_title.show()
        self._title.show()
        self._invitation.show()
        self._load_hero_image()
        QTimer.singleShot(0, self._scale_hero_image)
        self._timer_label.clear()
        self._stop_video_preview()
        self._show_actions(self._start)
        self._message.clear()
        self._message.hide()

    def _load_hero_image(self) -> None:
        theme_folder = getattr(self.nav.theme, "folder", self.config.dossier_theme)
        visual_folder = theme_folder / "visuels"
        candidates = (
            visual_folder / "livre_or.png", visual_folder / "livre_or.jpg",
            visual_folder / "livre_or.jpeg", visual_folder / "guestbook.png",
        )
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            log.warning("Image d'accueil du livre d'or introuvable dans %s", visual_folder)
            self._hero_pixmap = QPixmap()
            self._hero_image.hide()
            return
        self._hero_pixmap = QPixmap(str(path)) if path is not None else QPixmap()
        if self._hero_pixmap.isNull():
            log.warning("Image d'accueil du livre d'or illisible : %s", path)
        self._hero_image.setVisible(not self._hero_pixmap.isNull())
        self._scale_hero_image()

    def _scale_hero_image(self) -> None:
        if self._hero_pixmap.isNull() or self._hero_image.size().isEmpty():
            return
        self._hero_image.setPixmap(self._hero_pixmap.scaled(
            self._hero_image.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._scale_hero_image()
        self._countdown_label.setGeometry(self._preview.rect())
        self._scale_preview_image()

    def on_leave(self) -> None:
        self.nav.capture_display.set_live_preview(False)
        self._timer.stop()
        self._countdown_timer.stop()
        self.nav.camera.set_preview_enabled(False)
        self._stop_video_preview()
        if self._recorder is not None and self._recorder.isRunning():
            self._recorder.cancel_recording()

    def _accept(self) -> None:
        active_event = self.nav.events.active_event()
        if not self._event_id or active_event is None or active_event.id != self._event_id:
            self._message.setText("Aucune soirée active : le message vidéo ne peut pas être classé.")
            self._message.show()
            self._show_actions()
            return
        try:
            folder = event_folder(self.config, self._event_id)
            folder.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            log.exception("Préparation du dossier du livre d'or impossible")
            self._message.setText(f"Le livre d'or n'est pas disponible : {exc}")
            self._message.show()
            self._show_actions()
            return
        camera = self.nav.camera
        self._camera_error_message = ""
        self._showing_video_review = False
        self._hero_image.hide()
        self._invitation_title.hide()
        self._invitation.hide()
        camera.set_preview_processor(None)
        camera.set_preview_enabled(True)
        self.nav.capture_display.set_live_preview(True)
        if not camera.is_active():
            camera.start_camera()
        self._message.setText("Place-toi devant la caméra, puis touche « Action ! ».")
        self._message.show()
        self._preview.show()
        self._countdown_label.setGeometry(self._preview.rect())
        self._show_actions(self._record)

    def _on_preview(self, image: QImage) -> None:
        try:
            if self.nav.current_name != "guestbook" or self._showing_video_review:
                return
            self._preview_pixmap = QPixmap.fromImage(image)
            self._scale_preview_image()
        finally:
            self.nav.camera.preview_consumed()

    def _on_camera_failed(self, message: str) -> None:
        if self.nav.current_name != "guestbook":
            return
        self._camera_error_message = message
        log.error("Caméra indisponible pour le livre d'or : %s", message)
        self._countdown_timer.stop()
        self._countdown_label.clear()
        self._countdown_label.hide()
        self.nav.capture_display.set_live_preview(False)
        if self._recorder is not None and self._recorder.isRunning():
            self._recorder.cancel_recording()
            self._timer.stop()
            self._show_actions(self._back)
        self._message.setText(message)
        self._message.show()
        if self._recorder is None or not self._recorder.isRunning():
            self._show_actions()

    def _begin_recording(self) -> None:
        self._countdown_remaining = 3
        self._countdown_label.setText(str(self._countdown_remaining))
        self._countdown_label.setGeometry(self._preview.rect())
        self._countdown_label.show()
        self._countdown_label.raise_()
        self._show_actions()
        self._countdown_timer.start()

    def _countdown_tick(self) -> None:
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
            self._countdown_label.clear()
            self._countdown_label.hide()
            self._start_recording()
            return
        self._countdown_label.setText(str(self._countdown_remaining))

    def _start_recording(self) -> None:
        folder = event_folder(self.config, self._event_id)
        filename = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:8]}.mp4"
        self._final_video = folder / filename
        pending_folder = folder / "_en_attente"
        try:
            pending_folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.exception("Création du dossier temporaire du livre d'or impossible")
            self._message.setText(f"Impossible de préparer la vidéo : {exc}")
            self._message.show()
            self._show_actions(self._record)
            return
        self._pending_folder = pending_folder
        pending_video = pending_folder / filename
        self._recorder = VideoGuestbookRecorder(self._grab_recording_frame, pending_video, self)
        self._recorder.remaining.connect(self._set_remaining)
        self._recorder.completed.connect(self._recording_completed)
        self._recorder.cancelled.connect(self._recording_cancelled)
        self._recorder.failed.connect(self._recording_failed)
        self._recording_started_at = time.monotonic()
        self._message.setText("Enregistrement en cours. Touche le bouton pour arrêter, ou attends la fin des 15 secondes.")
        self._show_actions(self._stop, self._cancel)
        self._timer.start()
        self._recorder.start()

    def _scale_preview_image(self) -> None:
        if self._preview_pixmap.isNull() or self._preview.size().isEmpty():
            return
        self._preview.setPixmap(self._preview_pixmap.scaled(
            self._preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def _stop_recording(self) -> None:
        if self._recorder is not None and self._recorder.isRunning() and self._stop.isEnabled():
            log.info("Arrêt manuel de l'enregistrement du livre d'or demandé")
            self._recorder.stop_recording()
            self._timer.stop()
            self._timer_label.clear()
            self._stop.setEnabled(False)
            self._stop.hide()
            self._cancel.hide()
            self._message.setText("Finalisation du message…")

    def _grab_recording_frame(self):
        frame = self.nav.camera.grab_frame()
        return cv2.flip(frame, 1) if frame is not None and self.config.miroir else frame

    def _refresh_remaining(self) -> None:
        remaining = max(0, 15 - int(time.monotonic() - self._recording_started_at))
        self._set_remaining(remaining)

    def _set_remaining(self, seconds: int) -> None:
        self._timer_label.setText(f"Temps restant : {seconds} s")
        if seconds <= 0:
            self._stop_recording()

    def _recording_completed(self, path: str) -> None:
        self._timer.stop()
        self._showing_video_review = True
        self._pending_video = Path(path)
        log.info("Vidéo du livre d'or en attente de validation : %s", path)
        self.nav.capture_display.set_live_preview(False)
        self.nav.camera.set_preview_enabled(False)
        self._hero_image.hide()
        self._invitation_title.hide()
        self._title.hide()
        self._invitation.hide()
        self._preview_pixmap = QPixmap()
        self._preview.show()
        self._timer_label.clear()
        self._countdown_label.clear()
        self._countdown_label.hide()
        self._message.setText("Regarde la vidéo, puis choisis si tu veux l'enregistrer ou la refaire.")
        self._message.show()
        self._start_video_preview(self._pending_video)
        self._show_actions(self._validate_video, self._retry_video, self._cancel)

    def _start_video_preview(self, path: Path) -> None:
        self._stop_video_preview()
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            capture.release()
            log.warning("Aperçu de la vidéo impossible : %s", path)
            self._message.setText("Aperçu indisponible. Tu peux quand même valider ou refaire la vidéo.")
            return
        self._video_capture = capture
        self._video_preview_timer.start()
        self._show_video_preview_frame()

    def _show_video_preview_frame(self) -> None:
        if self._video_capture is None:
            return
        ok, frame = self._video_capture.read()
        if not ok:
            self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._video_capture.read()
        if ok:
            self._preview_pixmap = QPixmap.fromImage(bgr_to_qimage(frame))
            self._scale_preview_image()

    def _stop_video_preview(self) -> None:
        self._video_preview_timer.stop()
        if self._video_capture is not None:
            self._video_capture.release()
            self._video_capture = None

    def _save_pending_video(self) -> None:
        if self._pending_video is None or self._final_video is None or not self._pending_video.is_file():
            self._message.setText("La vidéo en attente est introuvable. Tu peux refaire l'enregistrement.")
            self._message.show()
            self._show_actions(self._retry_video, self._cancel)
            return
        self._stop_video_preview()
        try:
            self._pending_video.replace(self._final_video)
        except OSError as exc:
            log.exception("Enregistrement validé du livre d'or impossible")
            self._message.setText(f"La vidéo n'a pas pu être enregistrée : {exc}")
            self._message.show()
            return
        log.info("Vidéo du livre d'or enregistrée : %s", self._final_video)
        try:
            self._pending_video.parent.rmdir()
        except OSError:
            pass
        self._pending_video = None
        self._pending_folder = None
        self._final_video = None
        self._preview.hide()
        self._message.setText("Merci ! Ton message vidéo est enregistré pour cette soirée.")
        self._show_actions(self._done)

    def _retry_recording(self) -> None:
        self._discard_pending_video()
        self._camera_error_message = ""
        self._showing_video_review = False
        self._hero_image.hide()
        self._invitation_title.hide()
        self._title.hide()
        self._invitation.hide()
        self.nav.camera.set_preview_processor(None)
        self.nav.camera.set_preview_enabled(True)
        self.nav.capture_display.set_live_preview(True)
        if not self.nav.camera.is_active():
            self.nav.camera.start_camera()
        self._preview.show()
        self._message.setText("Place-toi devant la caméra, puis touche « Action ! ».")
        self._show_actions(self._record)

    def _cancel_action(self) -> None:
        if self._recorder is not None and self._recorder.isRunning():
            log.info("Annulation de l'enregistrement du livre d'or demandée")
            self._recorder.cancel_recording()
            self._timer.stop()
            self._timer_label.clear()
            self._stop.hide()
            self._cancel.hide()
            self._message.setText("Annulation de l'enregistrement…")
            self._show_actions(self._back)
            return
        self._discard_pending_video()
        self.nav.go_home()

    def _recording_cancelled(self) -> None:
        self._timer.stop()
        self._timer_label.clear()
        if self._pending_folder is not None:
            try:
                self._pending_folder.rmdir()
            except OSError:
                pass
            self._pending_folder = None
        self._message.setText(self._camera_error_message or "Vidéo annulée. Tu peux recommencer.")
        self._message.show()
        self._final_video = None
        self._show_actions(self._back if self._camera_error_message else self._record)

    def _discard_pending_video(self) -> None:
        self._stop_video_preview()
        if self._pending_video is not None:
            self._pending_video.unlink(missing_ok=True)
        if self._pending_folder is not None:
            try:
                self._pending_folder.rmdir()
            except OSError:
                pass
        self._pending_video = None
        self._pending_folder = None
        self._final_video = None

    def _recording_failed(self, message: str) -> None:
        self._timer.stop()
        if self._pending_folder is not None:
            try:
                self._pending_folder.rmdir()
            except OSError:
                pass
        self._pending_folder = None
        self._pending_video = None
        self._final_video = None
        log.error("Échec du livre d'or vidéo : %s", message)
        self.nav.capture_display.set_live_preview(False)
        self._message.setText(f"Le message n'a pas pu être enregistré. {message}")
        self._message.show()
        self._timer_label.clear()
        self._countdown_label.clear()
        self._countdown_label.hide()
        self._show_actions()

    def _show_actions(self, *buttons) -> None:
        all_buttons = (self._start, self._record, self._stop, self._done, self._back,
                       self._cancel, self._validate_video, self._retry_video)
        for button in all_buttons:
            button.hide()
        while self._actions.count():
            self._actions.takeAt(0)
        self._actions.addStretch(1)
        decision_buttons = (self._cancel, self._validate_video, self._retry_video)
        if (self._stop not in buttons and self._back not in buttons
                and not any(button in decision_buttons for button in buttons)):
            buttons = (self._back, *buttons)
        for button in buttons:
            button.setEnabled(True)
            button.show()
            self._actions.addWidget(button)
        self._actions.addStretch(1)

    def _finish(self) -> None:
        self.nav.go_home()

    def stop_and_wait(self) -> None:
        if self._recorder is not None and self._recorder.isRunning():
            self._recorder.stop_recording()
            if not self._recorder.wait(15_000):
                log.warning("L'enregistrement du livre d'or est encore en cours à la fermeture")
