"""Accès administrateur : schéma ou code tactile, derrière un geste (voir main_window.py)."""
from __future__ import annotations

import hmac
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QScrollArea, QSlider, QTableWidget,
    QScroller, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.contact_sheets import create_contact_sheets
from ..core.emails import is_valid_email, normalize_email
from ..core.guests import Guest, GuestListError, load_guests, update_guest_emails
from ..core.keyboards import EMAIL_ROWS
from ..core.text_buffer import TextBuffer
from ..core.video_guestbook import delete_recordings, event_folder, list_recordings
from .files import open_folder
from .green_screen_dialog import GreenScreenCalibrationDialog
from .admin_auth import PatternDialog, PinDialog
from .widgets.big_button import BigButton
from .widgets.virtual_keyboard import VirtualKeyboard
from .scale import px

if TYPE_CHECKING:
    from .main_window import MainWindow

log = logging.getLogger(__name__)

BUTTON_HEIGHT = 64    # plus bas que les boutons des invités : la boîte doit tenir sur un petit écran


def open_admin_dialog(window: "MainWindow") -> None:
    mode = window.config.admin_auth_mode
    while True:
        if mode == "code":
            dialog = PinDialog(window)
            expected = window.config.code_admin
        else:
            dialog = PatternDialog(window)
            expected = window.config.admin_pattern
        result = dialog.exec()
        if dialog.switch_to:
            mode = dialog.switch_to
            continue
        if result != QDialog.DialogCode.Accepted:
            return
        if not hmac.compare_digest(dialog.value or "", expected):
            log.warning("Code administrateur incorrect")
            QMessageBox.warning(window, "Accès refusé", "Code ou schéma incorrect.")
            return
        break
    log.info("Accès administrateur ouvert")
    AdminDialog(window).exec()


