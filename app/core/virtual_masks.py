"""Chargement, détection du visage et incrustation de masques PNG transparents."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from ..paths import resource_path

log = logging.getLogger(__name__)

MASK_EXTENSIONS = {".png"}
DETECTION_WIDTH = 480
MAX_SLOW_PREVIEWS = 3
MAX_PREVIEW_SECONDS = 0.12
MAX_TRACK_MISSES = 2


@dataclass(frozen=True)
class MaskAsset:
    path: Path
    name: str
    image: np.ndarray
    anchor: str
    width_ratio: float
    anchor_y: float


def scan_masks(directories: list[Path]) -> list[MaskAsset]:
    """Charge les PNG transparents ; les fichiers utilisateur remplacent les défauts homonymes."""
    found: dict[str, MaskAsset] = {}
    for directory in directories:
        try:
            paths = sorted((path for path in directory.iterdir()
                            if path.is_file() and path.suffix.casefold() in MASK_EXTENSIONS
                            and not path.name.startswith((".", "_"))),
                           key=lambda path: path.name.casefold())
        except OSError:
            continue
        for path in paths:
            image = load_mask(path)
            if image is None:
                continue
            key = path.stem.casefold()
            found[key] = _describe(path, image)
    return sorted(found.values(), key=lambda asset: asset.name.casefold())


def load_mask(path: Path) -> np.ndarray | None:
    """Lit un PNG BGRA (y compris un nom avec accents sous Windows)."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None
    except (OSError, cv2.error):
        log.exception("Lecture du masque impossible : %s", path)
        return None
    if image is None or image.ndim != 3 or image.shape[2] != 4:
        log.warning("Masque ignoré : un PNG avec transparence est attendu (%s)", path)
        return None
    if image.dtype != np.uint8:
        image = cv2.convertScaleAbs(image, alpha=255.0 / np.iinfo(image.dtype).max)
    if not np.any(image[:, :, 3]):
        log.warning("Masque ignoré car il est entièrement transparent : %s", path)
        return None
    height, width = image.shape[:2]
    factor = min(1.0, 1200 / max(width, height))
    if factor < 1.0:
        image = cv2.resize(image, (round(width * factor), round(height * factor)),
                           interpolation=cv2.INTER_AREA)
    return image


def _describe(path: Path, image: np.ndarray) -> MaskAsset:
    key = path.stem.casefold()
    prefix = key.split("_", 1)[0].split("-", 1)[0]
    if prefix == "yeux":
        return MaskAsset(path, _display_name(path), image, "eyes", 1.12, 0.40)
    if prefix == "bouche":
        return MaskAsset(path, _display_name(path), image, "mouth", 0.72, 0.70)
    if prefix == "nez":
        return MaskAsset(path, _display_name(path), image, "nose", 0.34, 0.56)
    if prefix == "oreille":
        # Le PNG représente une seule oreille ; le rendu en crée une paire miroir.
        return MaskAsset(path, _display_name(path), image, "ears", 0.25, 0.58)
    if prefix == "cheveux":
        return MaskAsset(path, _display_name(path), image, "top", 1.20, 0.08)
    if any(word in key for word in ("lunette", "glasses", "goggle")):
        return MaskAsset(path, _display_name(path), image, "eyes", 1.12, 0.40)
    if any(word in key for word in ("moustache", "mustache", "moust")):
        return MaskAsset(path, _display_name(path), image, "mouth", 0.72, 0.70)
    if any(word in key for word in ("couronne", "crown", "chapeau", "hat")):
        return MaskAsset(path, _display_name(path), image, "top", 1.0, 0.08)
    # Anciens fichiers de paire d'oreilles, dont le PNG fourni avec l'application.
    if any(word in key for word in ("oreilles", "ears", "lapin", "bunny")):
        return MaskAsset(path, _display_name(path), image, "top", 0.92, 0.12)
    return MaskAsset(path, _display_name(path), image, "center", 1.08, 0.50)


