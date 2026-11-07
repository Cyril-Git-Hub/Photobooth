"""Silhouettes pictogrammes pour les poses du défi Just Dance."""
from __future__ import annotations

import math
import random

import cv2
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ...core.qt_image import bgr_to_qimage
from ..scale import px

# Angle du bras gauche, pli du coude, bras droit, pli du coude,
# jambe gauche, pli du genou, jambe droite, pli du genou.
# 0° pointe vers le bas ; les angles positifs partent vers la droite.
_POSES = (
    (-145, 0, 145, 0, -12, 0, 12, 0),          # bras levés en V
    (-90, 0, 90, 0, -12, 0, 12, 0),            # bras ouverts
    (-155, 0, 70, -100, -12, 0, 12, 0),         # salut
    (-55, 105, 55, -105, -12, 0, 12, 0),        # coudes pliés
    (-120, 80, 120, -80, -12, 0, 12, 0),        # bras en diagonale
    (-155, 15, 20, 0, -20, 0, 20, 0),           # un bras en l'air
    (-20, 0, 155, -15, -12, 0, 12, 0),          # autre bras en l'air
    (-90, 90, 90, -90, -12, 0, 12, 0),          # bras repliés
    (-135, 85, 90, 0, -12, 0, 12, 0),           # un coude plié
    (-90, 0, 135, 85, -12, 0, 12, 0),           # l'autre coude plié
    (-155, 0, 90, -5, -12, 0, 12, 0),           # bras opposés
    (-90, 0, 155, 0, -35, 0, 35, 0),            # jambes écartées
    (-90, 0, 90, 0, -45, 70, 12, 0),            # pas de côté
    (-135, 35, 45, -35, -12, 0, 12, 0),         # bras en zigzag
    (-45, -90, 145, 0, -20, 0, 20, 0),          # mouvement asymétrique
    (-155, 0, 45, 0, -12, 0, 45, 65),           # un pied levé
    (-90, 70, 155, 0, -35, 0, 20, 0),           # pose déhanchée
    (-145, 50, 90, -65, -12, 0, 35, -70),       # pas dansant
    (-150, 0, 150, 0, -48, 65, 48, -65),        # saut, bras levés
    (-90, 0, 90, 0, -80, 0, 80, 0),             # allongé sur le côté
)
_JUMP_POSE = 18
_INK = QColor("#090909")
_GLASSES = QColor("#72d83b")
_GLASSES_HIGHLIGHT = QColor("#baff84")


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


def _draw_star(painter: QPainter, center: QPointF, radius: float) -> None:
    points = QPolygonF()
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        point_radius = radius if index % 2 == 0 else radius * 0.46
        points.append(QPointF(
            center.x() + math.cos(angle) * point_radius,
            center.y() + math.sin(angle) * point_radius,
        ))
    painter.setPen(QPen(_GLASSES_HIGHLIGHT, max(1, round(radius * 0.14))))
    painter.setBrush(_GLASSES)
    painter.drawPolygon(points)


def _draw_figure(painter: QPainter, pose: tuple[float, ...], scale: float) -> None:
    def mapped(point: tuple[float, float]) -> QPointF:
        return QPointF(point[0] * scale, point[1] * scale)

    def limb(start: tuple[float, float], angle: float, bend: float,
             first_length: float, second_length: float) -> tuple[QPointF, QPointF, QPointF]:
        elbow = _point(start, angle, first_length)
        end = _point(elbow, angle + bend, second_length)
        return mapped(start), mapped(elbow), mapped(end)

    shoulders = ((-0.13, -0.07), (0.13, -0.07))
    hips = ((-0.075, 0.28), (0.075, 0.28))
    arms = (
        limb(shoulders[0], pose[0], pose[1], 0.29, 0.24),
        limb(shoulders[1], pose[2], pose[3], 0.29, 0.24),
    )
    legs = (
        limb(hips[0], pose[4], pose[5], 0.31, 0.34),
        limb(hips[1], pose[6], pose[7], 0.31, 0.34),
    )

    painter.setPen(QPen(_INK, max(2, round(scale * 0.15)),
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
    for points in (*legs, *arms):
        painter.drawLine(points[0], points[1])
        painter.drawLine(points[1], points[2])

    torso = QPolygonF([
        mapped((-0.15, -0.10)), mapped((0.15, -0.10)),
        mapped((0.15, 0.30)), mapped((0.105, 0.36)),
        mapped((-0.105, 0.36)), mapped((-0.15, 0.30)),
    ])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_INK)
    painter.drawPolygon(torso)

    head_center = mapped((0, -0.27))
    head_radius = scale * 0.105
    painter.drawEllipse(
        QRectF(head_center.x() - head_radius, head_center.y() - head_radius,
               head_radius * 2, head_radius * 2))
    _draw_star(painter, mapped((-0.052, -0.28)), scale * 0.038)
    _draw_star(painter, mapped((0.052, -0.28)), scale * 0.038)
    painter.setPen(QPen(_GLASSES_HIGHLIGHT, max(1, round(scale * 0.012)),
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(mapped((-0.014, -0.28)), mapped((0.014, -0.28)))


def draw_dance_pose(painter: QPainter, rect: QRectF, pose_index: int) -> None:
    """Dessine un pictogramme contrasté sur un fond clair arrondi."""
    scale = min(rect.width(), rect.height()) * 0.62
    if scale <= 0:
        return
    pose_index %= len(_POSES)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    card_pen = QPen(QColor("#9dbb82"), max(1, round(scale * 0.025)))
    painter.setPen(card_pen)
    painter.setBrush(QColor("#f4f6ef"))
    painter.drawRoundedRect(rect.adjusted(
        card_pen.widthF() / 2, card_pen.widthF() / 2,
        -card_pen.widthF() / 2, -card_pen.widthF() / 2),
        scale * 0.12, scale * 0.12)
    painter.translate(rect.center())
    if pose_index == _JUMP_POSE:
        painter.translate(0, -scale * 0.045)
    _draw_figure(painter, _POSES[pose_index], scale)
    painter.restore()


def stamp_dance_pose(frame: np.ndarray, pose_index: int, step: int, total: int) -> np.ndarray:
    """Ajoute le pictogramme de la pose dans le coin supérieur droit d'une image GIF."""
    image = bgr_to_qimage(frame)
    height, width = frame.shape[:2]
    side = max(1, round(min(width, height) * 0.34))
    margin = max(8, round(min(width, height) * 0.025))
    card = QRectF(width - margin - side, margin, side, side)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(255, 255, 255, 235))
    painter.setPen(QPen(QColor("#72d83b"), max(2, round(side * 0.018))))
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
                font_scale, (20, 20, 20), thickness, cv2.LINE_AA)
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
