"""Accès administrateur : protégé par un code, caché derrière un geste (voir main_window.py)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from ..core.contact_sheets import create_contact_sheets
from ..core.video_guestbook import delete_recordings, event_folder, list_recordings
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

        activation_button = BigButton("Gérer les activations", "secondary")
        activation_button.clicked.connect(self._manage_activations)
        layout.addWidget(activation_button)

        event_label = QLabel("Soirée et planches-contact")
        event_label.setStyleSheet("font-weight: bold")
        layout.addWidget(event_label)
        event_row = QHBoxLayout()
        self._event_combo = QComboBox()
        self._event_combo.setMinimumHeight(px(48))
        event_row.addWidget(self._event_combo, 1)
        start_event = BigButton("Démarrer une nouvelle soirée", "secondary")
        start_event.setMinimumSize(px(280), px(BUTTON_HEIGHT))
        start_event.clicked.connect(self._start_event)
        event_row.addWidget(start_event)
        create_sheets = BigButton("Créer les planches-contact", "primary")
        create_sheets.setMinimumSize(px(280), px(BUTTON_HEIGHT))
        create_sheets.clicked.connect(self._generate_contact_sheets)
        event_row.addWidget(create_sheets)
        layout.addLayout(event_row)
        self._event_status = QLabel()
        self._event_status.setWordWrap(True)
        layout.addWidget(self._event_status)
        guestbook_row = QHBoxLayout()
        open_guestbook = BigButton("Ouvrir les vidéos du livre d'or", "secondary")
        open_guestbook.clicked.connect(self._open_guestbook)
        guestbook_row.addWidget(open_guestbook)
        delete_guestbook = BigButton("Supprimer les vidéos de la soirée", "danger")
        delete_guestbook.clicked.connect(self._delete_guestbook)
        guestbook_row.addWidget(delete_guestbook)
        layout.addLayout(guestbook_row)

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
        self._refresh_events()

    def _refresh_events(self) -> None:
        events = self._window.events.list_events()
        active = self._window.events.active_event()
        self._event_combo.blockSignals(True)
        self._event_combo.clear()
        for event in events:
            guests = self._window.events.guests(event.id)
            photo_count = sum(guest.count for guest in guests)
            video_count = len(list_recordings(self._window.config, event.id))
            state = " · en cours" if event.active else ""
            label = f"{event.name}{state} — {len(guests)} invité(s), {photo_count} média(s), {video_count} vidéo(s)"
            self._event_combo.addItem(label, event.id)
        if active is not None:
            index = self._event_combo.findData(active.id)
            if index >= 0:
                self._event_combo.setCurrentIndex(index)
        self._event_combo.blockSignals(False)
        if active:
            self._event_status.setText(
                f"Soirée active : {active.name}. Les prochaines photos validées avec une adresse mail y seront associées."
            )
        else:
            self._event_status.setText(
                "Aucune soirée active. Démarre-en une avant la séance pour inclure les prochaines photos aux planches-contact."
            )

    def _start_event(self) -> None:
        active = self._window.events.active_event()
        if active is not None:
            answer = QMessageBox.question(
                self, "Démarrer une nouvelle soirée",
                f"La soirée « {active.name} » sera clôturée. Ses photos resteront disponibles. Continuer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            event = self._window.events.start_event()
        except Exception as exc:
            log.exception("Démarrage de soirée impossible")
            QMessageBox.warning(self, "Soirée", f"Impossible de démarrer une soirée :\n{exc}")
            return
        log.info("Soirée démarrée depuis l'administration : %s", event.id)
        self._refresh_events()

    def _generate_contact_sheets(self) -> None:
        event_id = self._event_combo.currentData()
        if not event_id:
            QMessageBox.information(self, "Planches-contact", "Aucune soirée n'est disponible.")
            return
        event = next((item for item in self._window.events.list_events() if item.id == event_id), None)
        if event is None:
            self._refresh_events()
            QMessageBox.warning(self, "Planches-contact", "Cette soirée n'est plus disponible.")
            return
        try:
            paths, missing = create_contact_sheets(
                self._window.events, event, self._window.config.dossier_exports)
        except Exception as exc:
            log.exception("Génération des planches-contact impossible")
            QMessageBox.warning(self, "Planches-contact", f"La génération a échoué :\n{exc}")
            return
        self._refresh_events()
        if not paths:
            QMessageBox.information(
                self, "Planches-contact",
                "Aucune planche créée. Vérifie que cette soirée contient des photos encore disponibles associées à une adresse mail."
                + (f"\n{missing} photo(s) introuvable(s) ou illisible(s)." if missing else ""),
            )
            return
        extra = f"\n{missing} photo(s) introuvable(s) ou illisible(s)." if missing else ""
        QMessageBox.information(
            self, "Planches-contact créées",
            f"{len(paths)} planche(s) créée(s) dans :\n{paths[0].parent}{extra}",
        )
        open_folder(paths[0].parent)

    def _open_guestbook(self) -> None:
        event_id = self._event_combo.currentData()
        if not event_id:
            QMessageBox.information(self, "Livre d'or", "Sélectionne une soirée.")
            return
        recordings = list_recordings(self._window.config, event_id)
        if not recordings:
            QMessageBox.information(self, "Livre d'or", "Aucune vidéo enregistrée pour cette soirée.")
            return
        open_folder(event_folder(self._window.config, event_id))

    def _delete_guestbook(self) -> None:
        event_id = self._event_combo.currentData()
        if not event_id:
            QMessageBox.information(self, "Livre d'or", "Sélectionne une soirée.")
            return
        recordings = list_recordings(self._window.config, event_id)
        if not recordings:
            QMessageBox.information(self, "Livre d'or", "Aucune vidéo enregistrée pour cette soirée.")
            return
        answer = QMessageBox.question(
            self, "Supprimer le livre d'or",
            f"Supprimer définitivement les {len(recordings)} vidéo(s) de cette soirée ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_recordings(self._window.config, event_id)
        except OSError as exc:
            log.exception("Suppression des vidéos du livre d'or impossible")
            QMessageBox.warning(self, "Livre d'or", f"Suppression impossible :\n{exc}")
            return
        self._refresh_events()
        QMessageBox.information(self, "Livre d'or", "Les vidéos de cette soirée ont été supprimées.")

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

    def _manage_activations(self) -> None:
        dialog = ActivationDialog(self._window, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not self._window.apply_activation_settings():
            QMessageBox.warning(
                self, "Partage QR indisponible",
                "L'option a été enregistrée, mais Google Drive n'est pas prêt. Vérifie sa configuration dans le guide.",
            )
        self._sound_active.blockSignals(True)
        self._sound_active.setChecked(self._window.config.son_active)
        self._sound_active.blockSignals(False)
        self._refresh_info()

    def _reload(self) -> None:
        self._sound_save_timer.stop()
        self._window.config.reload()
        self._window.reload_theme()
        self._window.mail.reload_settings()
        self._window.slideshow.reload()
        self._window.ensure_drive_service()
        self._sound_active.blockSignals(True)
        self._sound_active.setChecked(self._window.config.son_active)
        self._sound_active.blockSignals(False)
        self._sound_volume.blockSignals(True)
        self._sound_volume.setValue(self._window.config.son_volume)
        self._sound_volume.blockSignals(False)
        self._sound_volume_label.setText(f"{self._window.config.son_volume} %")
        self._refresh_info()
        log.info("Configuration rechargée")

    # ---------- états ----------

    def _mail_text(self) -> str:
        stats = self._window.mail.stats()
        if not self._window.config.mail_actif:
            return f"Envoi par mail : désactivé ({stats.pending} message(s) en attente, suspendu(s))"
        if not stats.configured:
            return "Envoi par mail : NON CONFIGURÉ (renseigne la section [mail] de config.ini)"
        connection = {None: "aucun essai", True: "connexion OK", False: "PAS DE CONNEXION"}[stats.online]
        text = (f"Envoi par mail : {stats.pending} en attente, {stats.sent} envoyés, "
                f"{stats.failed} en échec ({connection})")
        return text + ("\n" + "\n".join(stats.errors) if stats.errors else "")

    def _backup_text(self) -> str:
        stats = self._window.backup.stats()
        if not stats.enabled:
            return "Sauvegarde des photos : désactivée (activation et dossier dans [sauvegarde] de config.ini)"
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



class ActivationDialog(QDialog):
    """Interrupteurs persistants des fonctions facultatives du photobooth."""

    def __init__(self, window: "MainWindow", parent: QDialog) -> None:
        super().__init__(parent)
        self._window = window
        cfg = window.config
        self.setWindowTitle("Gérer les activations")
        self.setMinimumWidth(px(560))
        self.setMinimumHeight(px(460))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Active ou désactive les fonctions proposées aux invités."))

        content = QWidget()
        options = QVBoxLayout(content)
        options.setSpacing(px(10))
        self._mail = self._option(options, "Envoi des photos par mail", cfg.mail_actif)
        options.addWidget(QLabel("Les messages déjà en attente seront suspendus puis reprendront si tu réactives l'envoi."))
        self._backup = self._option(options, "Copie automatique de sauvegarde", window.backup.stats().enabled)
        self._backup.setEnabled(cfg.dossier_sauvegarde is not None)
        if cfg.dossier_sauvegarde is None:
            options.addWidget(QLabel("Configure d'abord un dossier dans la section [sauvegarde] de config.ini."))
        self._gif = self._option(options, "Format GIF animé", cfg.gif_actif)
        self._challenges = self._option(options, "Casting/Audition", cfg.defis_actifs)
        self._qr = self._option(options, "Partage par QR code", cfg.qr_drive_actif)
        self._guestbook = self._option(options, "Livre d'or vidéo", cfg.livre_or_actif)
        self._second_screen = self._option(options, "Diaporama sur le second écran", cfg.second_ecran_active)
        self._sounds = self._option(options, "Effets sonores", cfg.son_active)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        note = QLabel("Les changements sont enregistrés dans config.ini et appliqués immédiatement.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _option(layout: QVBoxLayout, text: str, checked: bool) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.setMinimumHeight(px(42))
        checkbox.setChecked(checked)
        layout.addWidget(checkbox)
        return checkbox

    def _save(self) -> None:
        cfg = self._window.config
        updates = {
            ("mail", "actif"): self._mail.isChecked(),
            ("sauvegarde", "actif"): self._backup.isChecked(),
            ("gif", "actif"): self._gif.isChecked(),
            ("defis", "actif"): self._challenges.isChecked(),
            ("qr_drive", "actif"): self._qr.isChecked(),
            ("livre_or", "actif"): self._guestbook.isChecked(),
            ("general", "second_ecran_active"): self._second_screen.isChecked(),
            ("general", "son_active"): self._sounds.isChecked(),
        }
        if cfg.dossier_sauvegarde is None:
            updates.pop(("sauvegarde", "actif"))
        try:
            cfg.save_activation_settings(updates)
        except OSError as exc:
            log.exception("Enregistrement des activations impossible")
            QMessageBox.warning(self, "Enregistrement impossible", f"Les réglages n'ont pas été enregistrés :\n{exc}")
            return
        self.accept()
