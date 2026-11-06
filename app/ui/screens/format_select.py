"""Choix du format : une seule photo, ou photomaton (bande de plusieurs photos)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..widgets.big_button import BigButton
from .base import BaseScreen
from ..scale import px, touch_px


class FormatSelectScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        heading = QLabel("Quel format ?")
        heading.setObjectName("heading")
        heading.setProperty("screenRole", "screenTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._single = BigButton("Photo unique", "notListed")
        self._single.setObjectName("formatOptionButton")
        self._single.setMinimumSize(px(330), touch_px(84))
        self._single.setMaximumWidth(px(450))
        self._single.clicked.connect(lambda: self._choose("single"))
        self._strip = BigButton("Photomaton", "notListed")
        self._strip.setObjectName("formatOptionButton")
        self._strip.setMinimumSize(px(330), touch_px(84))
        self._strip.setMaximumWidth(px(450))
        self._strip.clicked.connect(lambda: self._choose("strip"))
        self._gif = BigButton("GIF animé", "notListed")
        self._gif.setObjectName("formatOptionButton")
        self._gif.setMinimumSize(px(330), touch_px(84))
        self._gif.setMaximumWidth(px(450))
        self._gif.clicked.connect(self._choose_gif)
        self._challenge = BigButton("Casting/Audition", "notListed")
        self._challenge.setObjectName("formatOptionButton")
        self._challenge.setMinimumSize(px(330), touch_px(84))
        self._challenge.setMaximumWidth(px(450))
        self._challenge.clicked.connect(lambda: self.nav.go_to("challenge"))
        self._guestbook = BigButton("Livre d'or vidéo", "guestbook")
        self._guestbook.setObjectName("formatOptionButton")
        self._guestbook.setMinimumSize(px(330), touch_px(84))
        self._guestbook.setMaximumWidth(px(450))
        self._guestbook.clicked.connect(self._choose_guestbook)

        self._email_note = QLabel("")
        self._email_note.setObjectName("summary")
        self._email_note.setAlignment(Qt.AlignmentFlag.AlignCenter)

        back = BigButton("Retour", "secondary")
        back.clicked.connect(lambda: self.nav.go_to("guest_select"))

        self._choices = QVBoxLayout()
        self._choices.setSpacing(px(24))
        self._option_rows = QVBoxLayout()
        self._option_rows.setSpacing(px(12))
        self._top_row = self._make_choice_row()
        self._bottom_row = self._make_choice_row()
        self._option_rows.addWidget(self._top_row)
        self._option_rows.addWidget(self._bottom_row)
        self._choices.addLayout(self._option_rows)
        guestbook_row = QHBoxLayout()
        guestbook_row.addStretch(1)
        guestbook_row.addWidget(self._guestbook)
        guestbook_row.addStretch(1)
        self._choices.addLayout(guestbook_row)
        self._arrange_choices()
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(back)
        footer.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(48), px(28), px(48), px(24))
        layout.setSpacing(px(18))
        layout.addWidget(heading)
        layout.addStretch(1)
        layout.addLayout(self._choices)
        layout.addStretch(1)
        layout.addWidget(self._email_note)
        layout.addLayout(footer)

    def on_enter(self) -> None:
        email = self.session.email.strip()
        self._email_note.setText(f"La photo sera envoyée sur ton mail : {email}" if email else "")
        self._email_note.setVisible(bool(email))
        poses = self.config.nb_poses
        has_strip = poses >= 2             # un « photomaton » d'une seule pose n'aurait pas de sens
        self._single.setVisible(True)
        self._strip.setText("Photomaton")
        self._strip.setVisible(has_strip)
        self._gif.setVisible(self.config.gif_actif)
        self._challenge.setVisible(self.config.defis_actifs)
        self._guestbook.setVisible(
            self.config.livre_or_actif and self.nav.events.active_event() is not None
        )
        self._arrange_choices()

    def _make_choice_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(px(36))
        return row

    @staticmethod
    def _fill_choice_row(row: QWidget, buttons: list[BigButton]) -> None:
        layout = row.layout()
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        if not buttons:
            row.hide()
            return
        layout.addStretch(1)
        for button in buttons:
            layout.addWidget(button)
            button.show()
        layout.addStretch(1)
        row.show()

    def _arrange_choices(self) -> None:
        options = (self._single, self._strip, self._gif, self._challenge)
        visible = [button for button in options if not button.isHidden()]
        self._fill_choice_row(self._top_row, visible[:2])
        self._fill_choice_row(self._bottom_row, visible[2:])

    def _choose(self, photo_format: str) -> None:
        self.session.photo_format = photo_format
        self.session.background_path = None
        self.session.frame_mode = False
        self.session.frame_path = None
        self.session.clear_virtual_masks()
        self._clear_challenge()
        self.nav.go_to("background_select")

    def _choose_gif(self) -> None:
        self.session.photo_format = "gif"
        self.session.background_path = None
        self.session.frame_mode = False
        self.session.frame_path = None
        self.session.clear_virtual_masks()
        self._clear_challenge()
        self.nav.go_to("gif_options")

    def _choose_guestbook(self) -> None:
        if not self.config.livre_or_actif:
            return
        event = self.nav.events.active_event()
        if event is None:
            self._guestbook.hide()
            return
        self.session.event_id = event.id
        self._clear_challenge()
        self.nav.go_to("guestbook")

    def _clear_challenge(self) -> None:
        self.session.challenge_id = ""
        self.session.challenge_title = ""
        self.session.challenge_instruction = ""
        self.session.challenge_background_required = False
        self.session.challenge_mask = ""
        self.session.challenge_style = ""
        self.session.challenge_reference_png = None
        self.session.challenge_guest_name = ""
        self.session.challenge_type = "photo"
        self.session.dance_pose_ids = []