def _display_name(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").strip().capitalize()


class FaceMaskRenderer:
    """Détecte plusieurs visages à petite résolution et lisse leurs boîtes dans le temps."""

    def __init__(self, asset: MaskAsset) -> None:
        # Certains wheels OpenCV (et certaines installations existantes) ne
        # livrent pas cv2/data. Le projet embarque donc sa copie du classificateur.
        cascade_path = resource_path("assets/haarcascade_frontalface_default.xml")
        if not cascade_path.is_file():
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self._detector = cv2.CascadeClassifier(str(cascade_path))
        if self._detector.empty():
            raise RuntimeError(f"Classificateur de visages introuvable : {cascade_path}")
        self.asset = asset
        self._lock = threading.Lock()
        self._tracks: list[tuple[np.ndarray, int]] = []
        self._slow_count = 0
        self._disabled = False
        self._last_face_count = 0

    @property
    def disabled(self) -> bool:
        return self._disabled

    @property
    def last_face_count(self) -> int:
        return self._last_face_count

    def process_preview(self, source: np.ndarray, rendered: np.ndarray) -> np.ndarray:
        """Incruste sur l'aperçu déjà rendu (décor/cadre), depuis l'image caméra non transformée."""
        if self._disabled:
            return rendered
        started = time.perf_counter()
        try:
            with self._lock:
                boxes = self._detect(source)
                smoothed = self._smooth_tracks(boxes)
                out = apply_mask(rendered, self.asset, smoothed)
            elapsed = time.perf_counter() - started
            if elapsed > MAX_PREVIEW_SECONDS:
                self._slow_count += 1
            else:
                self._slow_count = 0
            self._last_face_count = len(smoothed)
            if self._slow_count >= MAX_SLOW_PREVIEWS:
                self._disabled = True
                log.warning("Masque virtuel désactivé : détection trop lente (%.0f ms)", elapsed * 1000)
                return rendered
            return out
        except Exception:
            self._disabled = True
            log.exception("Masque virtuel désactivé après une erreur de détection/incrustation")
            return rendered

    def apply_photo(self, source: np.ndarray, rendered: np.ndarray) -> np.ndarray:
        """Incruste sur une photo finale ; cette détection ne réutilise pas une ancienne position."""
        if self._disabled:
            return rendered
        try:
            with self._lock:
                boxes = self._detect(source)
            self._last_face_count = len(boxes)
            return apply_mask(rendered, self.asset, boxes)
        except Exception:
            log.exception("Masque non appliqué à la photo finale")
            return rendered

    def _detect(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        height, width = image.shape[:2]
        scale = min(1.0, DETECTION_WIDTH / width)
        small = cv2.resize(image, (round(width * scale), round(height * scale)),
                           interpolation=cv2.INTER_AREA) if scale < 1.0 else image
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        detections = self._detector.detectMultiScale(
            gray, scaleFactor=1.12, minNeighbors=5, minSize=(36, 36),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        factor = 1.0 / scale
        boxes = [np.array((round(x * factor), round(y * factor), round(w * factor), round(h * factor)),
                          dtype=np.float32) for x, y, w, h in detections]
        return [tuple(int(value) for value in box) for box in boxes]

    def _smooth_tracks(self, detections: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
        old_tracks = self._tracks
        used: set[int] = set()
        new_tracks: list[tuple[np.ndarray, int]] = []
        output: list[tuple[int, int, int, int]] = []
        for detection in detections:
            current = np.asarray(detection, dtype=np.float32)
            match = max((( _iou(current, old), index, old, missed)
                         for index, (old, missed) in enumerate(old_tracks) if index not in used),
                        default=(0.0, -1, None, 0), key=lambda item: item[0])
            overlap, index, previous, _missed = match
            if index >= 0 and overlap >= 0.12:
                used.add(index)
                current = previous * 0.62 + current * 0.38
            new_tracks.append((current, 0))
            output.append(tuple(int(round(value)) for value in current))
        for index, (previous, missed) in enumerate(old_tracks):
            if index not in used and missed < MAX_TRACK_MISSES:
                retained = (previous, missed + 1)
                new_tracks.append(retained)
                output.append(tuple(int(round(value)) for value in previous))
        self._tracks = new_tracks
        return output


def _iou(first: np.ndarray, second: np.ndarray) -> float:
    ax1, ay1, aw, ah = first
    bx1, by1, bw, bh = second
    x1, y1 = max(ax1, bx1), max(ay1, by1)
    x2, y2 = min(ax1 + aw, bx1 + bw), min(ay1 + ah, by1 + bh)
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - intersection
    return float(intersection / union) if union > 0 else 0.0


def apply_mask(image: np.ndarray, asset: MaskAsset,
               faces: list[tuple[int, int, int, int]]) -> np.ndarray:
    """Redimensionne et alpha-compose le masque pour chacun des visages détectés."""
    result = image.copy()
    mask_h, mask_w = asset.image.shape[:2]
    for x, y, face_w, face_h in faces:
        if face_w <= 0 or face_h <= 0:
            continue
        target_w = max(1, round(face_w * asset.width_ratio))
        target_h = max(1, round(target_w * mask_h / mask_w))
        if asset.anchor == "ears":
            center_y = y + round(face_h * asset.anchor_y)
            left = x - round(face_w * 0.025) - target_w // 2
            right = x + face_w + round(face_w * 0.025) - target_w // 2
            _blend_bgra(result, asset.image, left, center_y - target_h // 2, target_w, target_h)
            mirrored = cv2.flip(asset.image, 1)
            _blend_bgra(result, mirrored, right, center_y - target_h // 2, target_w, target_h)
            continue
        if asset.anchor == "eyes":
            center_y = y + round(face_h * asset.anchor_y)
            top = center_y - target_h // 2
        elif asset.anchor == "mouth":
            center_y = y + round(face_h * asset.anchor_y)
            top = center_y - target_h // 2
        elif asset.anchor == "nose":
            center_y = y + round(face_h * asset.anchor_y)
            top = center_y - target_h // 2
        elif asset.anchor == "top":
            top = y - target_h + round(face_h * asset.anchor_y)
        else:
            top = y + round(face_h * asset.anchor_y) - target_h // 2
        left = x + face_w // 2 - target_w // 2
        _blend_bgra(result, asset.image, left, top, target_w, target_h)
    return result


def _blend_bgra(canvas: np.ndarray, overlay: np.ndarray, x: int, y: int,
                width: int, height: int) -> None:
    canvas_h, canvas_w = canvas.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(canvas_w, x + width), min(canvas_h, y + height)
    if x1 >= x2 or y1 >= y2:
        return
    source_alpha = overlay[:, :, 3].astype(np.float32) / 255.0
    premultiplied = overlay[:, :, :3].astype(np.float32) * source_alpha[:, :, None]
    interpolation = cv2.INTER_AREA if width < overlay.shape[1] else cv2.INTER_LINEAR
    alpha = cv2.resize(source_alpha, (width, height), interpolation=interpolation)
    foreground = cv2.resize(premultiplied, (width, height), interpolation=interpolation)
    alpha = alpha[y1 - y:y2 - y, x1 - x:x2 - x, None]
    foreground = foreground[y1 - y:y2 - y, x1 - x:x2 - x]
    background = canvas[y1:y2, x1:x2].astype(np.float32)
    canvas[y1:y2, x1:x2] = np.clip(background * (1.0 - alpha) + foreground, 0, 255).astype(np.uint8)
