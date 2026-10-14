"""Fenêtre du diaporama, plein écran sur le second écran : affichage uniquement (le rythme est géré par le contrôleur)."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QImage, QImageReader, QLinearGradient, QPainter
from PyQt6.QtWidgets import QWidget

log = logging.getLogger(__name__)

FADE_MS = 700
IDLE_NOTE = "Les photos de la soirée apparaîtront ici !"


class SlideshowWindow(QWidget):
    def __init__(self, config) -> None:
        super().__init__()
        self._title = config.pm_titre or "Photo Booth"
        self._current: QImage | None = None
        self._previous: QImage | None = None
        self._fade = 1.0
        self._idle = True
        self.setWindowTitle("Photo Booth : diaporama")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)   # ne vole jamais le focus à la borne
        self.setCursor(Qt.CursorShape.BlankCursor)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(FADE_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_fade)

    # ---------- placement ----------

    def show_on(self, screen) -> None:
        """Plein écran sur `screen`."""
        self.setScreen(screen)
        self.move(screen.geometry().topLeft())
        self.resize(screen.geometry().size())
        self.showFullScreen()

    def show_windowed(self) -> None:
        """Fenêtre ordinaire (développement, sans second écran)."""
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.resize(960, 540)
        self.show()

    # ---------- contenu ----------

    def show_idle(self, title: str | None = None) -> None:
        self._title = title or self._title
        self._current = self._previous = None
        self._idle = True
        self.update()

    def show_photo(self, path: Path) -> bool:
        """Affiche la photo avec un fondu. False si elle est illisible (le contrôleur la retire alors de la liste)."""
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():                     # décodage directement à la taille de l'écran : rapide, peu de mémoire
            reader.setScaledSize(size.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            log.warning("Photo illisible, retirée du diaporama : %s", path)
            return False
        self._previous = None if self._idle else self._current
        self._current, self._idle = image, False
        self._anim.stop()
        self._fade = 0.0
        self._anim.start()
        return True

    def _on_fade(self, value) -> None:
        self._fade = float(value)
        if self._fade >= 1.0:
            self._previous = None
        self.update()

    # ---------- dessin ----------

    def _draw_centered(self, painter: QPainter, image: QImage) -> None:
        painter.drawImage((self.width() - image.width()) // 2, (self.height() - image.height()) // 2, image)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#1a1a2e"))
        gradient.setColorAt(1.0, QColor("#0b0a1a"))
        painter.fillRect(self.rect(), gradient)
        if self._idle or self._current is None:
            title_font = QFont(self.font())
            title_font.setPixelSize(max(40, self.height() // 10))
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.setPen(QColor("#ffd166"))
            painter.drawText(self.rect().adjusted(40, 0, -40, -self.height() // 8),
                             Qt.AlignmentFlag.AlignCenter.value | Qt.TextFlag.TextWordWrap.value, self._title)
            note_font = QFont(self.font())
            note_font.setPixelSize(max(20, self.height() // 28))
            painter.setFont(note_font)
            painter.setPen(QColor("#b8b2d9"))
            painter.drawText(self.rect().adjusted(40, self.height() // 2 + self.height() // 12, -40, 0),
                             Qt.AlignmentFlag.AlignHCenter.value | Qt.AlignmentFlag.AlignTop.value, IDLE_NOTE)
        else:
            if self._previous is not None and self._fade < 1.0:
                self._draw_centered(painter, self._previous)         # l'ancienne photo reste dessous pendant le fondu
            painter.setOpacity(self._fade if self._previous is not None else 1.0)
            self._draw_centered(painter, self._current)
        painter.end()
