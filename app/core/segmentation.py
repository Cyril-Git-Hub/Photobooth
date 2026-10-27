"""Détourage des invités.

Un `Segmenter` renvoie un masque float32 de la taille de l'image : 1 = personne, 0 = fond,
déjà adouci et prêt à être mélangé avec le décor. Deux implémentations :
- AiSegmenter : segmentation de personnes par IA (MediaPipe), sans fond vert ;
- ChromaKeySegmenter : incrustation sur fond vert (OpenCV, HSV), avec suppression du halo vert.
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..config import Config
from .models import MODELS

log = logging.getLogger(__name__)

REFINE_LOW, REFINE_HIGH = 0.35, 0.65   # le masque est « durci » entre ces deux seuils
MIN_PERSON_AREA = 0.015     # une zone « personne » plus petite que 1,5 % de l'image est un parasite
MAX_HOLE_AREA = 0.12        # un trou entouré par la personne, jusqu'à 12 % de l'image...
HOLE_MIN_CONFIDENCE = 0.15  # ...est comblé s'il est incertain (vêtement proche du fond), pas s'il est sûr (jour entre bras et corps)
GUIDE_EPS = 1e-3            # plus petit = contours collés de plus près à ceux de l'image

_HAS_GUIDED_FILTER = hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "guidedFilter")

MSG_MODEL_MISSING = ("Modèle de détourage introuvable :\n{path}\n"
                     "Lance « python tools\\telecharger_modele.py » (une seule fois, avec internet), "
                     "ou choisis mode_detourage = fond_vert dans config.ini.")
MSG_MEDIAPIPE_MISSING = "MediaPipe n'est pas installé.\nLance : pip install -r requirements.txt"
MSG_MODEL_INVALID = "Le modèle de détourage est illisible :\n{error}\nRetélécharge-le : python tools\\telecharger_modele.py --force"


class SegmentationError(RuntimeError):
    """Détourage impossible ; le message est destiné à être affiché à l'écran."""


