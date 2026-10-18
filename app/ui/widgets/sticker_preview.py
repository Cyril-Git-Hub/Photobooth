"""Aperçu de photo avec autocollants déplaçables au doigt ou à la souris."""
from __future__ import annotations

import math
import logging

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap

from .preview_widget import PreviewWidget
from ...core.stickers import StickerAsset, StickerPlacement, load_sticker

log = logging.getLogger(__name__)


class StickerPreview(PreviewWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.placements: list[StickerPlacement] = []
        self.selected_index = -1
        self._pixmaps: dict[object, QPixmap] = {}
        self._drag_offset = QPointF()
        self._render_error_logged = False

    def set_image(self, image: QImage) -> None:
        super().set_image(image)
        self.update()

    def clear_stickers(self) -> None:
        self.placements.clear()
        self.selected_index = -1
        self._render_error_logged = False
        self.update()

    def add_sticker(self, asset: StickerAsset) -> None:
        self.placements.append(StickerPlacement(asset))
        self.selected_index = len(self.placements) - 1
        self._render_error_logged = False
        self.update()

    def adjust_selected(self, *, scale: float = 1.0, rotation: float = 0.0) -> None:
        if not 0 <= self.selected_index < len(self.placements):
            return
        old = self.placements[self.selected_index]
        self.placements[self.selected_index] = StickerPlacement(
            old.asset, old.center_x, old.center_y,
            min(0.8, max(0.06, old.width_ratio * scale)),
            (old.rotation + rotation) % 360,
        )
        self.update()

    def remove_selected(self) -> None:
        if not 0 <= self.selected_index < len(self.placements):
            return
        self.placements.pop(self.selected_index)
        self.selected_index = min(self.selected_index, len(self.placements) - 1)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._image is None or self._image.isNull():
            return
        try:
            self._paint_stickers()
        except Exception:
            if not self._render_error_logged:
                log.exception("Affichage des autocollants impossible")
                self._render_error_logged = True

    def _paint_stickers(self) -> None:
        photo_rect = self._fit_rect(self._image.width(), self._image.height())
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            for index, placement in enumerate(self.placements):
                pixmap = self._pixmaps.get(placement.asset.path)
                if pixmap is None:
                    sticker = load_sticker(placement.asset.path)
                    pixmap = QPixmap.fromImage(sticker) if not sticker.isNull() else QPixmap()
                    self._pixmaps[placement.asset.path] = pixmap
                if pixmap.isNull():
                    continue
                sticker_width = max(1, round(photo_rect.width() * placement.width_ratio))
                sticker_height = max(1, round(pixmap.height() * sticker_width / pixmap.width()))
                center = QPointF(photo_rect.left() + photo_rect.width() * placement.center_x,
                                 photo_rect.top() + photo_rect.height() * placement.center_y)
                painter.save()
                painter.translate(center)
                painter.rotate(placement.rotation)
                rect = QRectF(-sticker_width / 2, -sticker_height / 2, sticker_width, sticker_height)
                painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
                if index == self.selected_index:
                    painter.setPen(QPen(QColor("#ffd166"), 2, Qt.PenStyle.DashLine))
                    painter.drawRect(rect)
                painter.restore()
        finally:
            painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._image is None:
            super().mousePressEvent(event)
            return
        photo_rect = self._fit_rect(self._image.width(), self._image.height())
        point = event.position()
        self.selected_index = self._hit_test(point, photo_rect)
        if self.selected_index >= 0:
            placement = self.placements[self.selected_index]
            center = QPointF(photo_rect.left() + photo_rect.width() * placement.center_x,
                             photo_rect.top() + photo_rect.height() * placement.center_y)
            self._drag_offset = point - center
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not event.buttons() & Qt.MouseButton.LeftButton or not 0 <= self.selected_index < len(self.placements):
            super().mouseMoveEvent(event)
            return
        photo_rect = self._fit_rect(self._image.width(), self._image.height())
        point = event.position() - self._drag_offset
        placement = self.placements[self.selected_index]
        half_width = photo_rect.width() * placement.width_ratio / 2
        half_height = half_width * self._sticker_aspect(placement.asset)
        center_x = min(photo_rect.right() - half_width, max(photo_rect.left() + half_width, point.x()))
        center_y = min(photo_rect.bottom() - half_height, max(photo_rect.top() + half_height, point.y()))
        self.placements[self.selected_index] = StickerPlacement(
            placement.asset,
            (center_x - photo_rect.left()) / photo_rect.width(),
            (center_y - photo_rect.top()) / photo_rect.height(),
            placement.width_ratio, placement.rotation,
        )
        self.update()
        event.accept()

    def _hit_test(self, point: QPointF, photo_rect) -> int:
        for index in range(len(self.placements) - 1, -1, -1):
            placement = self.placements[index]
            half_width = photo_rect.width() * placement.width_ratio / 2
            half_height = half_width * self._sticker_aspect(placement.asset)
            center = QPointF(photo_rect.left() + photo_rect.width() * placement.center_x,
                             photo_rect.top() + photo_rect.height() * placement.center_y)
            delta = point - center
            angle = math.radians(-placement.rotation)
            local_x = delta.x() * math.cos(angle) - delta.y() * math.sin(angle)
            local_y = delta.x() * math.sin(angle) + delta.y() * math.cos(angle)
            if abs(local_x) <= half_width and abs(local_y) <= half_height:
                return index
        return -1

    def _sticker_aspect(self, asset: StickerAsset) -> float:
        pixmap = self._pixmaps.get(asset.path)
        if pixmap is None:
            image = load_sticker(asset.path)
            pixmap = QPixmap.fromImage(image) if not image.isNull() else QPixmap()
            self._pixmaps[asset.path] = pixmap
        return pixmap.height() / pixmap.width() if not pixmap.isNull() else 1.0
