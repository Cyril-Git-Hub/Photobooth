"""Écran d'attente animé, avec le message tactile et quelques photos de la soirée."""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImageReader, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from .scale import px

log = logging.getLogger(__name__)
DEFAULT_PHOTOS = 15
MAX_PHOTOS = 20
ANIMATION_INTERVAL_MS = 40
PHOTO_SPEED_MIN, PHOTO_SPEED_MAX = 0.8, 1.4
PHOTO_TILT_MAX = 12.0


@dataclass
class _FloatingPhoto:
    pixmap: QPixmap
    x: float
    y: float
    vx: float
    vy: float
    angle: float


class ScreensaverOverlay(QWidget):
    def __init__(self, theme, on_start, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._on_start = on_start
        self._message = self._text("screensaver_message", "Touchez pour commencer")
        self.setObjectName("screensaverOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {self._color('background', '#14122b')};")

        self._photos: list[_FloatingPhoto] = []
        self._photo_paths: tuple[Path, ...] = ()
        self._rng = random.Random()
        self._message_x = self._message_y = 0.0
        self._message_vx, self._message_vy = 1.0, 0.8
        self._font = QFont(self.font())
        self._font.setPixelSize(px(28))
        self._font.setBold(True)
        self._timer = QTimer(self)
        self._timer.setInterval(ANIMATION_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)

    def _color(self, name: str, fallback: str) -> str:
        return getattr(self._theme, "colors", {}).get(name, fallback)

    def _text(self, name: str, fallback: str) -> str:
        return getattr(self._theme, name, fallback)

    def set_photos(self, paths: list[Path], photo_count: int = DEFAULT_PHOTOS) -> None:
        if not 1 <= photo_count <= MAX_PHOTOS:
            raise ValueError(f"Le nombre de photos de veille doit être compris entre 1 et {MAX_PHOTOS}.")
        unique_paths = tuple(dict.fromkeys(Path(path) for path in paths if Path(path).is_file()))
        self._photo_paths = unique_paths
        self._photos.clear()
        if not unique_paths:
            self.update()
            return

        selected = self._rng.sample(list(unique_paths), min(photo_count, len(unique_paths)))
        screen_width = self.width() or px(1280)
        screen_height = self.height() or px(720)
        photo_width = min(screen_width, max(px(100), min(px(240), screen_width // 5)))
        photo_height = min(screen_height, max(px(72), min(px(150), screen_height // 5)))
        target = QSize(max(1, photo_width - px(12)), max(1, photo_height - px(12)))
        columns = min(3, len(selected))
        rows = (len(selected) + columns - 1) // columns
        for index, path in enumerate(selected):
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            source_size = reader.size()
            if source_size.isValid():
                reader.setScaledSize(source_size.scaled(target, Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            if image.isNull():
                log.warning("Photo illisible sur l'écran de veille : %s", path)
                continue
            pixmap = QPixmap.fromImage(image)
            col, row = index % columns, index // columns
            x = (col + 0.5) * screen_width / columns
            y = (row + 0.5) * screen_height / rows
            x += self._rng.uniform(-photo_width * 0.15, photo_width * 0.15)
            y += self._rng.uniform(-photo_height * 0.15, photo_height * 0.15)
            vx = self._rng.choice((-1, 1)) * self._rng.uniform(PHOTO_SPEED_MIN, PHOTO_SPEED_MAX)
            vy = self._rng.choice((-1, 1)) * self._rng.uniform(PHOTO_SPEED_MIN, PHOTO_SPEED_MAX)
            angle = self._rng.uniform(-PHOTO_TILT_MAX, PHOTO_TILT_MAX)
            self._photos.append(_FloatingPhoto(pixmap, x, y, vx, vy, angle))
        self._constrain_photos()
        self._reset_message_position()
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reset_message_position()
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reset_message_position()
        self._constrain_photos()

    def _message_size(self) -> tuple[float, float]:
        metrics = QFontMetricsF(self._font)
        max_width = max(1.0, self.width() - px(48))
        width = min(max_width, metrics.horizontalAdvance(self._message) + px(40))
        height = max(float(px(60)), metrics.height() + px(24))
        return width, height

    def _reset_message_position(self) -> None:
        width, height = self._message_size()
        if self.width() > 0 and self.height() > 0:
            self._message_x = max(0.0, (self.width() - width) / 2)
            self._message_y = max(0.0, (self.height() - height) / 2)

    def _constrain_photos(self) -> None:
        for photo in self._photos:
            bound_width, bound_height = self._photo_bounds(photo)
            photo.x = min(max(bound_width / 2, photo.x), max(bound_width / 2, self.width() - bound_width / 2))
            photo.y = min(max(bound_height / 2, photo.y), max(bound_height / 2, self.height() - bound_height / 2))

    @staticmethod
    def _photo_bounds(photo: _FloatingPhoto) -> tuple[float, float]:
        width = photo.pixmap.width() + px(12)
        height = photo.pixmap.height() + px(12)
        angle = math.radians(photo.angle)
        return (abs(width * math.cos(angle)) + abs(height * math.sin(angle)),
                abs(width * math.sin(angle)) + abs(height * math.cos(angle)))

    @staticmethod
    def _move(x: float, y: float, vx: float, vy: float,
              max_x: float, max_y: float) -> tuple[float, float, float, float]:
        x += vx
        y += vy
        if x < 0 or x > max_x:
            vx, x = -vx, min(max(0.0, x), max_x)
        if y < 0 or y > max_y:
            vy, y = -vy, min(max(0.0, y), max_y)
        return x, y, vx, vy

    def _advance(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        message_width, message_height = self._message_size()
        (self._message_x, self._message_y,
         self._message_vx, self._message_vy) = self._move(
            self._message_x, self._message_y, self._message_vx, self._message_vy,
            max(0.0, self.width() - message_width), max(0.0, self.height() - message_height),
        )
        for photo in self._photos:
            bound_width, bound_height = self._photo_bounds(photo)
            half_width, half_height = bound_width / 2, bound_height / 2
            x, y, photo.vx, photo.vy = self._move(
                photo.x - half_width, photo.y - half_height, photo.vx, photo.vy,
                max(0.0, self.width() - bound_width), max(0.0, self.height() - bound_height))
            photo.x, photo.y = x + half_width, y + half_height
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for photo in self._photos:
            card = QRectF(-photo.pixmap.width() / 2 - px(6),
                          -photo.pixmap.height() / 2 - px(6),
                          photo.pixmap.width() + px(12), photo.pixmap.height() + px(12))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 100))
            painter.save()
            painter.translate(photo.x, photo.y)
            painter.rotate(photo.angle)
            painter.drawRoundedRect(card.translated(px(3), px(4)), px(8), px(8))
            painter.setBrush(QColor("#ffffff"))
            painter.drawRoundedRect(card, px(8), px(8))
            painter.drawPixmap(-photo.pixmap.width() // 2, -photo.pixmap.height() // 2, photo.pixmap)
            painter.restore()

        message_width, message_height = self._message_size()
        message_rect = self._message_rect(message_width, message_height)
        painter.setPen(QColor(self._color("accent", "#ffd166")))
        painter.setBrush(QColor(self._color("primary", "#ff4d8d")))
        painter.drawRoundedRect(message_rect, px(18), px(18))
        painter.setFont(self._font)
        painter.setPen(QColor(self._color("white", "#ffffff")))
        painter.drawText(message_rect, Qt.AlignmentFlag.AlignCenter, self._message)
        painter.end()

    def _message_rect(self, width: float, height: float):
        return QRectF(self._message_x, self._message_y, width, height)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_start(event.position().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)
