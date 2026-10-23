"""Zone d'affichage d'une image (aperçu webcam ou photo), avec barres noires si le format diffère."""
from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from .countdown_overlay import CountdownOverlay
from ..scale import px


class PreviewWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image: QImage | None = None
        self._message = ""
        self._colors: dict[str, str] = {}
        self.setMinimumSize(px(640), px(360))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.overlay = CountdownOverlay(self)
        self._reference = QLabel(self)
        self._reference_source: QPixmap | None = None
        self._reference.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reference.setStyleSheet("background: rgba(18, 16, 42, 220); border: 3px solid #ffc44d; padding: 5px;")
        self._reference.hide()

    def set_reference_image(self, image: QImage | None, colors: dict[str, str] | None = None) -> None:
        if image is None or image.isNull():
            self._reference_source = None
            self._reference.clear()
            self._reference.hide()
            return
        self._reference_source = QPixmap.fromImage(image)
        palette = colors or {}
        panel = palette.get("challenge_panel", "#12102a")
        border = palette.get("reference_border", "#ffc44d")
        self._reference.setStyleSheet(
            f"background-color: {panel}; border: 3px solid {border}; padding: 5px;"
        )
        self._reference.show()
        self._position_reference()
        self._reference.raise_()
        self.overlay.raise_()

    def set_image(self, image: QImage) -> None:
        self._image = image
        self._message = ""
        self.update()

    def set_colors(self, colors: dict[str, str] | None) -> None:
        self._colors = colors or {}
        self.update()

    def set_message(self, text: str) -> None:
        """Affiche un message à la place de l'image (démarrage, erreur…)."""
        self._image = None
        self._message = text
        self.update()

    def resizeEvent(self, event) -> None:
        self.overlay.setGeometry(self.rect())
        self._position_reference()
        super().resizeEvent(event)

    def _position_reference(self) -> None:
        if not self._reference.isVisible():
            return
        margin = max(8, int(min(self.width(), self.height()) * 0.025))
        width = max(1, int(self.width() * 0.24))
        height = max(1, int(self.height() * 0.30))
        pixmap = self._reference_source
        if pixmap is not None:
            fitted = pixmap.scaled(max(1, width - 16), max(1, height - 16),
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            self._reference.setPixmap(fitted)
            width = fitted.width() + 16
            height = fitted.height() + 16
        self._reference.setGeometry(self.width() - margin - width,
                                    self.height() - margin - height, width, height)

    def _fit_rect(self, width: int, height: int) -> QRect:
        ratio = min(self.width() / width, self.height() / height)
        target_w, target_h = int(width * ratio), int(height * ratio)
        return QRect((self.width() - target_w) // 2, (self.height() - target_h) // 2, target_w, target_h)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._colors.get("mail_background", "#0b0a1a")))
        if self._image is not None and not self._image.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(self._fit_rect(self._image.width(), self._image.height()), self._image)
        elif self._message:
            font = QFont(self.font())
            font.setPixelSize(px(30))
            painter.setFont(font)
            painter.setPen(QColor(self._colors.get("muted", "#b8b2d9")))
            flags = Qt.AlignmentFlag.AlignCenter.value | Qt.TextFlag.TextWordWrap.value
            painter.drawText(self.rect().adjusted(40, 40, -40, -40), flags, self._message)
        painter.end()
