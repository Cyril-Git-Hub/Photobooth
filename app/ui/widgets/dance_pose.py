"""Silhouettes vectorielles pour les poses du défi Just Dance."""
from __future__ import annotations

import math
import random

import cv2
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ...core.qt_image import bgr_to_qimage
from ..scale import px

# Angles des bras (épaule, coude) et des jambes (hanche, genou), en degrés.
_POSES = (
    (205, 230, 155, 130, -18, -8, 18, 8),
    (120, 155, -120, -155, -28, -10, 12, 24),
    (250, 220, 110, 140, -8, -24, 28, 12),
    (170, 205, -70, -35, -24, -4, 8, 24),
    (90, 120, 270, 240, -12, -28, 18, 32),
    (225, 180, -45, 0, -30, -12, 10, 28),
    (135, 95, 225, 265, -5, -24, 30, 12),
    (180, 145, 0, 35, -22, -2, 22, 38),
    (235, 265, 45, 15, -32, -18, 5, 25),
    (80, 45, 200, 235, -15, -35, 25, 5),
    (155, 190, 25, -10, -5, -20, 32, 18),
    (260, 230, 100, 130, -26, -40, 20, 36),
    (80, 115, -80, -45, -35, -20, 18, 42),
    (210, 175, 150, 185, -42, -12, 12, 40),
    (135, 175, -135, -95, 10, -24, 42, 18),
    (285, 250, 65, 110, -18, -35, 38, 4),
    (175, 125, -5, 55, -50, -20, 8, 36),
)


def generate_pose_sequence(count: int) -> list[int]:
    """Génère un ordre aléatoire de poses sans répétition avant épuisement."""
    if count <= 0:
        return []
    sequence: list[int] = []
    while len(sequence) < count:
        batch = random.sample(range(len(_POSES)), len(_POSES))
        sequence.extend(batch[:count - len(sequence)])
    return sequence


def _point(origin: tuple[float, float], angle: float, length: float) -> tuple[float, float]:
    radians = math.radians(angle)
    return origin[0] + math.sin(radians) * length, origin[1] + math.cos(radians) * length


def draw_dance_pose(painter: QPainter, rect: QRectF, pose_index: int) -> None:
    """Dessine un personnage en silhouette, centré dans le rectangle fourni."""
    if not _POSES:
        return
    scale = min(rect.width(), rect.height()) * 0.88
    if scale <= 0:
        return
    pose = _POSES[pose_index % len(_POSES)]
    origin_x = rect.center().x()
    origin_y = rect.center().y() - scale * 0.43

    def mapped(point: tuple[float, float]):
        return (origin_x + point[0] * scale, origin_y + point[1] * scale)

    def limb(start: tuple[float, float], first_angle: float, second_angle: float,
             first_length: float, second_length: float) -> None:
        elbow = _point(start, first_angle, first_length)
        hand_or_foot = _point(elbow, second_angle, second_length)
        painter.drawLine(QPointF(*mapped(start)), QPointF(*mapped(elbow)))
        painter.drawLine(QPointF(*mapped(elbow)), QPointF(*mapped(hand_or_foot)))
        for joint in (elbow, hand_or_foot):
            x, y = mapped(joint)
            painter.drawEllipse(QRectF(x - scale * 0.025, y - scale * 0.025,
                                       scale * 0.05, scale * 0.05))

    shoulder_left = (-0.12, 0.31)
    shoulder_right = (0.12, 0.31)
    hip_left = (-0.055, 0.58)
    hip_right = (0.055, 0.58)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    outline = max(1, int(scale * 0.09))
    painter.setPen(QPen(QColor("#15152c"), outline,
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
    limbs = ((shoulder_left, pose[0:2]), (shoulder_right, pose[2:4]),
             (hip_left, pose[4:6]), (hip_right, pose[6:8]))
    for start, angles in limbs:
        limb(start, angles[0], angles[1], 0.17, 0.18)
    painter.setPen(QPen(QColor("#4de8ff"), max(1, int(scale * 0.065)),
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for start, angles in limbs:
        elbow = _point(start, angles[0], 0.17)
        end = _point(elbow, angles[1], 0.18)
        painter.drawLine(QPointF(*mapped(start)), QPointF(*mapped(elbow)))
        painter.drawLine(QPointF(*mapped(elbow)), QPointF(*mapped(end)))
    painter.setPen(QPen(QColor("#ff4fa3"), max(1, int(scale * 0.08)),
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(*mapped((0.0, 0.29))), QPointF(*mapped((0.0, 0.58))))
    head_x, head_y = mapped((0.0, 0.17))
    head_size = scale * 0.17
    painter.setBrush(QColor("#ffd166"))
    painter.drawEllipse(QRectF(head_x - head_size / 2, head_y - head_size / 2,
                               head_size, head_size))
    painter.restore()


def stamp_dance_pose(frame: np.ndarray, pose_index: int, step: int, total: int) -> np.ndarray:
    """Ajoute la silhouette de référence dans le coin supérieur droit d'une image GIF."""
    image = bgr_to_qimage(frame)
    height, width = frame.shape[:2]
    side = max(1, round(min(width, height) * 0.34))
    margin = max(8, round(min(width, height) * 0.025))
    card = QRectF(width - margin - side, margin, side, side)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(18, 16, 42, 225))
    painter.setPen(QPen(QColor("#ffd166"), max(2, round(side * 0.018))))
    painter.drawRoundedRect(card, side * 0.07, side * 0.07)
    draw_dance_pose(painter, card.adjusted(side * 0.08, side * 0.04,
                                           -side * 0.08, -side * 0.23), pose_index)
    painter.end()

    rgb_image = image.convertToFormat(QImage.Format.Format_RGB888)
    pixels = rgb_image.constBits()
    pixels.setsize(rgb_image.sizeInBytes())
    rgb = np.frombuffer(pixels, dtype=np.uint8).reshape(
        (height, rgb_image.bytesPerLine()))[:, :width * 3].reshape((height, width, 3))
    stamped = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    label = f"POSE {step}/{total}"
    font_scale = max(0.35, side / 390)
    thickness = max(1, round(side / 100))
    (label_width, _), _ = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    label_x = round(card.center().x() - label_width / 2)
    label_y = round(card.bottom() - side * 0.07)
    cv2.putText(stamped, label, (label_x, label_y), cv2.FONT_HERSHEY_SIMPLEX,
                font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
    return stamped


class DancePoseWidget(QWidget):
    def __init__(self, pose_index: int, parent=None) -> None:
        super().__init__(parent)
        self.pose_index = pose_index
        self.setMinimumSize(px(90), px(110))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        draw_dance_pose(painter, QRectF(self.rect()), self.pose_index)
        painter.end()