def refine_mask(mask: np.ndarray, low: float = REFINE_LOW, high: float = REFINE_HIGH) -> np.ndarray:
    """Courbe « smoothstep » : écrase les valeurs douteuses vers 0 ou 1 pour des contours nets."""
    t = np.clip((mask - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def clean_coarse(coarse: np.ndarray) -> np.ndarray:
    """Nettoie le masque à la résolution du modèle (rapide, ~1 ms).

    - supprime les petits îlots « personne » isolés dans le fond (on garde toujours la plus grande zone) ;
    - comble les trous entourés par la personne quand le modèle y hésite (vêtement de la couleur du mur),
      mais pas les jours francs (entre un bras et le corps), où le modèle est sûr qu'il s'agit du fond.
    """
    height, width = coarse.shape
    area = height * width
    count, labels, stats, _ = cv2.connectedComponentsWithStats((coarse > 0.5).astype(np.uint8), connectivity=8)
    keep_lut = np.zeros(count, np.uint8)
    if count > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep_lut[1:] = areas >= MIN_PERSON_AREA * area
        keep_lut[1 + int(np.argmax(areas))] = 1
    keep = keep_lut[labels]
    out = coarse * cv2.dilate(keep, np.ones((3, 3), np.uint8), iterations=2)

    hole_count, hole_labels, hole_stats, _ = cv2.connectedComponentsWithStats(
        (1 - keep).astype(np.uint8), connectivity=4)
    x, y, w, h, hole_area = (hole_stats[:, i] for i in range(5))
    enclosed = (x > 0) & (y > 0) & (x + w < width) & (y + h < height)      # ne touche pas le bord de l'image
    mean_confidence = np.bincount(hole_labels.ravel(), weights=coarse.ravel(), minlength=hole_count) / np.maximum(hole_area, 1)
    fill = enclosed & (hole_area <= MAX_HOLE_AREA * area) & (mean_confidence >= HOLE_MIN_CONFIDENCE)
    fill[0] = False                                                           # l'étiquette 0 est la personne
    out[fill[hole_labels]] = 1.0
    return out


def refine_coarse_mask(frame_bgr: np.ndarray, coarse: np.ndarray, guided: bool = True) -> np.ndarray:
    """Masque du modèle (basse résolution) -> masque net à la taille de l'image.

    Le modèle travaille en 256 px de large : agrandi tel quel, son masque a des bords en marches d'escalier.
    Le filtre guidé recolle ces bords sur les vrais contours de l'image (cheveux, épaules, vêtements).
    `guided=False` reproduit l'ancienne méthode (agrandissement simple), pour comparer.
    """
    height, width = frame_bgr.shape[:2]
    if not guided:
        upscaled = cv2.resize(coarse, (width, height), interpolation=cv2.INTER_LINEAR)
        return cv2.GaussianBlur(refine_mask(np.clip(upscaled, 0.0, 1.0), 0.3, 0.7), (5, 5), 0)
    upscaled = cv2.resize(clean_coarse(coarse), (width, height), interpolation=cv2.INTER_LINEAR)
    if _HAS_GUIDED_FILTER:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        radius = max(3, round(width / 160))
        upscaled = cv2.ximgproc.guidedFilter(gray, upscaled, radius, GUIDE_EPS)
        return refine_mask(np.clip(upscaled, 0.0, 1.0))
    return cv2.GaussianBlur(refine_mask(np.clip(upscaled, 0.0, 1.0)), (5, 5), 0)   # repli : opencv sans « contrib »


class Segmenter(ABC):
    @abstractmethod
    def segment(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Masque float32 (H, W) entre 0 et 1."""

    def clean_frame(self, frame_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Retouche éventuelle de l'image avant mélange (suppression du halo vert)."""
        return frame_bgr

    def close(self) -> None:
        pass


# ---------------------------------------------------------------- IA

class AiSegmenter(Segmenter):
    def __init__(self, model_path: Path, input_size: tuple[int, int] = (256, 144),
                 invert: bool = False, guided: bool = True) -> None:
        if not model_path.is_file():
            raise SegmentationError(MSG_MODEL_MISSING.format(path=model_path))
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as exc:
            raise SegmentationError(MSG_MEDIAPIPE_MISSING) from exc

        self._mp = mp
        self._input_size = input_size
        self._invert = invert
        self._guided = guided
        self._lock = threading.Lock()   # aperçu (thread caméra) et photo (interface) partagent le modèle
        self._diagnosed = False
        if guided and not _HAS_GUIDED_FILTER:
            log.warning("opencv sans le module « contrib » : contours moins précis (installe opencv-contrib-python)")
        # buffer plutôt que chemin : le chargement par chemin échoue avec certains caractères accentués
        options = vision.ImageSegmenterOptions(
            base_options=mp_python.BaseOptions(model_asset_buffer=model_path.read_bytes()),
            running_mode=vision.RunningMode.IMAGE,
            output_confidence_masks=True,
            output_category_mask=False,
        )
        try:
            self._segmenter = vision.ImageSegmenter.create_from_options(options)
        except Exception as exc:
            raise SegmentationError(MSG_MODEL_INVALID.format(error=exc)) from exc
        log.info("Détourage IA prêt (%s, entrée %dx%d)", model_path.name, *input_size)

    def segment(self, frame_bgr: np.ndarray) -> np.ndarray:
        # On donne au modèle exactement la taille qu'il attend (réduction soignée, INTER_AREA) : il n'a plus
        # rien à redimensionner, et le masque n'est agrandi qu'une fois, avec le filtre guidé.
        small = cv2.resize(frame_bgr, self._input_size, interpolation=cv2.INTER_AREA)
        rgb = np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        with self._lock:
            result = self._segmenter.segment(mp_image)
            masks = result.confidence_masks
            if not masks:
                raise SegmentationError("Le modèle n'a renvoyé aucun masque.")
            if len(masks) >= 3:          # multiclasse : 0 = fond, le reste = parties de la personne
                coarse = 1.0 - np.array(masks[0].numpy_view(), dtype=np.float32)
            elif len(masks) == 2:        # selfie_segmenter : fond = 0 et personne = 1
                coarse = np.array(masks[1].numpy_view(), dtype=np.float32)
            else:
                coarse = np.array(masks[0].numpy_view(), dtype=np.float32)   # copie : la vue appartient à MediaPipe
        if coarse.ndim == 3:
            coarse = coarse[:, :, 0]
        if self._invert:
            coarse = 1.0 - coarse
        coarse = np.clip(coarse, 0.0, 1.0)
        if not self._diagnosed:
            self._diagnosed = True
            log.info("Détourage IA : %d masque(s), part de personne dans l'image = %.2f", len(masks), float(coarse.mean()))
        return refine_coarse_mask(frame_bgr, coarse, self._guided)

    def close(self) -> None:
        with self._lock:
            self._segmenter.close()


# ---------------------------------------------------------------- fond vert

@dataclass(frozen=True)
class ChromaParams:
    teinte_min: int = 35
    teinte_max: int = 85
    saturation_min: int = 70
    valeur_min: int = 40
    adoucissement: int = 2
    despill: bool = True

    @classmethod
    def from_config(cls, config: Config) -> "ChromaParams":
        return cls(config.fv_teinte_min, config.fv_teinte_max, config.fv_saturation_min,
                   config.fv_valeur_min, config.fv_adoucissement, config.fv_despill)


_K3 = np.ones((3, 3), np.uint8)
_K5 = np.ones((5, 5), np.uint8)


class ChromaKeySegmenter(Segmenter):
    def __init__(self, params: ChromaParams) -> None:
        self.params = params

    def segment(self, frame_bgr: np.ndarray) -> np.ndarray:
        p = self.params
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        backdrop = cv2.inRange(hsv, (p.teinte_min, p.saturation_min, p.valeur_min), (p.teinte_max, 255, 255))
        # Les ombres et les plis peuvent laisser de petits trous dans le fond détecté.
        # Les refermer avant l'inversion évite que ces points isolés soient gardés comme sujet.
        backdrop = cv2.morphologyEx(backdrop, cv2.MORPH_CLOSE, _K5)
        person = cv2.bitwise_not(backdrop)
        person = cv2.morphologyEx(person, cv2.MORPH_OPEN, _K3)    # grains isolés dans le fond
        person = cv2.morphologyEx(person, cv2.MORPH_CLOSE, _K5)   # petits trous dans la personne
        if p.adoucissement > 0:
            size = 2 * p.adoucissement + 1
            person = cv2.GaussianBlur(person, (size, size), 0)
        return person.astype(np.float32) / 255.0

    def clean_frame(self, frame_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Despill : sur le contour uniquement, le vert ne dépasse pas max(bleu, rouge)."""
        if not self.params.despill:
            return frame_bgr
        edge = ((mask > 0.02) & (mask < 0.98)).astype(np.uint8)
        edge = cv2.dilate(edge, _K5, iterations=2) > 0
        blue, green, red = cv2.split(frame_bgr)
        limit = np.maximum(blue, red)
        fixed = np.where(edge & (green > limit), limit, green).astype(np.uint8)
        return cv2.merge((blue, fixed, red))


# ---------------------------------------------------------------- choix du mode

def segmenter_key(config: Config) -> tuple:
    """Change dès qu'un réglage influençant le détourage change (pour recréer le segmenteur)."""
    if config.mode_detourage == "fond_vert":
        return ("fond_vert", ChromaParams.from_config(config))
    return ("ia", config.ia_modele, str(config.fichier_modele_ia), config.ia_inverser_masque)


def create_segmenter(config: Config) -> Segmenter:
    if config.mode_detourage == "fond_vert":
        return ChromaKeySegmenter(ChromaParams.from_config(config))
    return AiSegmenter(config.fichier_modele_ia, MODELS[config.ia_modele].input_size, config.ia_inverser_masque)
