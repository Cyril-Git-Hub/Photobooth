"""Incrustation d'accessoires photo à partir des repères du corps."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from .accessory_config import AccessoryPlacement, AccessorySpec
from .models import AUXILIARY_MODELS

log = logging.getLogger(__name__)

POSE_MODEL_FILENAME = AUXILIARY_MODELS["pose"].filename
HAND_MODEL_FILENAME = AUXILIARY_MODELS["main"].filename
MIN_LANDMARK_VISIBILITY = 0.35


class AccessoryError(RuntimeError):
    """Erreur de chargement du modèle ou de l'accessoire."""


def _arm_points(landmarks, width: int, height: int):
    """Choisit le bras le plus visible pour associer son poignet à une main détectée."""
    candidates = []
    for shoulder_index, elbow_index, wrist_index in ((11, 13, 15), (12, 14, 16)):
        shoulder, elbow, wrist = (landmarks[index] for index in
                                  (shoulder_index, elbow_index, wrist_index))
        confidence = min(float(getattr(point, "visibility", 1.0))
                         for point in (shoulder, elbow, wrist))
        if confidence < MIN_LANDMARK_VISIBILITY:
            continue
        shoulder_xy = np.array((shoulder.x * width, shoulder.y * height), dtype=np.float32)
        elbow_xy = np.array((elbow.x * width, elbow.y * height), dtype=np.float32)
        wrist_xy = np.array((wrist.x * width, wrist.y * height), dtype=np.float32)
        forearm = wrist_xy - elbow_xy
        forearm_length = float(np.linalg.norm(forearm))
        if forearm_length < max(8.0, width * 0.01):
            continue
        upper_arm = shoulder_xy - elbow_xy
        upper_length = float(np.linalg.norm(upper_arm))
        if upper_length <= 0:
            continue
        straightness = (1.0 - float(np.dot(upper_arm, forearm) /
                                    (upper_length * forearm_length))) / 2.0
        score = confidence * (0.55 + 0.45 * straightness)
        candidates.append((score, wrist_xy, forearm_length, forearm / forearm_length))
    if not candidates:
        return None
    _, wrist, forearm_length, forearm_direction = max(candidates, key=lambda item: item[0])
    return wrist, forearm_length, forearm_direction


def _match_hand_to_pose(hand_landmarks, pose_landmarks, width: int, height: int):
    """Associe la main détectée au poignet de pose le plus fiable."""
    if not hand_landmarks:
        return None, None
    arm = _arm_points(pose_landmarks, width, height) if pose_landmarks else None
    if arm is None:
        return hand_landmarks[0], None
    wrist, forearm_length, forearm_direction = arm
    selected = min(
        hand_landmarks,
        key=lambda points: float(np.linalg.norm(
            np.array((points[0].x * width, points[0].y * height), dtype=np.float32) - wrist)),
    )
    return selected, (forearm_length, forearm_direction)


def _hand_mask(
    shape: tuple[int, ...],
    hand_points: np.ndarray,
) -> np.ndarray | None:
    """Construit un masque adouci depuis les 21 repères du Hand Landmarker."""
    if hand_points.shape[0] != 21:
        return None
    points = np.round(hand_points).astype(np.int32)
    hull = cv2.convexHull(points.reshape(-1, 1, 2))
    if len(hull) < 3 or cv2.contourArea(hull) < 4:
        return None
    height, width = shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(mask, hull, 255)
    palm_width = float(np.linalg.norm(hand_points[5] - hand_points[17]))
    radius = max(1, round(palm_width * 0.08))
    kernel_size = radius * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    mask = cv2.dilate(mask, kernel)
    return cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1.0, radius / 2)).astype(np.float32) / 255.0


def place_accessory(
    image: np.ndarray,
    accessory: np.ndarray,
    hand_landmarks,
    placement: AccessoryPlacement,
    forearm_length: float | None = None,
    forearm_direction: np.ndarray | None = None,
) -> np.ndarray:
    """Place un PNG à partir des 21 repères détaillés d'une main détectée."""
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"Image BGR attendue, reçu : {image.shape}")
    if accessory.ndim != 3 or accessory.shape[2] != 4:
        raise ValueError(f"Accessoire BGRA attendu, reçu : {accessory.shape}")
    if len(hand_landmarks) != 21:
        return image

    height, width = image.shape[:2]
    points = np.array(
        [(point.x * width, point.y * height) for point in hand_landmarks],
        dtype=np.float32,
    )
    wrist = points[0]
    palm_center = np.mean(points[[5, 9, 13, 17]], axis=0)
    hand_axis = points[9] - wrist
    hand_length = float(np.linalg.norm(hand_axis))
    palm_width = float(np.linalg.norm(points[5] - points[17]))
    if hand_length < 2 or palm_width < 2:
        return image
    hand_direction = hand_axis / hand_length
    forearm_direction = forearm_direction if forearm_direction is not None else hand_direction
    target = palm_center if placement.body_anchor == "main" else wrist
    direction = {
        "axe_main": hand_direction,
        "axe_avant_bras": forearm_direction,
        "verticale": np.array((0.0, -1.0), dtype=np.float32),
        "horizontale": np.array((1.0, 0.0), dtype=np.float32),
    }[placement.orientation].copy()
    angle = np.deg2rad(placement.rotation_degrees)
    rotation = np.array(((np.cos(angle), -np.sin(angle)),
                         (np.sin(angle), np.cos(angle))), dtype=np.float32)
    direction = rotation @ direction
    if placement.direction == "vers_le_haut" and direction[1] > 0:
        direction *= -1
    reference_length = (palm_width if placement.size_reference == "main" else
                        forearm_length if forearm_length is not None else hand_length * 2.7)
    if reference_length <= 0:
        return image
    scale = reference_length * placement.size_ratio / accessory.shape[0]
    normal = np.array((-direction[1], direction[0]), dtype=np.float32)
    target = target + reference_length * (
        placement.offset[0] * normal + placement.offset[1] * direction)

    anchor_x = accessory.shape[1] * placement.image_anchor[0]
    anchor_y = accessory.shape[0] * placement.image_anchor[1]
    dx, dy = (float(value) for value in direction)
    transform = np.array((
        (-dy * scale, -dx * scale, 0.0),
        (dx * scale, -dy * scale, 0.0),
    ), dtype=np.float32)
    transform[:, 2] = target - transform[:, :2] @ np.array((anchor_x, anchor_y), dtype=np.float32)
    overlay = cv2.warpAffine(
        accessory, transform, (width, height),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0),
    )
    alpha = overlay[:, :, 3:4].astype(np.float32) / 255.0
    foreground = overlay[:, :, :3].astype(np.float32)
    output = np.clip(image.astype(np.float32) * (1.0 - alpha) + foreground * alpha,
                     0, 255).astype(np.uint8)
    if placement.hand_layer == "derriere":
        hand_mask = _hand_mask(image.shape, points)
        if hand_mask is not None:
            hand_mask = hand_mask[:, :, np.newaxis]
            output = np.clip(
                image.astype(np.float32) * hand_mask
                + output.astype(np.float32) * (1.0 - hand_mask),
                0, 255,
            ).astype(np.uint8)
    return output


