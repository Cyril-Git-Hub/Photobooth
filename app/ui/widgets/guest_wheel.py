"""Roue animée de tirage au sort parmi les invités."""
from __future__ import annotations

import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ..scale import px


class GuestWheel(QWidget):
    finished = pyqtSignal(int)

    _COLORS = ("#ef476f", "#ffd166", "#06d6a0", "#118ab2", "#9b5de5", "#f15bb5")
    _DURATION = 5.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._names: list[str] = []
        self._angle = 0.0
        self._start_angle = 0.0
        self._target_angle = 0.0
        self._started_at = 0.0
        self._target_index = -1
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        self.setMinimumSize(px(340), px(340))
        self.setMaximumSize(px(560), px(560))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    @property
    def spinning(self) -> bool:
        return self._timer.isActive()

    def set_names(self, names: list[str]) -> None:
        self.stop()
        self._names = names[:]
        self._angle = 0.0
        self.update()

    def spin(self) -> None:
        if self.spinning or not self._names:
            return
        self._target_index = random.randrange(len(self._names))
        sector = 360.0 / len(self._names)
        desired = (-(self._target_index + 0.5) * sector) % 360.0
        distance = (desired - self._angle) % 360.0
        self._start_angle = self._angle
        self._target_angle = self._angle + random.randint(6, 9) * 360.0 + distance
        self._started_at = time.monotonic()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._target_index = -1
        self.update()

    def sizeHint(self):
        return self.minimumSize()

    def _advance(self) -> None:
        progress = min(1.0, (time.monotonic() - self._started_at) / self._DURATION)
        eased = 1.0 - (1.0 - progress) ** 4
        self._angle = self._start_angle + (self._target_angle - self._start_angle) * eased
        self.update()
        if progress >= 1.0:
            self._timer.stop()
            self._angle = self._target_angle % 360.0
            index = self._target_index
            self._target_index = -1
            self.update()
            self.finished.emit(index)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.contentsRect()
        side = min(bounds.width(), bounds.height()) - px(28)
        if side <= 0:
            return
        radius = side / 2
        center = QPointF(bounds.center())
        wheel_radius = radius - px(10)

        if not self._names:
            painter.setPen(QColor("#ffffff"))
            painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, "Aucun invité disponible")
            return

        sector = 2 * math.pi / len(self._names)
        for index, name in enumerate(self._names):
            start = math.radians(self._angle) + index * sector - math.pi / 2
            end = start + sector
            path = QPainterPath()
            path.moveTo(center)
            steps = max(2, min(32, math.ceil(32 * sector / (2 * math.pi))))
            for step in range(steps + 1):
                angle = start + (end - start) * step / steps
                path.lineTo(QPointF(center.x() + wheel_radius * math.cos(angle),
                                    center.y() + wheel_radius * math.sin(angle)))
            path.closeSubpath()
            painter.setPen(QPen(QColor("#ffffff"), px(1)))
            painter.setBrush(QColor(self._COLORS[index % len(self._COLORS)]))
            painter.drawPath(path)

            midpoint = start + sector / 2
            label_radius = wheel_radius * 0.57
            point = QPointF(center.x() + label_radius * math.cos(midpoint),
                            center.y() + label_radius * math.sin(midpoint))
            label_width = wheel_radius * 0.8
            font = QFont(self.font())
            font.setPixelSize(px(14))
            painter.setFont(font)
            painter.setPen(QPen(QColor("#ffffff"), px(1)))
            painter.save()
            painter.translate(point)
            rotation = math.degrees(midpoint)
            if 90 < rotation % 360 < 270:
                rotation += 180
            painter.rotate(rotation)
            metrics = QFontMetricsF(font)
            while metrics.horizontalAdvance(name) > label_width and font.pixelSize() > px(9):
                font.setPixelSize(font.pixelSize() - 1)
                painter.setFont(font)
                metrics = QFontMetricsF(font)
            text_rect = QRectF(-label_width / 2, -px(18), label_width, px(36))
            painter.setPen(QColor("#18202a"))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.drawText(
                    text_rect.translated(px(dx), px(dy)),
                    Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                    name,
                )
            painter.setPen(QColor("#ffffff"))
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                name,
            )
            painter.restore()

        pointer = QPainterPath()
        pointer.moveTo(center.x(), center.y() - wheel_radius + px(2))
        pointer.lineTo(center.x() - px(15), center.y() - wheel_radius - px(20))
        pointer.lineTo(center.x() + px(15), center.y() - wheel_radius - px(20))
        pointer.closeSubpath()
        painter.setPen(QPen(QColor("#ffffff"), px(2)))
        painter.setBrush(QColor("#ffffff"))
        painter.drawPath(pointer)
