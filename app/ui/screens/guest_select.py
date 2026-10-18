"""« Qui es-tu ? » : liste d'invités avec recherche au clavier tactile."""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QScroller, QVBoxLayout, QWidget,
)

from ...core.guests import Guest, GuestListError, load_guests, search_guests
from ...core.keyboards import SEARCH_ROWS
from ...core.text_buffer import TextBuffer
from ..widgets.big_button import BigButton
from ..widgets.virtual_keyboard import VirtualKeyboard
from .base import BaseScreen
from ..scale import px

log = logging.getLogger(__name__)

COLUMNS = 3
EMPTY_LIST = ("La liste d'invités est vide.\nAjoute des lignes dans le fichier {name} "
              "(colonnes : nom, prénom, mail), puis reviens sur cet écran.")


class GuestSelectScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._guests: list[Guest] = []
        self._error = ""
        self._loaded: tuple | None = None          # (fichier, date de modification) du dernier chargement
        self._search_open = False
        self._query = TextBuffer(max_length=40, allow_space=True)

        heading = QLabel("Qui es-tu ?")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._search_label = QLabel("")
        self._search_label.setObjectName("search")
        self._search_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setSpacing(px(16))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self._grid_host)
        QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self._keyboard = VirtualKeyboard(SEARCH_ROWS)
        self._keyboard.setVisible(False)
        self._keyboard.text_typed.connect(self._on_text)
        self._keyboard.backspace_pressed.connect(self._on_backspace)
        self._keyboard.clear_pressed.connect(self._on_clear)

        back = BigButton("Retour", "secondary")
        back.clicked.connect(lambda: self.nav.go_back())
        self._search_button = BigButton("Rechercher", "secondary")
        self._search_button.clicked.connect(lambda: self._toggle_search())
        not_listed = BigButton("Je ne suis pas dans la liste")
        not_listed.clicked.connect(lambda: self._not_listed())
        buttons = QHBoxLayout()
        buttons.setSpacing(px(24))
        buttons.addStretch(1)
        for button in (back, self._search_button, not_listed):
            buttons.addWidget(button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(30), px(24), px(30), px(24))
        layout.setSpacing(px(12))
        layout.addWidget(heading)
        layout.addWidget(self._search_label)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._keyboard)
        layout.addLayout(buttons)

    # ---------- chargement ----------

    def on_enter(self) -> None:
        self._load_if_needed()
        self._query.clear()
        self._search_open = False
        self._refresh()

    def _load_if_needed(self) -> None:
        """Relit le fichier configuré s'il a changé depuis le dernier passage (ou si la lecture avait échoué)."""
        path = self.config.fichier_invites
        try:
            stamp = (str(path), path.stat().st_mtime)
        except OSError:
            stamp = (str(path), None)
        if stamp == self._loaded and not self._error:
            return
        try:
            self._guests = load_guests(path)
            self._error = ""
        except GuestListError as exc:
            log.error("Liste d'invités : %s", exc.args[0].replace("\n", " "))
            self._guests, self._error = [], exc.args[0]
        self._loaded = stamp

    # ---------- affichage ----------

    def _refresh(self) -> None:
        self._keyboard.setVisible(self._search_open)
        self._search_button.setText("Fermer le clavier" if self._search_open else "Rechercher")
        self._search_label.setVisible(self._search_open)
        self._search_label.setText(f"Recherche : {self._query.value}|")
        self._build_grid()

    def _build_grid(self) -> None:
        while self._grid.count():
            widget = self._grid.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        matches = search_guests(self._guests, self._query.value)
        if self._error or not matches:
            text = (self._error or (EMPTY_LIST.format(name=self.config.fichier_invites.name) if not self._guests
                                    else f"Aucun invité ne correspond à « {self._query.value} »."))
            message = QLabel(text)
            message.setObjectName("note")
            message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            message.setWordWrap(True)
            self._grid.addWidget(message, 0, 0)
            return
        for index, guest in enumerate(matches):
            tile = BigButton(guest.display_name, "secondary")
            tile.setMinimumSize(px(300), px(84))
            tile.clicked.connect(lambda _checked=False, g=guest: self._choose(g))
            self._grid.addWidget(tile, index // COLUMNS, index % COLUMNS)

    # ---------- recherche ----------

    def _toggle_search(self) -> None:
        self._search_open = not self._search_open
        if not self._search_open:
            self._query.clear()
        self._refresh()

    def _on_text(self, text: str) -> None:
        self._query.insert(text)
        self._refresh()

    def _on_backspace(self) -> None:
        self._query.backspace()
        self._refresh()

    def _on_clear(self) -> None:
        self._query.clear()
        self._refresh()

    # ---------- choix ----------

    def _choose(self, guest: Guest) -> None:
        self.session.guest_last_name = guest.last_name
        self.session.guest_first_name = guest.first_name
        self.session.email = guest.email
        self.nav.go_next()

    def _not_listed(self) -> None:
        self.session.guest_last_name = ""
        self.session.guest_first_name = ""
        self.session.email = ""
        self.nav.go_next()
