"""Gros chiffre animé (décompte) et flash blanc, dessinés par-dessus l'aperçu."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget


class CountdownOverlay(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._text = ""
        self._pulse = 0.0   # 1 -> 0 pendant un chiffre : il rétrécit et s'estompe
        self._flash = 0.0   # 1 -> 0 : flash blanc
        self._pulse_anim = self._make_anim(900, self._set_pulse)
        self._flash_anim = self._make_anim(350, self._set_flash)

    def _make_anim(self, duration_ms: int, callback) -> QVariantAnimation:
        anim = QVariantAnimation(self)
        anim.setDuration(duration_ms)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.valueChanged.connect(callback)
        return anim

    def _set_pulse(self, value) -> None:
        self._pulse = float(value)
        self.update()

    def _set_flash(self, value) -> None:
        self._flash = float(value)
        self.update()

    def show_number(self, text: str) -> None:
        self._text = text
        self._pulse = 1.0
        self._pulse_anim.stop()
        self._pulse_anim.start()
        self.update()

    def flash(self) -> None:
        self._flash = 1.0
        self._flash_anim.stop()
        self._flash_anim.start()
        self.update()

    def clear(self) -> None:
        self._pulse_anim.stop()
        self._flash_anim.stop()
        self._text = ""
        self._pulse = 0.0
        self._flash = 0.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._flash > 0:
            painter.fillRect(self.rect(), QColor(255, 255, 255, int(255 * self._flash)))
        if self._text:
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(max(40, int(self.height() * 0.55 * (0.8 + 0.2 * self._pulse))))
            painter.setFont(font)
            alpha = int(255 * (0.35 + 0.65 * self._pulse))
            flags = Qt.AlignmentFlag.AlignCenter.value
            painter.setPen(QColor(20, 18, 43, alpha))                       # ombre
            painter.drawText(self.rect().translated(6, 6), flags, self._text)
            painter.setPen(QColor(255, 209, 102, alpha))
            painter.drawText(self.rect(), flags, self._text)
        painter.end()
