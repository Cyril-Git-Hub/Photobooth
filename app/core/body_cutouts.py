"""Segmentation sémantique et pose pour supprimer des parties du corps."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from .models import AUXILIARY_MODELS

log = logging.getLogger(__name__)

POSE_MODEL_FILENAME = AUXILIARY_MODELS["pose"].filename
BODY_PARTS_MODEL_FILENAME = AUXILIARY_MODELS["corps"].filename
BODY_CUTOUTS = frozenset({
    "jambe_gauche", "jambe_droite", "bras_gauche", "bras_droit",
    "sous_taille", "tete", "haut_corps",
})
POSE_DETECTION_WIDTH = 640
MIN_LANDMARK_VISIBILITY = 0.35
PARSING_INPUT_SIZE = 192
PARSING_REFRESH_SECONDS = 0.08
PARSING_LABELS = {
    "skirt": 5,
    "pants": 6,
    "dress": 7,
    "left_shoe": 9,
    "right_shoe": 10,
    "face": 11,
    "left_leg": 12,
    "right_leg": 13,
    "left_arm": 14,
    "right_arm": 15,
    "hair": 2,
    "hat": 1,
    "sunglasses": 3,
    "upper_clothes": 4,
    "belt": 8,
    "scarf": 17,
}
PARSING_DEBUG_CLASSES = (
    (PARSING_LABELS["pants"], (255, 0, 255), "pantalon"),
    (PARSING_LABELS["left_leg"], (255, 180, 0), "jambes"),
    (PARSING_LABELS["right_leg"], (255, 180, 0), "jambes"),
    (PARSING_LABELS["left_shoe"], (0, 255, 255), "chaussures"),
    (PARSING_LABELS["right_shoe"], (0, 255, 255), "chaussures"),
    (PARSING_LABELS["upper_clothes"], (255, 0, 0), "haut"),
    (PARSING_LABELS["scarf"], (0, 0, 255), "écharpe"),
)
_PARSING_INPUT_MEAN = np.array((0.485, 0.456, 0.406), dtype=np.float32)
_PARSING_INPUT_STD = np.array((0.229, 0.224, 0.225), dtype=np.float32)


class BodyCutoutError(RuntimeError):
    """Erreur de chargement du modèle de repérage corporel."""


def _point(landmarks, index: int, width: int, height: int) -> np.ndarray | None:
    landmark = landmarks[index]
    if min(float(getattr(landmark, "visibility", 1.0)),
           float(getattr(landmark, "presence", 1.0))) < MIN_LANDMARK_VISIBILITY:
        return None
    x, y = float(landmark.x), float(landmark.y)
    if not np.isfinite((x, y)).all() or not (-0.1 <= x <= 1.1 and -0.1 <= y <= 1.1):
        return None
    return np.array((x * width, y * height), dtype=np.float32)


def _capsule(mask: np.ndarray, start: np.ndarray, end: np.ndarray, radius: float) -> None:
    first = tuple(np.round(start).astype(int))
    last = tuple(np.round(end).astype(int))
    thickness = max(1, round(radius * 2))
    cv2.line(mask, first, last, 255, thickness, cv2.LINE_AA)
    cv2.circle(mask, first, max(1, round(radius)), 255, -1, cv2.LINE_AA)
    cv2.circle(mask, last, max(1, round(radius)), 255, -1, cv2.LINE_AA)


def _limb(
    mask: np.ndarray,
    landmarks,
    indices: tuple[int, ...],
    width: int,
    height: int,
    radius: float,
) -> None:
    points = [_point(landmarks, index, width, height) for index in indices]
    for index, (start, end) in enumerate(zip(points, points[1:])):
        if start is not None and end is not None:
            _capsule(mask, start, end, radius * (0.9 ** index))


def _waist_y(landmarks, width: int, height: int) -> float | None:
    hips = [_point(landmarks, index, width, height) for index in (23, 24)]
    if any(point is None for point in hips):
        return None
    return float((hips[0][1] + hips[1][1]) / 2)


def build_body_cutout_mask(
    shape: tuple[int, ...],
    landmarks,
    parts: frozenset[str] | set[str],
) -> np.ndarray:
    """Retourne un masque alpha (1 = garder la personne, 0 = révéler le décor)."""
    height, width = shape[:2]
    hidden = np.zeros((height, width), dtype=np.uint8)
    if len(landmarks) < 33:
        return np.ones((height, width), dtype=np.float32)

    shoulder_points = [_point(landmarks, index, width, height) for index in (11, 12)]
    hip_points = [_point(landmarks, index, width, height) for index in (23, 24)]
    shoulder_span = (float(np.linalg.norm(shoulder_points[0] - shoulder_points[1]))
                     if all(point is not None for point in shoulder_points) else width * 0.12)
    hip_span = (float(np.linalg.norm(hip_points[0] - hip_points[1]))
                if all(point is not None for point in hip_points) else shoulder_span * 0.55)

    if "bras_gauche" in parts:
        _limb(hidden, landmarks, (11, 13, 15), width, height, max(3.0, shoulder_span * 0.105))
    if "bras_droit" in parts:
        _limb(hidden, landmarks, (12, 14, 16), width, height, max(3.0, shoulder_span * 0.105))
    leg_radius = min(max(5.0, hip_span * 0.42), min(width, height) * 0.12)
    if "jambe_gauche" in parts or "sous_taille" in parts:
        _limb(hidden, landmarks, (23, 25, 27, 31), width, height, leg_radius)
    if "jambe_droite" in parts or "sous_taille" in parts:
        _limb(hidden, landmarks, (24, 26, 28, 32), width, height, leg_radius)
    if "sous_taille" in parts and all(point is not None for point in hip_points):
        first = tuple(np.round(hip_points[0]).astype(int))
        last = tuple(np.round(hip_points[1]).astype(int))
        cv2.line(
            hidden, first, last, 255,
            max(1, round(leg_radius * 2.2)), cv2.LINE_AA,
        )

    if "haut_corps" in parts:
        waist_y = _waist_y(landmarks, width, height)
        if waist_y is not None:
            boundary = int(np.clip(round(waist_y), 0, height))
            hidden[:boundary, :] = 255

    if "tete" in parts:
        nose = _point(landmarks, 0, width, height)
        ears = [_point(landmarks, index, width, height) for index in (7, 8)]
        if nose is not None and all(point is not None for point in ears):
            ear_center = (ears[0] + ears[1]) / 2
            ear_span = float(np.linalg.norm(ears[0] - ears[1]))
            center = np.array((ear_center[0], (ear_center[1] + nose[1]) / 2), dtype=np.float32)
            head_width = max(ear_span * 1.65, shoulder_span * 0.34, 8.0)
            head_height = max(head_width * 1.55, float(abs(nose[1] - ear_center[1])) * 2.2)
            cv2.ellipse(
                hidden, tuple(np.round(center).astype(int)),
                (max(1, round(head_width / 2)), max(1, round(head_height / 2))),
                0, 0, 360, 255, -1, cv2.LINE_AA,
            )

    if not np.any(hidden):
        return np.ones((height, width), dtype=np.float32)
    sigma = max(1.0, min(width, height) / 800)
    hidden = cv2.GaussianBlur(hidden, (0, 0), sigmaX=sigma)
    return 1.0 - hidden.astype(np.float32) / 255.0


def build_body_part_mask(
    shape: tuple[int, ...],
    labels: np.ndarray,
    parts: frozenset[str] | set[str],
    landmarks=None,
) -> np.ndarray:
    """Construit le masque de retrait depuis la segmentation sémantique et, si disponible, la pose."""
    height, width = shape[:2]
    if labels.shape != (height, width):
        raise ValueError(f"Taille de segmentation incompatible : {labels.shape} != {(height, width)}")
    hidden = np.zeros((height, width), dtype=np.uint8)
    part_ids: set[int] = set()
    if "sous_taille" in parts:
        part_ids.update((
            PARSING_LABELS["pants"], PARSING_LABELS["left_shoe"],
            PARSING_LABELS["right_shoe"], PARSING_LABELS["left_leg"],
            PARSING_LABELS["right_leg"],
        ))
    if "jambe_gauche" in parts:
        part_ids.update((PARSING_LABELS["left_leg"], PARSING_LABELS["left_shoe"]))
    if "jambe_droite" in parts:
        part_ids.update((PARSING_LABELS["right_leg"], PARSING_LABELS["right_shoe"]))
    if "bras_gauche" in parts:
        part_ids.add(PARSING_LABELS["left_arm"])
    if "bras_droit" in parts:
        part_ids.add(PARSING_LABELS["right_arm"])
    if "tete" in parts:
        part_ids.update((PARSING_LABELS["hat"], PARSING_LABELS["hair"],
                         PARSING_LABELS["sunglasses"], PARSING_LABELS["face"]))
    if "haut_corps" in parts:
        part_ids.update((PARSING_LABELS["hat"], PARSING_LABELS["hair"],
                         PARSING_LABELS["sunglasses"], PARSING_LABELS["upper_clothes"],
                         PARSING_LABELS["belt"], PARSING_LABELS["face"],
                         PARSING_LABELS["left_arm"], PARSING_LABELS["right_arm"],
                         PARSING_LABELS["scarf"]))
    hidden[np.isin(labels, tuple(part_ids))] = 255

    pose_mask = None
    if landmarks is not None:
        leg_parts = parts & {"jambe_gauche", "jambe_droite"}
        arm_parts = parts & {"bras_gauche", "bras_droit"}
        if "sous_taille" in parts:
            pose_mask = build_body_cutout_mask(shape, landmarks, {"sous_taille"})
            hidden = np.maximum(
                hidden, np.round((1.0 - pose_mask) * 255).astype(np.uint8))
        elif leg_parts or arm_parts:
            pose_mask = build_body_cutout_mask(shape, landmarks, parts)
        if leg_parts and pose_mask is not None:
            hidden[(labels == PARSING_LABELS["pants"]) & (pose_mask < 0.5)] = 255
        if arm_parts and pose_mask is not None:
            hidden[(labels == PARSING_LABELS["upper_clothes"]) & (pose_mask < 0.5)] = 255

    if not np.any(hidden):
        return np.ones((height, width), dtype=np.float32)
    sigma = max(1.0, min(width, height) / 800)
    hidden = cv2.GaussianBlur(hidden, (0, 0), sigmaX=sigma)
    return 1.0 - hidden.astype(np.float32) / 255.0


class BodyCutoutRenderer:
    """Segmente vêtements et parties du corps, puis les retire du masque de personne."""

    def __init__(
        self,
        model_path: Path,
        parts: frozenset[str],
        pose_model_path: Path | None = None,
    ) -> None:
        if not model_path.is_file():
            raise BodyCutoutError(
                f"Modèle de segmentation corporelle absent : {model_path}. "
                "Lance « python tools\\telecharger_modele.py corps » avant la soirée.")
        if not parts or not parts <= BODY_CUTOUTS:
            raise ValueError(f"Parties du corps inconnues : {sorted(parts - BODY_CUTOUTS)}")
        try:
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            self._session = ort.InferenceSession(
                str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
            self._input_name = self._session.get_inputs()[0].name
        except ImportError as exc:
            raise BodyCutoutError(
                "onnxruntime n'est pas installé. Lance « pip install -r requirements.txt ».") from exc
        except Exception as exc:
            raise BodyCutoutError(f"Impossible de charger le modèle corporel : {exc}") from exc

        self._mp = None
        self._landmarker = None
        pose_required = bool(parts & {
            "jambe_gauche", "jambe_droite", "bras_gauche", "bras_droit", "sous_taille",
        })
        if pose_required and pose_model_path is not None and pose_model_path.is_file():
            try:
                import mediapipe as mp
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision

                pose_options = vision.PoseLandmarkerOptions(
                    base_options=mp_python.BaseOptions(
                        model_asset_buffer=pose_model_path.read_bytes()),
                    running_mode=vision.RunningMode.IMAGE,
                    num_poses=1,
                    min_pose_detection_confidence=0.35,
                    min_pose_presence_confidence=0.35,
                )
                self._mp = mp
                self._landmarker = vision.PoseLandmarker.create_from_options(pose_options)
            except ImportError as exc:
                self._session = None
                raise BodyCutoutError("MediaPipe n'est pas installé.") from exc
            except Exception as exc:
                self._session = None
                raise BodyCutoutError(f"Impossible de charger le modèle de pose : {exc}") from exc
        elif pose_required:
            log.warning("Modèle de pose absent : seules les classes segmentées seront masquées.")
        self._parts = parts
        self._lock = threading.Lock()
        self._pose_lock = threading.Lock()
        self._onnx_lock = threading.Lock()
        self._last_labels: np.ndarray | None = None
        self._last_landmarks = None
        self._last_labels_shape: tuple[int, int] | None = None
        self._last_inference = 0.0

    def _infer_parts(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        resized = cv2.resize(
            frame, (PARSING_INPUT_SIZE, PARSING_INPUT_SIZE), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = np.ascontiguousarray(
            ((rgb - _PARSING_INPUT_MEAN) / _PARSING_INPUT_STD).transpose(2, 0, 1)[None])
        try:
            with self._onnx_lock:
                outputs = self._session.run(None, {self._input_name: tensor})
                logits = outputs[0]
                if logits.ndim != 4 or logits.shape[1] != 18:
                    raise BodyCutoutError(
                        "Le modèle de segmentation a renvoyé un résultat inattendu.")
                logits = logits[0].transpose(1, 2, 0)
                logits = cv2.resize(logits, (width, height), interpolation=cv2.INTER_LINEAR)
                return np.argmax(logits, axis=2).astype(np.uint8)
        except Exception as exc:
            if isinstance(exc, BodyCutoutError):
                raise
            raise BodyCutoutError(f"Échec de la segmentation des parties du corps : {exc}") from exc

    def _infer_parts_and_pose(
        self, frame: np.ndarray,
    ) -> tuple[np.ndarray, object | None]:
        return self._infer_parts(frame), self._pose_landmarks(frame)

    def _segment_parts_preview(self, frame: np.ndarray) -> tuple[np.ndarray, object | None]:
        height, width = frame.shape[:2]
        with self._lock:
            now = time.monotonic()
            if (self._last_labels is not None
                    and self._last_labels_shape == (height, width)
                    and now - self._last_inference < PARSING_REFRESH_SECONDS):
                return self._last_labels, self._last_landmarks
            labels, landmarks = self._infer_parts_and_pose(frame)
            self._last_labels = labels
            self._last_landmarks = landmarks
            self._last_labels_shape = (height, width)
            self._last_inference = time.monotonic()
            return labels, landmarks

    def _segment_parts_photo(
        self, frame: np.ndarray,
    ) -> tuple[np.ndarray, object | None]:
        with self._lock:
            labels, landmarks = self._infer_parts_and_pose(frame)
            self._last_labels = labels
            self._last_landmarks = landmarks
            self._last_labels_shape = frame.shape[:2]
            self._last_inference = time.monotonic()
        return labels, landmarks

    def _pose_landmarks(self, frame: np.ndarray):
        if self._landmarker is None:
            return None
        height, width = frame.shape[:2]
        scale = min(1.0, POSE_DETECTION_WIDTH / width)
        detection_frame = (cv2.resize(
            frame, (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA) if scale < 1 else frame)
        rgb = np.ascontiguousarray(cv2.cvtColor(detection_frame, cv2.COLOR_BGR2RGB))
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        try:
            with self._pose_lock:
                result = self._landmarker.detect(mp_image)
        except Exception as exc:
            raise BodyCutoutError(f"Échec du repérage des articulations : {exc}") from exc
        return result.pose_landmarks[0] if result.pose_landmarks else None

    def _apply_labels(
        self,
        frame: np.ndarray,
        person_mask: np.ndarray,
        labels: np.ndarray,
        landmarks,
    ) -> np.ndarray:
        if person_mask.shape != frame.shape[:2]:
            raise ValueError(
                f"Tailles incompatibles : image {frame.shape}, masque {person_mask.shape}")
        keep_mask = build_body_part_mask(frame.shape, labels, self._parts, landmarks)
        removed = float(np.sum(person_mask * (1.0 - keep_mask)))
        person_area = float(np.sum(person_mask))
        if person_area > 0 and removed / person_area > 0.65:
            log.warning("Effet de disparition ignoré : la segmentation masquerait presque toute la personne.")
            return person_mask
        return person_mask * keep_mask

    def apply_to_mask_preview(self, frame: np.ndarray, person_mask: np.ndarray) -> np.ndarray:
        if person_mask.shape != frame.shape[:2]:
            raise ValueError(
                f"Tailles incompatibles : image {frame.shape}, masque {person_mask.shape}")
        result = self._segment_parts_preview(frame)
        return self._apply_labels(frame, person_mask, result[0], result[1])

    def apply_to_mask(self, frame: np.ndarray, person_mask: np.ndarray) -> np.ndarray:
        if person_mask.shape != frame.shape[:2]:
            raise ValueError(
                f"Tailles incompatibles : image {frame.shape}, masque {person_mask.shape}")
        labels, landmarks = self._segment_parts_photo(frame)
        return self._apply_labels(frame, person_mask, labels, landmarks)

    def render_parsing_debug_preview(self, frame: np.ndarray) -> np.ndarray:
        labels, _ = self._segment_parts_preview(frame)
        output = frame.copy()
        for class_id, color, _ in PARSING_DEBUG_CLASSES:
            selected = labels == class_id
            output[selected] = (
                frame[selected].astype(np.float32) * 0.35
                + np.asarray(color, dtype=np.float32) * 0.65
            ).astype(np.uint8)

        legend = (
            ("Pantalon", (255, 0, 255)),
            ("Jambes", (255, 180, 0)),
            ("Chaussures", (0, 255, 255)),
            ("Haut", (255, 0, 0)),
            ("Echarpe", (0, 0, 255)),
        )
        x, y = 12, 24
        for name, color in legend:
            cv2.rectangle(output, (x, y - 11), (x + 12, y + 1), color, -1)
            cv2.putText(
                output, name, (x + 17, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (255, 255, 255), 1, cv2.LINE_AA,
            )
            x += 105
        return output

    def close(self) -> None:
        with self._pose_lock:
            if self._landmarker is not None:
                self._landmarker.close()
                self._landmarker = None
        self._session = None
