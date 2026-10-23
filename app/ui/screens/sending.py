"""Affiche le résultat validé, le QR de téléchargement et met le média en file d'envoi."""
from __future__ import annotations

import logging
from concurrent.futures import Future
from io import BytesIO
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QImage, QMovie, QPixmap
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ...core.drive_sharing import SharedMedia
from ...core.emails import mask_email
from .base import BaseScreen
from ..scale import px
from ..widgets.big_button import BigButton

log = logging.getLogger(__name__)

PHOTO_DISPLAY_MS = 45_000
QR_DISPLAY_MS = 60_000
LEGACY_DISPLAY_MS = 4_000


class SendingScreen(BaseScreen):
    allow_inactivity_reset = False

    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._title = QLabel("Merci !")
        self._title.setObjectName("heading")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._photo_page = QWidget()
        photo_layout = QVBoxLayout(self._photo_page)
        photo_layout.setContentsMargins(0, 0, 0, 0)
        photo_layout.setSpacing(px(8))
        self._preview = QLabel()
        self._preview.setObjectName("resultPhotoPreview")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(px(640), px(300))
        photo_layout.addWidget(self._preview, 1)
        self._note = QLabel("")
        self._note.setObjectName("note")
        self._note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note.setWordWrap(True)
        photo_layout.addWidget(self._note)
        photo_actions = QHBoxLayout()
        photo_actions.setSpacing(px(20))
        self._show_qr = BigButton("Afficher le QR code")
        self._show_qr.setEnabled(False)
        self._show_qr.clicked.connect(self._show_qr_page)
        done = BigButton("Terminer", "secondary")
        done.clicked.connect(self._finish)
        photo_actions.addStretch(1)
        photo_actions.addWidget(self._show_qr)
        photo_actions.addWidget(done)
        photo_actions.addStretch(1)
        photo_layout.addLayout(photo_actions)

        self._qr_page = QWidget()
        qr_layout = QVBoxLayout(self._qr_page)
        qr_layout.setContentsMargins(0, 0, 0, 0)
        qr_layout.setSpacing(px(10))
        qr_title = QLabel("Scanne pour télécharger ton résultat")
        qr_title.setObjectName("heading")
        qr_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_layout.addWidget(qr_title)
        self._qr_image = QLabel()
        self._qr_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_layout.addWidget(self._qr_image, 1)
        self._qr_url = QLabel("")
        self._qr_url.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_url.setWordWrap(True)
        qr_layout.addWidget(self._qr_url)
        qr_actions = QHBoxLayout()
        qr_actions.setSpacing(px(20))
        back = BigButton("Retour à la photo", "secondary")
        back.clicked.connect(self._return_to_photo)
        finish_qr = BigButton("Terminer", "secondary")
        finish_qr.clicked.connect(self._finish)
        qr_actions.addStretch(1)
        qr_actions.addWidget(back)
        qr_actions.addWidget(finish_qr)
        qr_actions.addStretch(1)
        qr_layout.addLayout(qr_actions)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._photo_page)
        self._pages.addWidget(self._qr_page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(28), px(16), px(28), px(16))
        layout.setSpacing(px(8))
        layout.addWidget(self._title)
        layout.addWidget(self._pages, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._finish)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(250)
        self._poll_timer.timeout.connect(self._poll_upload)
        self._movie: QMovie | None = None
        self._photo_pixmap: QPixmap | None = None
        self._qr_pixmap: QPixmap | None = None
        self._share_future: Future | None = None
        self._share_path: Path | None = None
        self._shared_media: SharedMedia | None = None

    def on_enter(self) -> None:
        self._stop_movie()
        self._pages.setCurrentWidget(self._photo_page)
        path = self.session.photos[-1] if self.session.photos else None
        self._set_result_preview(path)
        self._note.setText(self._queue_photo())
        self._start_share(path)
        self._timer.start(PHOTO_DISPLAY_MS if self.config.qr_drive_actif else LEGACY_DISPLAY_MS)

    def on_leave(self) -> None:
        self._timer.stop()
        self._poll_timer.stop()
        self._stop_movie()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._photo_pixmap is not None:
            self._show_photo_pixmap()
        if self._movie is not None:
            self._movie.setScaledSize(self._preview.size())
        if self._qr_pixmap is not None:
            self._show_qr_pixmap()

    def _set_result_preview(self, path: Path | None) -> None:
        self._preview.clear()
        self._photo_pixmap = None
        if path is None:
            return
        if path.suffix.casefold() == ".gif":
            movie = QMovie(str(path))
            if movie.isValid():
                self._movie = movie
                movie.setScaledSize(QSize(px(900), px(506)))
                self._preview.setMovie(movie)
                movie.start()
                return
            log.warning("Aperçu GIF impossible pour %s", path)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            log.warning("Aperçu du résultat impossible pour %s", path)
            return
        self._photo_pixmap = pixmap
        self._show_photo_pixmap()

    def _show_photo_pixmap(self) -> None:
        if self._photo_pixmap is None:
            return
        self._preview.setPixmap(self._photo_pixmap.scaled(
            self._preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def _start_share(self, path: Path | None) -> None:
        if not self.config.qr_drive_actif:
            self._show_qr.setVisible(False)
            return
        if path is None:
            self._show_qr.setVisible(False)
            return
        self._show_qr.setVisible(True)
        self._show_qr.setEnabled(False)
        if self._shared_media is not None and self._share_path == path:
            self._prepare_qr(self._shared_media)
            return
        if self.nav.drive_share is None or not self.nav.drive_share.is_configured():
            self._note.setText(self._note.text() + " Le QR code n'est pas configuré sur cette borne.")
            return
        self._share_path = path
        self._note.setText(self._note.text() + " Préparation du QR code…")
        self._share_future = self.nav.drive_executor.submit(self.nav.drive_share.upload_and_share, path)
        self._poll_timer.start()

    def _poll_upload(self) -> None:
        if self._share_future is None or not self._share_future.done():
            return
        self._poll_timer.stop()
        try:
            self._shared_media = self._share_future.result()
            if self._prepare_qr(self._shared_media):
                self._note.setText(self._queue_status + " Le QR code est prêt.")
        except Exception:
            log.exception("Création du lien QR impossible ; la photo reste enregistrée localement")
            self._note.setText(self._queue_status + " QR indisponible ; la photo reste enregistrée et envoyée par mail.")

    def _prepare_qr(self, media: SharedMedia) -> bool:
        try:
            import qrcode

            image = qrcode.make(media.url)
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            qimage = QImage.fromData(buffer.getvalue(), "PNG")
            self._qr_pixmap = QPixmap.fromImage(qimage)
            expiry = media.expires_at.astimezone().strftime("%d/%m/%Y à %H:%M")
            self._qr_url.setText(f"Lien accessible jusqu’au {expiry}\n{media.url}")
            self._show_qr_pixmap()
            self._show_qr.setEnabled(True)
            return True
        except Exception:
            log.exception("Génération de l'image QR impossible")
            self._note.setText(self._queue_status + " QR indisponible ; la photo reste enregistrée et envoyée par mail.")
            return False

    def _show_qr_pixmap(self) -> None:
        if self._qr_pixmap is not None:
            size = min(self._qr_image.width(), self._qr_image.height(), px(520))
            self._qr_image.setPixmap(self._qr_pixmap.scaled(
                size, size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def _show_qr_page(self) -> None:
        if self._shared_media is None or not self._show_qr.isEnabled():
            return
        self._pages.setCurrentWidget(self._qr_page)
        QTimer.singleShot(0, self._show_qr_pixmap)
        self._timer.start(QR_DISPLAY_MS)

    def _return_to_photo(self) -> None:
        self._pages.setCurrentWidget(self._photo_page)
        self._timer.start(PHOTO_DISPLAY_MS)

    def _finish(self) -> None:
        self.nav.go_home()

    def _queue_photo(self) -> str:
        """Met la photo validée en file d'envoi et de suivi ; renvoie le message invité."""
        session = self.session
        if not session.photos:
            self._queue_status = "Ta photo est enregistrée !"
            return self._queue_status
        try:
            display_first_name = session.guest_pseudo or session.guest_first_name
            display_last_name = "" if session.guest_pseudo else session.guest_last_name
            self.nav.slideshow.add_photo(session.photos[-1])
        except Exception:
            log.exception("Ajout au diaporama impossible")
        try:
            self.nav.backup.add([session.photos[-1], *session.poses])
        except Exception:
            log.exception("Ajout à la sauvegarde impossible")
        if session.event_id and session.email:
            try:
                media_type = ("gif" if session.photos[-1].suffix.casefold() == ".gif" else
                              "strip" if session.photo_format == "strip" else
                              "framed" if session.frame_mode else "single")
                self.nav.events.record_photo(
                    session.event_id, session.email, display_first_name,
                    display_last_name, session.photos[-1], media_type)
            except Exception:
                log.exception("Indexation de la photo pour la planche-contact impossible")
        try:
            result = self.nav.mail.enqueue_photo(session.photos[-1], display_first_name,
                                                 display_last_name, session.email)
            stats = self.nav.mail.stats()
        except Exception:
            log.exception("Mise en file d'envoi impossible : la photo reste enregistrée")
            self._queue_status = "Ta photo est enregistrée !"
            return self._queue_status
        if result.guest and result.configured:
            self._queue_status = ("Pas de connexion pour l'instant : ta photo partira dès que le réseau sera revenu."
                                  if stats.online is False else
                                  f"Ta photo est en route vers {mask_email(session.email)} !")
        else:
            self._queue_status = "Ta photo est enregistrée !"
        return self._queue_status

    def _stop_movie(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie = None
