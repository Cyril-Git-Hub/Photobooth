"""Écran d'attente tactile affiché quand la borne est inactive sur l'accueil."""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .scale import px


class ScreensaverOverlay(QWidget):
    def __init__(self, theme, on_start) -> None:
        super().__init__()
        self._theme = theme
        self._on_start = on_start
        self.setObjectName("screensaverOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {self._color('background', '#14122b')};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(48), px(36), px(48), px(36))
        layout.setSpacing(px(20))
        layout.addStretch(1)

        self._title = QLabel(self._text("welcome_title", "Photobooth"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._title.setStyleSheet(
            f"color: {self._color('accent', '#ffd166')}; font-size: {px(58)}px; font-weight: 700; background: transparent;"
        )
        layout.addWidget(self._title)

        self._visual = QLabel()
        self._visual.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._visual.setStyleSheet("background: transparent;")
        self._visual.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        image_path = getattr(theme, "welcome_image", None) or getattr(theme, "logo", None)
        self._pixmap = QPixmap(str(image_path)) if image_path is not None else QPixmap()
        if not self._pixmap.isNull():
            layout.addWidget(self._visual, 1)
        else:
            self._visual.hide()

        self._message = QLabel(self._text("screensaver_message", "Touchez pour commencer"))
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(False)
        self._message.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._message.setMinimumHeight(px(56))
        self._message.setMaximumWidth(px(700))
        self._message.setStyleSheet(
            f"color: {self._color('white', '#ffffff')}; font-size: {px(20)}px; font-weight: 700; "
            f"background-color: {self._color('primary', '#ff4d8d')}; border: 2px solid "
            f"{self._color('accent', '#ffd166')}; border-radius: {px(18)}px; padding: {px(8)}px {px(18)}px;"
        )
        layout.addWidget(self._message, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

    def _color(self, name: str, fallback: str) -> str:
        return getattr(self._theme, "colors", {}).get(name, fallback)

    def _text(self, name: str, fallback: str) -> str:
        return getattr(self._theme, name, fallback)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._pixmap.isNull():
            target = QSize(int(self.width() * 0.72), int(self.height() * 0.50))
            self._visual.setPixmap(self._pixmap.scaled(
                target, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_start(event.position().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

