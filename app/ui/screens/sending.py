"""Écran de fin : la photo est mise en file d'envoi (rapide, sans attendre le réseau), puis retour à l'accueil."""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QVBoxLayout

from ...core.emails import mask_email
from .base import BaseScreen
from ..scale import px

log = logging.getLogger(__name__)

DISPLAY_MS = 4000
MSG_SAVED = "Ta photo est enregistrée !"
MSG_OFFLINE = "Pas de connexion pour l'instant : ta photo partira dès que le réseau sera revenu."


class SendingScreen(BaseScreen):
    allow_inactivity_reset = False

    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._title = QLabel("Merci !")
        self._title.setObjectName("title")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note = QLabel("")
        self._note.setObjectName("note")
        self._note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(60), px(60), px(60), px(60))
        layout.setSpacing(px(24))
        layout.addStretch(1)
        layout.addWidget(self._title)
        layout.addWidget(self._note)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.nav.go_next())   # fin du parcours -> accueil

    def on_enter(self) -> None:
        self._note.setText(self._queue_photo())
        self._timer.start(DISPLAY_MS)

    def on_leave(self) -> None:
        self._timer.stop()

    def _queue_photo(self) -> str:
        """Met la photo en file d'envoi ; renvoie le message pour l'invité."""
        session = self.session
        if not session.photos:
            return MSG_SAVED
        try:
            self.nav.slideshow.add_photo(session.photos[-1])        # le diaporama n'a rien à voir avec les mails
        except Exception:
            log.exception("Ajout au diaporama impossible")
        try:
            self.nav.backup.add([session.photos[-1], *session.poses])   # seconde copie, indépendante des mails
        except Exception:
            log.exception("Ajout à la sauvegarde impossible")
        try:
            result = self.nav.mail.enqueue_photo(session.photos[-1], session.guest_first_name,
                                                 session.guest_last_name, session.email)
            stats = self.nav.mail.stats()
        except Exception:
            log.exception("Mise en file d'envoi impossible : la photo reste enregistrée")
            return MSG_SAVED
        if result.guest and result.configured:
            if stats.online is False:
                return MSG_OFFLINE
            return f"Ta photo est en route vers {mask_email(session.email)} !"
        return MSG_SAVED