class AccessoryRenderer:
    """Détecte la pose et les mains sur la photo puis y place l'accessoire."""

    def __init__(
        self,
        pose_model_path: Path,
        hand_model_path: Path,
        accessory_spec: AccessorySpec,
    ) -> None:
        if not pose_model_path.is_file():
            raise AccessoryError(
                f"Modèle de pose absent : {pose_model_path}. "
                "Lance « python tools\\telecharger_modele.py pose main » avant la soirée.")
        if not hand_model_path.is_file():
            raise AccessoryError(
                f"Modèle de détection des mains absent : {hand_model_path}. "
                "Lance « python tools\\telecharger_modele.py main » avant la soirée.")
        try:
            data = np.fromfile(str(accessory_spec.image), dtype=np.uint8)
            accessory = cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None
        except OSError as exc:
            raise AccessoryError(f"Lecture de l'accessoire impossible : {accessory_spec.image}") from exc
        except cv2.error as exc:
            raise AccessoryError(f"Décodage de l'accessoire impossible : {accessory_spec.image}") from exc
        if accessory is None or accessory.ndim != 3 or accessory.shape[2] != 4:
            raise AccessoryError(f"Accessoire PNG transparent illisible : {accessory_spec.image}")
        if not np.any(accessory[:, :, 3]):
            raise AccessoryError(f"Accessoire entièrement transparent : {accessory_spec.image}")
        self._accessory = accessory
        self._placement = accessory_spec.placement
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            pose_options = vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_buffer=pose_model_path.read_bytes()),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=0.35,
                min_pose_presence_confidence=0.35,
            )
            hand_options = vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_buffer=hand_model_path.read_bytes()),
                running_mode=vision.RunningMode.IMAGE,
                num_hands=2,
                min_hand_detection_confidence=0.35,
                min_hand_presence_confidence=0.35,
                min_tracking_confidence=0.35,
            )
            self._mp = mp
            self._pose_landmarker = vision.PoseLandmarker.create_from_options(pose_options)
            self._hand_landmarker = vision.HandLandmarker.create_from_options(hand_options)
        except ImportError as exc:
            raise AccessoryError("MediaPipe n'est pas installé.") from exc
        except Exception as exc:
            if hasattr(self, "_pose_landmarker"):
                self._pose_landmarker.close()
            raise AccessoryError(f"Impossible de charger le modèle de pose : {exc}") from exc

    def apply_photo(self, source: np.ndarray, rendered: np.ndarray) -> tuple[np.ndarray, bool]:
        if source.shape[:2] != rendered.shape[:2]:
            raise ValueError(f"Tailles incompatibles : source {source.shape}, rendu {rendered.shape}")
        rgb = np.ascontiguousarray(cv2.cvtColor(source, cv2.COLOR_BGR2RGB))
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        try:
            pose_result = self._pose_landmarker.detect(mp_image)
            hand_result = self._hand_landmarker.detect(mp_image)
        except Exception as exc:
            raise AccessoryError(f"Échec de la détection du corps ou des mains : {exc}") from exc
        if not hand_result.hand_landmarks:
            log.warning("Accessoire non appliqué : aucune main détectée sur la photo.")
            return rendered, False
        pose_landmarks = pose_result.pose_landmarks[0] if pose_result.pose_landmarks else None
        selected_hand, arm = _match_hand_to_pose(
            hand_result.hand_landmarks, pose_landmarks, source.shape[1], source.shape[0])
        forearm_length, forearm_direction = arm if arm is not None else (None, None)
        output = place_accessory(
            rendered, self._accessory, selected_hand, self._placement,
            forearm_length, forearm_direction)
        if output is rendered:
            log.warning("Accessoire non appliqué : main détectée trop petite ou invalide.")
            return rendered, False
        return output, True

    def close(self) -> None:
        self._pose_landmarker.close()
        self._hand_landmarker.close()