class AdminDialog(QDialog):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window
        self.setWindowTitle("Administration")
        screen = window.screen()
        available = screen.availableGeometry() if screen else None
        available_width = available.width() if available else px(1280)
        available_height = available.height() if available else px(800)
        self.setMinimumSize(min(px(760), max(320, available_width - px(32))),
                            min(px(400), max(280, available_height - px(32))))
        self.resize(min(px(1100), int(available_width * 0.94)),
                    min(px(900), int(available_height * 0.92)))

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(px(8), px(8), px(8), px(8))
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        content = QWidget()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        layout = QVBoxLayout(content)
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
        self._sound_volume.setMinimumHeight(px(56))
        self._sound_volume.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: {px(8)}px; }} "
            f"QSlider::handle:horizontal {{ width: {px(32)}px; margin: -{px(12)}px 0; }}"
        )
        self._sound_volume.setValue(window.config.son_volume)
        self._sound_volume.valueChanged.connect(self._on_sound_volume_changed)
        self._sound_volume.sliderReleased.connect(self._persist_sound_settings)
        sound_row.addWidget(self._sound_volume, 1)
        self._sound_volume_label = QLabel(f"{window.config.son_volume} %")
        sound_row.addWidget(self._sound_volume_label)
        layout.addLayout(sound_row)
        countdown_row = QHBoxLayout()
        countdown_row.addWidget(QLabel("Décompte avant la prise de vue"))
        self._countdown = QComboBox()
        self._countdown.setMinimumHeight(px(56))
        self._countdown.view().setStyleSheet(
            f"QListView::item {{ min-height: {px(44)}px; padding: {px(4)}px; }}"
        )
        for seconds in range(1, 11):
            self._countdown.addItem(f"{seconds} seconde" + ("s" if seconds != 1 else ""), seconds)
        self._countdown.setCurrentIndex(self._countdown.findData(window.config.duree_decompte))
        self._countdown.currentIndexChanged.connect(self._on_countdown_changed)
        countdown_row.addWidget(self._countdown, 1)
        layout.addLayout(countdown_row)
        auth_row = QHBoxLayout()
        auth_row.addWidget(QLabel("Déverrouillage administrateur"))
        self._admin_auth_mode = QComboBox()
        self._admin_auth_mode.setMinimumHeight(px(56))
        self._admin_auth_mode.addItem("Schéma tactile", "pattern")
        self._admin_auth_mode.addItem("Code numérique", "code")
        self._admin_auth_mode.setCurrentIndex(
            self._admin_auth_mode.findData(window.config.admin_auth_mode))
        self._admin_auth_mode.view().setStyleSheet(
            f"QListView::item {{ min-height: {px(44)}px; padding: {px(4)}px; }}"
        )
        self._admin_auth_mode.currentIndexChanged.connect(self._on_admin_auth_mode_changed)
        auth_row.addWidget(self._admin_auth_mode, 1)
        self._pattern_button = BigButton("Définir le schéma", "secondary")
        self._pattern_button.setObjectName("adminPatternSetting")
        self._pattern_button.setMinimumSize(px(190), px(56))
        self._pattern_button.clicked.connect(self._define_admin_pattern)
        auth_row.addWidget(self._pattern_button)
        layout.addLayout(auth_row)
        self._sound_save_timer = QTimer(self)
        self._sound_save_timer.setSingleShot(True)
        self._sound_save_timer.setInterval(500)
        self._sound_save_timer.timeout.connect(self._persist_sound_settings)
        self.finished.connect(lambda _result: self._persist_sound_settings())

        detourage_row = QHBoxLayout()
        detourage_row.addWidget(QLabel("Mode de détourage"))
        self._detourage_mode = QComboBox()
        self._detourage_mode.setMinimumHeight(px(48))
        self._detourage_mode.view().setStyleSheet(
            f"QListView::item {{ min-height: {px(44)}px; padding: {px(4)}px; }}"
        )
        self._detourage_mode.addItem("Intelligence artificielle", "ia")
        self._detourage_mode.addItem("Fond vert", "fond_vert")
        self._detourage_mode.setCurrentIndex(self._detourage_mode.findData(window.config.mode_detourage))
        self._detourage_mode.currentIndexChanged.connect(self._on_detourage_mode_changed)
        detourage_row.addWidget(self._detourage_mode, 1)
        layout.addLayout(detourage_row)

        activation_button = BigButton("Gérer les activations", "secondary")
        activation_button.clicked.connect(self._manage_activations)
        layout.addWidget(activation_button)

        guest_email_button = BigButton("Corriger les mails des invités", "secondary")
        guest_email_button.setMinimumSize(px(300), px(BUTTON_HEIGHT))
        guest_email_button.clicked.connect(self._edit_guest_emails)
        layout.addWidget(guest_email_button)

        self._chroma_button = BigButton("Régler le fond vert avec la webcam", "secondary")
        self._chroma_button.setMinimumSize(px(300), px(BUTTON_HEIGHT))
        self._chroma_button.clicked.connect(self._calibrate_green_screen)
        layout.addWidget(self._chroma_button)
        self._update_chroma_controls()

        event_label = QLabel("Soirée et planches-contact")
        event_label.setStyleSheet("font-weight: bold")
        layout.addWidget(event_label)
        event_row = QHBoxLayout()
        self._event_combo = QComboBox()
        self._event_combo.setMinimumHeight(px(48))
        self._event_combo.view().setStyleSheet(
            f"QListView::item {{ min-height: {px(44)}px; padding: {px(4)}px; }}"
        )
        event_row.addWidget(self._event_combo, 1)
        start_event = BigButton("Démarrer une nouvelle soirée", "secondary")
        start_event.setMinimumSize(px(280), px(BUTTON_HEIGHT))
        start_event.clicked.connect(self._start_event)
        event_row.addWidget(start_event)
        create_sheets = BigButton("Créer les planches-contact", "primary")
        create_sheets.setMinimumSize(px(280), px(BUTTON_HEIGHT))
        create_sheets.clicked.connect(self._generate_contact_sheets)
        layout.addLayout(event_row)
        event_actions = QHBoxLayout()
        self._end_event_button = BigButton("Terminer la soir\u00e9e", "danger")
        self._end_event_button.setMinimumSize(px(280), px(BUTTON_HEIGHT))
        self._end_event_button.clicked.connect(self._end_event)
        event_actions.addStretch(1)
        event_actions.addWidget(self._end_event_button)
        event_actions.addWidget(create_sheets)
        event_actions.addStretch(1)
        layout.addLayout(event_actions)
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
        self._end_event_button.setEnabled(active is not None)
        if active:
            folder_date = datetime.fromtimestamp(active.started_at).strftime("%Y-%m-%d")
            self._event_status.setText(
                f"Soir\u00e9e active : {active.name}. Les prochaines photos iront dans soiree_{folder_date}."
            )
        else:
            self._event_status.setText(
                "Aucune soir\u00e9e active. Les prochaines photos iront dans hors-soiree_YYYY-MM-DD. "
                "D\u00e9marre une soir\u00e9e pour les associer aux planches-contact."
            )

    def _end_event(self) -> None:
        active = self._window.events.active_event()
        if active is None:
            self._refresh_events()
            return
        answer = QMessageBox.question(
            self, "Terminer la soir\u00e9e",
            f"Terminer la soir\u00e9e \u00ab {active.name} \u00bb ? Les prochaines photos iront hors soir\u00e9e.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._window.events.end_event()
        except Exception as exc:
            log.exception("Fin de soiree impossible")
            QMessageBox.warning(self, "Soir\u00e9e", f"Impossible de terminer la soir\u00e9e :\n{exc}")
            return
        self._refresh_events()

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

    def _on_countdown_changed(self, _index: int) -> None:
        seconds = self._countdown.currentData()
        if seconds is None:
            return
        try:
            self._window.config.save_countdown_settings(seconds)
        except (OSError, ValueError) as exc:
            log.exception("Enregistrement du décompte impossible")
            QMessageBox.warning(self, "Décompte", f"Le réglage n'a pas été enregistré :\n{exc}")
            self._countdown.blockSignals(True)
            self._countdown.setCurrentIndex(self._countdown.findData(self._window.config.duree_decompte))
            self._countdown.blockSignals(False)

    def _on_admin_auth_mode_changed(self, _index: int) -> None:
        mode = self._admin_auth_mode.currentData()
        if mode == self._window.config.admin_auth_mode:
            return
        try:
            self._window.config.save_admin_auth_settings(mode, self._window.config.admin_pattern)
        except (OSError, ValueError) as exc:
            log.exception("Enregistrement du mode d'accès administrateur impossible")
            QMessageBox.warning(self, "Accès administrateur", f"Le réglage n'a pas été enregistré :\n{exc}")
            self._admin_auth_mode.blockSignals(True)
            self._admin_auth_mode.setCurrentIndex(
                self._admin_auth_mode.findData(self._window.config.admin_auth_mode))
            self._admin_auth_mode.blockSignals(False)

    def _define_admin_pattern(self) -> None:
        dialog = PatternDialog(self, confirm=True)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.value:
            return
        try:
            self._window.config.save_admin_auth_settings(
                self._window.config.admin_auth_mode, dialog.value)
        except (OSError, ValueError) as exc:
            log.exception("Enregistrement du schéma administrateur impossible")
            QMessageBox.warning(self, "Schéma administrateur", f"Le schéma n'a pas été enregistré :\n{exc}")
            return
        log.info("Schéma d'accès administrateur modifié")

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
        self._detourage_mode.blockSignals(True)
        self._detourage_mode.setCurrentIndex(self._detourage_mode.findData(self._window.config.mode_detourage))
        self._detourage_mode.blockSignals(False)
        self._countdown.blockSignals(True)
        self._countdown.setCurrentIndex(self._countdown.findData(self._window.config.duree_decompte))
        self._countdown.blockSignals(False)
        self._admin_auth_mode.blockSignals(True)
        self._admin_auth_mode.setCurrentIndex(
            self._admin_auth_mode.findData(self._window.config.admin_auth_mode))
        self._admin_auth_mode.blockSignals(False)
        self._update_chroma_controls()
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

    def _edit_guest_emails(self) -> None:
        path = self._window.config.fichier_invites
        try:
            guests = load_guests(path)
        except GuestListError as exc:
            QMessageBox.warning(self, "Liste d'invités illisible", str(exc))
            return
        if not guests:
            QMessageBox.information(self, "Liste vide", "Aucun invité à modifier.")
            return
        GuestEmailDialog(path, guests, self).exec()

    def _calibrate_green_screen(self) -> None:
        if self._window.config.mode_detourage != "fond_vert":
            return
        if self._window.camera.is_active():
            QMessageBox.information(
                self, "Calibration du fond vert",
                "Retourne d’abord à l’accueil pour libérer la caméra, puis relance la calibration."
            )
            return
        GreenScreenCalibrationDialog(self._window, self).exec()

    def _on_detourage_mode_changed(self, _index: int) -> None:
        mode = self._detourage_mode.currentData()
        if mode == self._window.config.mode_detourage:
            self._update_chroma_controls()
            return
        if self._window.camera.is_active():
            self._detourage_mode.blockSignals(True)
            self._detourage_mode.setCurrentIndex(self._detourage_mode.findData(self._window.config.mode_detourage))
            self._detourage_mode.blockSignals(False)
            QMessageBox.information(
                self, "Mode de détourage",
                "Retourne d’abord à l’accueil pour libérer la caméra, puis change le mode de détourage."
            )
            return
        try:
            self._window.config.save_detourage_mode(mode)
            self._window.close_segmenter()
        except (OSError, ValueError) as exc:
            log.exception("Enregistrement du mode de détourage impossible")
            self._detourage_mode.blockSignals(True)
            self._detourage_mode.setCurrentIndex(self._detourage_mode.findData(self._window.config.mode_detourage))
            self._detourage_mode.blockSignals(False)
            QMessageBox.warning(self, "Mode non enregistré", f"Le mode n’a pas été modifié :\n{exc}")
            return
        log.info("Mode de détourage modifié : %s", mode)
        self._update_chroma_controls()
        self._refresh_info()

    def _update_chroma_controls(self) -> None:
        active = self._window.config.mode_detourage == "fond_vert"
        self._chroma_button.setVisible(active)
        self._chroma_button.setEnabled(active and not self._window.camera.is_active())

    def _clear_slideshow(self) -> None:
        self._window.slideshow.clear()
        log.info("Diaporama vidé")
        self._refresh_info()



class GuestEmailDialog(QDialog):
    """Permet de corriger les adresses mail enregistrées dans la liste d'invités."""

    def __init__(self, path, guests: list[Guest], parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._guests = guests
        self.setWindowTitle("Adresses mail des invités")
        screen = parent.screen() if parent else QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        available_width = available.width() if available else px(1100)
        available_height = available.height() if available else px(800)
        self.setMinimumSize(min(px(600), max(320, available_width - px(24))),
                            min(px(420), max(300, available_height - px(24))))
        self.resize(min(px(900), int(available_width * 0.94)),
                    min(px(680), int(available_height * 0.92)))
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(px(8), px(8), px(8), px(8))
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        content = QWidget()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        layout = QVBoxLayout(content)
        note = QLabel("Sélectionne un invité, saisis son adresse avec le clavier tactile, puis valide. "
                      "La touche Effacer vide l'adresse.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._table = QTableWidget(len(guests), 3)
        self._table.setHorizontalHeaderLabels(["Nom affiché", "Pseudo (identifiant)", "Adresse mail"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for row, guest in enumerate(guests):
            name = QTableWidgetItem(guest.display_name)
            pseudo = QTableWidgetItem(guest.pseudo)
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            pseudo.setFlags(pseudo.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, name)
            self._table.setItem(row, 1, pseudo)
            self._table.setItem(row, 2, QTableWidgetItem(guest.email))
        self._email_buffer = TextBuffer(max_length=80, allow_space=False)
        self._selected_guest = QLabel("")
        self._selected_guest.setObjectName("note")
        self._email_field = QLabel("")
        self._email_field.setObjectName("mailfield")
        self._email_field.setMinimumHeight(px(58))
        self._keyboard = VirtualKeyboard(EMAIL_ROWS, compact=True)
        self._keyboard.text_typed.connect(self._email_text)
        self._keyboard.backspace_pressed.connect(self._email_backspace)
        self._keyboard.clear_pressed.connect(self._email_clear)
        self._table.currentCellChanged.connect(self._select_guest)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._selected_guest)
        layout.addWidget(self._email_field)
        layout.addWidget(self._keyboard)
        if guests:
            self._table.setCurrentCell(0, 2)
            self._select_guest(0, 2, -1, -1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setMinimumSize(px(140), px(56))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setMinimumSize(px(140), px(56))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_guest(self, row: int, _column: int, _previous_row: int, _previous_column: int) -> None:
        if not 0 <= row < len(self._guests):
            return
        self._email_buffer.set(self._table.item(row, 2).text())
        self._selected_guest.setText(f"Adresse mail de {self._guests[row].display_name} :")
        self._refresh_email()

    def _refresh_email(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.item(row, 2).setText(self._email_buffer.value)
        self._email_field.setText(self._email_buffer.value + "|")

    def _email_text(self, text: str) -> None:
        self._email_buffer.insert(text)
        self._refresh_email()

    def _email_backspace(self) -> None:
        self._email_buffer.backspace()
        self._refresh_email()

    def _email_clear(self) -> None:
        self._email_buffer.clear()
        self._refresh_email()

    def _save(self) -> None:
        updates: dict[str, str] = {}
        for row, guest in enumerate(self._guests):
            item = self._table.item(row, 2)
            email = normalize_email(item.text() if item is not None else "")
            if email and not is_valid_email(email):
                QMessageBox.warning(
                    self, "Adresse invalide",
                    f"L'adresse indiquée pour {guest.display_name} n'est pas valide.",
                )
                self._table.setCurrentCell(row, 2)
                return
            if email != guest.email:
                updates[guest.pseudo] = email
        try:
            update_guest_emails(self._path, updates)
        except GuestListError as exc:
            QMessageBox.warning(self, "Enregistrement impossible", str(exc))
            return
        self.accept()


class ActivationDialog(QDialog):
    """Interrupteurs persistants des fonctions facultatives du photobooth."""

    def __init__(self, window: "MainWindow", parent: QDialog) -> None:
        super().__init__(parent)
        self._window = window
        cfg = window.config
        self.setWindowTitle("Gérer les activations")
        screen = window.screen()
        available = screen.availableGeometry() if screen else None
        available_width = available.width() if available else px(1000)
        available_height = available.height() if available else px(760)
        self.setMinimumSize(min(px(560), max(320, available_width - px(24))),
                            min(px(420), max(300, available_height - px(24))))
        self.resize(min(px(700), int(available_width * 0.92)),
                    min(px(720), int(available_height * 0.92)))
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
        QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        note = QLabel("Les changements sont enregistrés dans config.ini et appliqués immédiatement.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setMinimumSize(px(140), px(56))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setMinimumSize(px(140), px(56))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _option(layout: QVBoxLayout, text: str, checked: bool) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.setMinimumHeight(px(56))
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
