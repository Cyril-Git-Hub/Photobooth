"""Accès administrateur : protégé par un code, caché derrière un geste (voir main_window.py)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QSlider, QVBoxLayout,
)

from .files import open_folder
from .widgets.big_button import BigButton
from .scale import px

if TYPE_CHECKING:
    from .main_window import MainWindow

log = logging.getLogger(__name__)

BUTTON_HEIGHT = 64    # plus bas que les boutons des invités : la boîte doit tenir sur un petit écran


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
        self.setMinimumWidth(px(760))

        layout = QVBoxLayout(self)
        layout.setSpacing(px(10))
        self._info = QLabel()
        self._mail_info = QLabel()
        self._backup_info = QLabel()
        self._slideshow_info = QLabel()
        for label in (self._info, self._mail_info, self._backup_info, self._slideshow_info):
            label.setWordWrap(True)
            layout.addWidget(label)

        sound_row = QHBoxLayout()
        self._sound_active = QCheckBox("Effets sonores activés")
        self._sound_active.setChecked(window.config.son_active)
        self._sound_active.toggled.connect(self._on_sound_active_changed)
        sound_row.addWidget(self._sound_active)
        sound_row.addWidget(QLabel("Volume"))
        self._sound_volume = QSlider(Qt.Orientation.Horizontal)
        self._sound_volume.setRange(0, 100)
        self._sound_volume.setValue(window.config.son_volume)
        self._sound_volume.valueChanged.connect(self._on_sound_volume_changed)
        self._sound_volume.sliderReleased.connect(self._persist_sound_settings)
        sound_row.addWidget(self._sound_volume, 1)
        self._sound_volume_label = QLabel(f"{window.config.son_volume} %")
        sound_row.addWidget(self._sound_volume_label)
        layout.addLayout(sound_row)
        self._sound_save_timer = QTimer(self)
        self._sound_save_timer.setSingleShot(True)
        self._sound_save_timer.setInterval(500)
        self._sound_save_timer.timeout.connect(self._persist_sound_settings)
        self.finished.connect(lambda _result: self._persist_sound_settings())

        grid = QGridLayout()
        grid.setSpacing(px(12))
        for index, (text, variant, action) in enumerate([
            ("Réessayer maintenant (mails et sauvegarde)", "secondary", self._retry_now),
            ("Exporter les envois non partis", "secondary", self._export),
            ("Vider le diaporama", "secondary", self._clear_slideshow),
            ("Recharger la configuration", "secondary", self._reload),
            ("Quitter l'application", "danger", lambda: QApplication.quit()),
            ("Fermer", "primary", lambda: self.accept()),
        ]):
            button = BigButton(text, variant)
            button.setMinimumSize(px(260), px(BUTTON_HEIGHT))
            button.clicked.connect(lambda _checked=False, f=action: f())
            grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(grid)

        self._refresh_info()

    def _refresh_info(self) -> None:
        cfg = self._window.config
        self._info.setText(
            f"Détourage : {cfg.mode_detourage} | Poses photomaton : {cfg.nb_poses}\n"
            f"Configuration : {cfg.config_path}"
        )
        self._mail_info.setText(self._mail_text())
        self._backup_info.setText(self._backup_text())
        self._slideshow_info.setText(self._slideshow_text())

    def _on_sound_active_changed(self, active: bool) -> None:
        self._window.sounds.update_settings(active, self._sound_volume.value())
        self._sound_save_timer.stop()
        self._persist_sound_settings()

    def _on_sound_volume_changed(self, volume: int) -> None:
        self._sound_volume_label.setText(f"{volume} %")
        self._window.sounds.update_settings(self._sound_active.isChecked(), volume)
        self._sound_save_timer.start()

    def _persist_sound_settings(self) -> None:
        try:
            self._window.config.save_sound_settings(
                self._sound_active.isChecked(), self._sound_volume.value())
        except OSError as exc:
            log.exception("Enregistrement des réglages sonores impossible")
            QMessageBox.warning(self, "Réglages sonores", f"Réglages appliqués pour cette session, mais non enregistrés :\n{exc}")

    # ---------- états ----------

    def _mail_text(self) -> str:
        stats = self._window.mail.stats()
        if not stats.configured:
            return "Envoi par mail : NON CONFIGURÉ (renseigne la section [mail] de config.ini)"
        connection = {None: "aucun essai", True: "connexion OK", False: "PAS DE CONNEXION"}[stats.online]
        text = (f"Envoi par mail : {stats.pending} en attente, {stats.sent} envoyés, "
                f"{stats.failed} en échec ({connection})")
        return text + ("\n" + "\n".join(stats.errors) if stats.errors else "")

    def _backup_text(self) -> str:
        stats = self._window.backup.stats()
        if not stats.enabled:
            return "Sauvegarde des photos : désactivée (section [sauvegarde] de config.ini)"
        text = f"Sauvegarde des photos : {stats.copied} copiée(s), {stats.pending} en attente, vers {stats.destination}"
        return text + (f"\nPANNE : {stats.last_error}" if stats.pending and stats.last_error else "")

    def _slideshow_text(self) -> str:
        status = self._window.slideshow.status()
        return f"Diaporama : {status.photos} photo(s), {status.detail}"

    # ---------- actions ----------

    def _retry_now(self) -> None:
        count = self._window.mail.retry_now()
        self._window.backup.retry_now()
        log.info("Nouvel essai immédiat demandé (%d envoi(s) en échec remis en attente)", count)
        self._refresh_info()

    def _export(self) -> None:
        try:
            result = self._window.mail.export_unsent()
        except OSError as exc:
            log.exception("Export des envois impossible")
            QMessageBox.warning(self, "Export impossible", f"L'export a échoué :\n{exc}")
            return
        if result is None:
            QMessageBox.information(self, "Export", "Aucun envoi à exporter : tout est parti.")
            return
        extra = f"\n{result.missing} photo(s) introuvable(s) (signalées dans le tableau)." if result.missing else ""
        QMessageBox.information(self, "Export terminé",
                                f"{result.exported} photo(s) exportée(s) dans :\n{result.folder}{extra}")
        open_folder(result.folder)

    def _clear_slideshow(self) -> None:
        self._window.slideshow.clear()
        log.info("Diaporama vidé")
        self._refresh_info()

    def _reload(self) -> None:
        self._sound_save_timer.stop()
        self._window.config.reload()
        self._window.reload_theme()
        self._window.mail.reload_settings()
        self._window.slideshow.reload()
        self._sound_active.blockSignals(True)
        self._sound_active.setChecked(self._window.config.son_active)
        self._sound_active.blockSignals(False)
        self._sound_volume.blockSignals(True)
        self._sound_volume.setValue(self._window.config.son_volume)
        self._sound_volume.blockSignals(False)
        self._sound_volume_label.setText(f"{self._window.config.son_volume} %")
        self._refresh_info()
        log.info("Configuration rechargée")
