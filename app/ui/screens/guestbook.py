"""Consentement tactile et enregistrement facultatif d'un message vidéo de soirée."""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

import cv2
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from ...core.video_guestbook import VideoGuestbookRecorder, event_folder
from ..scale import px
from ..widgets.big_button import BigButton
from .base import BaseScreen

log = logging.getLogger(__name__)


class GuestbookScreen(BaseScreen):
    allow_inactivity_reset = False

    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._title = QLabel("Livre d'or vidéo")
        self._title.setObjectName("heading")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message = QLabel()
        self._message.setObjectName("note")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(px(640), px(360))
        self._preview.hide()
        self._timer_label = QLabel()
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._actions = QHBoxLayout()
        self._actions.setSpacing(px(20))
        self._skip = BigButton("Continuer sans message", "secondary")
        self._skip.clicked.connect(self._finish)
        self._start = BigButton("Accepter et continuer")
        self._start.clicked.connect(self._accept)
        self._record = BigButton("Enregistrer mon message")
        self._record.clicked.connect(self._begin_recording)
        self._stop = BigButton("Terminer l'enregistrement", "secondary")
        self._stop.clicked.connect(self._stop_recording)
        self._done = BigButton("Terminer", "secondary")
        self._done.clicked.connect(self._finish)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh_remaining)
        self._recorder: VideoGuestbookRecorder | None = None
        self._recording_started_at = 0.0
        self._event_id = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(36), px(24), px(36), px(24))
        layout.setSpacing(px(14))
        layout.addWidget(self._title)
        layout.addWidget(self._message)
        layout.addWidget(self._preview, 1)
        layout.addWidget(self._timer_label)
        layout.addLayout(self._actions)

    def on_enter(self) -> None:
        self._event_id = self.session.event_id
        self._preview.clear()
        self._preview.hide()
        self._timer_label.clear()
        self._show_actions(self._start, self._skip)
        self._message.setText(
            "Veux-tu laisser un message vidéo ? Il sera conservé sur cet ordinateur dans le dossier "
            "de la soirée. L'organisateur pourra le regarder, l'exporter ou le supprimer depuis "
            "l'administration. La vidéo et ta voix seront enregistrées, pendant 15 secondes maximum."
        )

    def on_leave(self) -> None:
        self._timer.stop()
        self.nav.camera.set_preview_enabled(False)
        if self._recorder is not None and self._recorder.isRunning():
            self._recorder.stop_recording()

    def _accept(self) -> None:
        active_event = self.nav.events.active_event()
        if not self._event_id or active_event is None or active_event.id != self._event_id:
            self._message.setText("Aucune soirée active : le message vidéo ne peut pas être classé.")
            self._show_actions(self._skip)
            return
        try:
            folder = event_folder(self.config, self._event_id)
            folder.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            log.exception("Préparation du dossier du livre d'or impossible")
            self._message.setText(f"Le livre d'or n'est pas disponible : {exc}")
            self._show_actions(self._skip)
            return
        camera = self.nav.camera
        camera.preview_ready.connect(self._on_preview)
        camera.failed.connect(self._on_camera_failed)
        camera.set_preview_processor(None)
        camera.set_preview_enabled(True)
        if not camera.is_active():
            camera.start_camera()
        self._message.setText("Place-toi devant la caméra, puis touche « Enregistrer mon message ».")
        self._preview.show()
        self._show_actions(self._record, self._skip)

    def _on_preview(self, image: QImage) -> None:
        try:
            if self.nav.current_name != "guestbook":
                return
            self._preview.setPixmap(QPixmap.fromImage(image).scaled(
                self._preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        finally:
            self.nav.camera.preview_consumed()

    def _on_camera_failed(self, message: str) -> None:
        if self.nav.current_name != "guestbook":
            return
        log.error("Caméra indisponible pour le livre d'or : %s", message)
        self._message.setText(message)
        self._show_actions(self._skip)

    def _begin_recording(self) -> None:
        folder = event_folder(self.config, self._event_id)
        filename = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:8]}.mp4"
        destination = folder / filename
        self._recorder = VideoGuestbookRecorder(self._grab_recording_frame, destination, self)
        self._recorder.remaining.connect(self._set_remaining)
        self._recorder.completed.connect(self._recording_completed)
        self._recorder.failed.connect(self._recording_failed)
        self._recording_started_at = time.monotonic()
        self._message.setText("Enregistrement en cours. Touche le bouton pour arrêter, ou attends la fin des 15 secondes.")
        self._show_actions(self._stop)
        self._timer.start()
        self._recorder.start()

    def _stop_recording(self) -> None:
        if self._recorder is not None:
            self._recorder.stop_recording()
            self._stop.setEnabled(False)
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
        log.info("Message du livre d'or enregistré : %s", path)
        self._preview.hide()
        self._timer_label.clear()
        self._message.setText("Merci ! Ton message vidéo est enregistré pour cette soirée.")
        self._show_actions(self._done)

    def _recording_failed(self, message: str) -> None:
        self._timer.stop()
        log.error("Échec du livre d'or vidéo : %s", message)
        self._message.setText(f"Le message n'a pas pu être enregistré. {message}")
        self._timer_label.clear()
        self._show_actions(self._skip)

    def _show_actions(self, *buttons) -> None:
        all_buttons = (self._skip, self._start, self._record, self._stop, self._done)
        for button in all_buttons:
            button.hide()
        while self._actions.count():
            self._actions.takeAt(0)
        self._actions.addStretch(1)
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
