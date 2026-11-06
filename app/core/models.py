"""Modèles de segmentation de personnes (MediaPipe) proposés pour le détourage IA."""
from __future__ import annotations

from dataclasses import dataclass

_BASE = "https://storage.googleapis.com/mediapipe-models/image_segmenter"


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    url: str
    input_size: tuple[int, int]   # (largeur, hauteur) attendues par le modèle
    description: str


@dataclass(frozen=True)
class DownloadSpec:
    filename: str
    url: str
    description: str


MODELS: dict[str, ModelSpec] = {
    "paysage": ModelSpec(
        "selfie_segmenter_landscape.tflite",
        f"{_BASE}/selfie_segmenter_landscape/float16/latest/selfie_segmenter_landscape.tflite",
        (256, 144), "léger, conçu pour le format 16/9 de la webcam (par défaut)"),
    "carre": ModelSpec(
        "selfie_segmenter.tflite",
        f"{_BASE}/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
        (256, 256), "léger, format carré"),
    "multiclasse": ModelSpec(
        "selfie_multiclass_256x256.tflite",
        f"{_BASE}/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite",
        (256, 256), "plus précis sur les vêtements et les cheveux, plus lent"),
}
MODEL_NAMES = tuple(MODELS)
DEFAULT_DOWNLOADS = ("paysage", "carre")   # petits fichiers, téléchargés par défaut

AUXILIARY_MODELS: dict[str, DownloadSpec] = {
    "pose": DownloadSpec(
        "pose_landmarker_lite.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        "repérage des articulations pour les accessoires photo"),
    "main": DownloadSpec(
        "hand_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
        "repérage détaillé des mains pour les accessoires photo"),
}
DOWNLOAD_MODELS = {**MODELS, **AUXILIARY_MODELS}
