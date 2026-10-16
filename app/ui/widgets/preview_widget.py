"""Zone d'affichage d'une image (aperçu webcam ou photo), avec barres noires si le format diffère."""
from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .countdown_overlay import CountdownOverlay
from ..scale import px


class PreviewWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image: QImage | None = None
        self._message = ""
        self.setMinimumSize(px(640), px(360))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.overlay = CountdownOverlay(self)

    def set_image(self, image: QImage) -> None:
        self._image = image
        self._message = ""
        self.update()

    def set_message(self, text: str) -> None:
        """Affiche un message à la place de l'image (démarrage, erreur…)."""
        self._image = None
        self._message = text
        self.update()

    def resizeEvent(self, event) -> None:
        self.overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def _fit_rect(self, width: int, height: int) -> QRect:
        ratio = min(self.width() / width, self.height() / height)
        target_w, target_h = int(width * ratio), int(height * ratio)
        return QRect((self.width() - target_w) // 2, (self.height() - target_h) // 2, target_w, target_h)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0a1a"))
        if self._image is not None and not self._image.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(self._fit_rect(self._image.width(), self._image.height()), self._image)
        elif self._message:
            font = QFont(self.font())
            font.setPixelSize(px(30))
            painter.setFont(font)
            painter.setPen(QColor("#b8b2d9"))
            flags = Qt.AlignmentFlag.AlignCenter.value | Qt.TextFlag.TextWordWrap.value
            painter.drawText(self.rect().adjusted(40, 40, -40, -40), flags, self._message)
        painter.end()
