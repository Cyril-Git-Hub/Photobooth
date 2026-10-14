"""Choix du décor : onglets par thème, miniatures tactiles, « Surprends-moi » et « Sans décor »."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImageReader, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QScroller, QToolButton, QVBoxLayout, QWidget,
)

from ...core import backgrounds
from ..widgets.big_button import BigButton
from .base import BaseScreen

log = logging.getLogger(__name__)

ICON_SIZE = QSize(240, 135)
COLUMNS = 4
EMPTY_TEXT = ("Aucun décor trouvé.\nAjoute des images (jpg, png) dans les sous-dossiers du dossier « fonds », "
              "puis reviens sur cet écran.")


class BackgroundSelectScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        self._themes: list[backgrounds.Theme] = []
        self._current = 0
        self._icons: dict[tuple[str, float], QIcon] = {}   # miniatures déjà calculées

        heading = QLabel("Choisis ton décor")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._tabs = QHBoxLayout()
        self._tabs.setSpacing(16)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setSpacing(20)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(self._grid_host)
        # défilement au doigt (glisser) sur l'écran tactile
        QScroller.grabGesture(self._scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        back = BigButton("Retour", "secondary")
        back.clicked.connect(lambda: self.nav.go_back())
        none = BigButton("Sans décor", "secondary")
        none.clicked.connect(lambda: self._no_background())
        surprise = BigButton("Surprends-moi !")
        surprise.clicked.connect(lambda: self._surprise())
        buttons = QHBoxLayout()
        buttons.setSpacing(30)
        buttons.addStretch(1)
        for button in (back, none, surprise):
            buttons.addWidget(button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)
        layout.addWidget(heading)
        layout.addLayout(self._tabs)
        layout.addWidget(self._scroll, 1)
        layout.addLayout(buttons)

    # ---------- affichage ----------

    def on_enter(self) -> None:
        self._themes = backgrounds.scan_backgrounds(self.config.dossier_fonds)   # relu à chaque passage
        if self._current >= len(self._themes):
            self._current = 0
        self._build_tabs()
        self._build_grid()

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def _build_tabs(self) -> None:
        self._clear(self._tabs)
        self._tabs.addStretch(1)
        for index, theme in enumerate(self._themes):
            tab = BigButton(theme.name, "primary" if index == self._current else "secondary")
            tab.setMinimumSize(160, 64)
            tab.clicked.connect(lambda _checked=False, i=index: self._select_theme(i))
            self._tabs.addWidget(tab)
        self._tabs.addStretch(1)

    def _select_theme(self, index: int) -> None:
        self._current = index
        self._build_tabs()
        self._build_grid()

    def _build_grid(self) -> None:
        self._clear(self._grid)
        if not self._themes:
            empty = QLabel(EMPTY_TEXT)
            empty.setObjectName("note")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self._grid.addWidget(empty, 0, 0)
            return
        column = row = 0
        for path in self._themes[self._current].images:
            icon = self._icon_for(path)
            if icon is None:
                continue
            tile = QToolButton()
            tile.setIcon(icon)
            tile.setIconSize(ICON_SIZE)
            tile.setText(path.stem)
            tile.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            tile.setMinimumSize(ICON_SIZE.width() + 30, ICON_SIZE.height() + 70)
            tile.clicked.connect(lambda _checked=False, p=path: self._choose(p))
            self._grid.addWidget(tile, row, column)
            column += 1
            if column == COLUMNS:
                column, row = 0, row + 1

    def _icon_for(self, path: Path) -> QIcon | None:
        try:
            key = (str(path), path.stat().st_mtime)
        except OSError:
            return None
        icon = self._icons.get(key)
        if icon is None:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():   # décodage directement à la taille de la miniature : bien plus rapide
                reader.setScaledSize(size.scaled(ICON_SIZE, Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            if image.isNull():
                log.warning("Miniature impossible, image ignorée : %s", path)
                return None
            icon = QIcon(QPixmap.fromImage(image))
            self._icons[key] = icon
        return icon

    # ---------- choix ----------

    def _choose(self, path: Path) -> None:
        self.session.background_path = path
        self.nav.go_next()

    def _surprise(self) -> None:
        path = backgrounds.random_background(self._themes)
        if path is not None:
            self._choose(path)

    def _no_background(self) -> None:
        self.session.background_path = None
        self.nav.go_next()
