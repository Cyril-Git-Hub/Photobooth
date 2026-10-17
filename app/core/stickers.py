"""Chargement et composition des autocollants de photo."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PyQt6.QtGui import QImage, QImageReader, QPainter
from PyQt6.QtSvg import QSvgRenderer

from ..config import Config
from ..paths import resource_path

log = logging.getLogger(__name__)
SUPPORTED = {".png", ".webp", ".jpg", ".jpeg", ".svg"}


@dataclass(frozen=True)
class StickerAsset:
    name: str
    path: Path


@dataclass(frozen=True)
class StickerPlacement:
    asset: StickerAsset
    center_x: float = 0.5
    center_y: float = 0.5
    width_ratio: float = 0.18
    rotation: float = 0.0


def _valid(path: Path) -> bool:
    if path.suffix.casefold() == ".svg":
        return QSvgRenderer(str(path)).isValid()
    reader = QImageReader(str(path))
    reader.setDecideFormatFromContent(True)
    return reader.canRead()


def list_stickers(config: Config) -> list[StickerAsset]:
    """Charge les autocollants fournis et ceux ajoutés par l'organisateur."""
    paths = (resource_path("assets/autocollants"), config.base_dir / "autocollants")
    found: dict[str, StickerAsset] = {}
    paths[1].mkdir(parents=True, exist_ok=True)
    for folder in paths:
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
            if not path.is_file() or path.suffix.casefold() not in SUPPORTED:
                continue
            if not _valid(path):
                log.warning("Autocollant ignoré (fichier illisible) : %s", path)
                continue
            found[path.stem.casefold()] = StickerAsset(path.stem.replace("_", " "), path)
    return list(found.values())


def load_sticker(path: Path, size: int = 640) -> QImage:
    """Charge un autocollant en RGBA ; les SVG sont rasterisés à la taille demandée."""
    if path.suffix.casefold() == ".svg":
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            return QImage()
        source = renderer.defaultSize()
        if source.isEmpty():
            source = QSize(size, size)
        target = source.scaled(QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio)
        image = QImage(target, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        return image
    reader = QImageReader(str(path))
    reader.setDecideFormatFromContent(True)
    image = reader.read()
    if image.isNull():
        return image
    return image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def apply_stickers(image_bgr: np.ndarray, placements: list[StickerPlacement]) -> np.ndarray:
    """Compose les autocollants sur une image BGR pleine résolution."""
    if not placements:
        return image_bgr
    height, width = image_bgr.shape[:2]
    source = QImage(image_bgr.data, width, height, image_bgr.strides[0], QImage.Format.Format_BGR888)
    image = source.copy().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    cache: dict[Path, QImage] = {}
    for placement in placements:
        sticker = cache.get(placement.asset.path)
        if sticker is None:
            sticker = load_sticker(placement.asset.path, size=max(width, height))
            cache[placement.asset.path] = sticker
        if sticker.isNull():
            log.warning("Autocollant ignoré lors de la composition : %s", placement.asset.path)
            continue
        sticker_width = max(1, round(width * placement.width_ratio))
        sticker_height = max(1, round(sticker.height() * sticker_width / sticker.width()))
        center_x = round(width * placement.center_x)
        center_y = round(height * placement.center_y)
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(placement.rotation)
        painter.drawImage(-sticker_width // 2, -sticker_height // 2,
                          sticker.scaled(sticker_width, sticker_height,
                                         Qt.AspectRatioMode.IgnoreAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
        painter.restore()
    painter.end()
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    decoded = cv2.imdecode(np.frombuffer(bytes(encoded), dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("Impossible de composer les autocollants sur la photo")
    return decoded
