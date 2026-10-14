"""Accès administrateur : protégé par un code, caché derrière un geste (voir main_window.py)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QApplication, QDialog, QInputDialog, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from .widgets.big_button import BigButton

if TYPE_CHECKING:
    from .main_window import MainWindow

log = logging.getLogger(__name__)


def open_admin_dialog(window: "MainWindow") -> None:
    code, ok = QInputDialog.getText(
        window, "Accès administrateur", "Code :", QLineEdit.EchoMode.Password)
    if not ok:
        return
    if code != window.config.code_admin:
        log.warning("Code administrateur incorrect")
        QMessageBox.warning(window, "Accès refusé", "Code incorrect.")
        return
    log.info("Accès administrateur ouvert")
    AdminDialog(window).exec()


class AdminDialog(QDialog):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window
        self.setWindowTitle("Administration")
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        self._info = QLabel()
        layout.addWidget(self._info)
        self._mail_info = QLabel()
        self._mail_info.setWordWrap(True)
        layout.addWidget(self._mail_info)
        self._slideshow_info = QLabel()
        self._slideshow_info.setWordWrap(True)
        layout.addWidget(self._slideshow_info)
        clear_btn = BigButton("Vider le diaporama", "secondary")
        clear_btn.clicked.connect(lambda: self._clear_slideshow())
        layout.addWidget(clear_btn)
        retry_btn = BigButton("Renvoyer les envois en échec", "secondary")
        retry_btn.clicked.connect(lambda: self._requeue())
        layout.addWidget(retry_btn)

        reload_btn = BigButton("Recharger la configuration", "secondary")
        reload_btn.clicked.connect(lambda: self._reload())
        layout.addWidget(reload_btn)

        quit_btn = BigButton("Quitter l'application", "danger")
        quit_btn.clicked.connect(lambda: QApplication.quit())
        layout.addWidget(quit_btn)

        close_btn = BigButton("Fermer")
        close_btn.clicked.connect(lambda: self.accept())
        layout.addWidget(close_btn)

        self._refresh_info()

    def _refresh_info(self) -> None:
        cfg = self._window.config
        self._info.setText(
            f"Détourage : {cfg.mode_detourage}\n"
            f"Poses photomaton : {cfg.nb_poses}\n"
            f"Configuration : {cfg.config_path}"
        )
        self._mail_info.setText(self._mail_text())
        self._slideshow_info.setText(self._slideshow_text())

    def _slideshow_text(self) -> str:
        status = self._window.slideshow.status()
        return f"Diaporama : {status.photos} photo(s), {status.detail}"

    def _clear_slideshow(self) -> None:
        self._window.slideshow.clear()
        log.info("Diaporama vidé")
        self._refresh_info()

    def _mail_text(self) -> str:
        stats = self._window.mail.stats()
        if not stats.configured:
            return "Envoi par mail : NON CONFIGURÉ (renseigne la section [mail] de config.ini)"
        connection = {None: "aucun essai", True: "connexion OK", False: "PAS DE CONNEXION"}[stats.online]
        text = (f"Envoi par mail : {stats.pending} en attente, {stats.sent} envoyés, "
                f"{stats.failed} en échec ({connection})")
        return text + ("\n" + "\n".join(stats.errors) if stats.errors else "")

    def _reload(self) -> None:
        self._window.config.reload()
        self._window.mail.reload_settings()
        self._window.slideshow.reload()
        self._refresh_info()
        log.info("Configuration rechargée")

    def _requeue(self) -> None:
        count = self._window.mail.requeue_failed()
        log.info("%d envoi(s) en échec remis en attente", count)
        self._refresh_info()
