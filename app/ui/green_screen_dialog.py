"""Calibration visuelle des seuils de détourage sur la webcam."""
from __future__ import annotations

import logging
import time

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QScroller, QSlider, QVBoxLayout, QWidget,
)

from ..core.compositor import blend
from ..core.segmentation import ChromaKeySegmenter, ChromaParams
from ..config import DEFAULTS
from ..core.qt_image import bgr_to_qimage
from .scale import px

log = logging.getLogger(__name__)
CALIBRATION_PREVIEW_WIDTH = 480
CALIBRATION_PREVIEW_INTERVAL_S = 0.12


class ClickablePreview(QLabel):
    """Image de webcam cliquable, en conservant son cadrage lors du redimensionnement."""

    def __init__(self, clicked, parent=None) -> None:
        super().__init__(parent)
        self._clicked = clicked
        self._source: QImage | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(px(220), px(160))
        self.setStyleSheet(f"background: #17152a; border: {px(1)}px solid #777;")
        self.setText("Démarrage de la webcam…")

    def set_image(self, image: QImage) -> None:
        self._source = image
        self._refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._source is not None:
            self.setPixmap(QPixmap.fromImage(self._source).scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def mousePressEvent(self, event) -> None:
        if self._source is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return
        left = (self.width() - pixmap.width()) / 2
        top = (self.height() - pixmap.height()) / 2
        x = event.position().x() - left
        y = event.position().y() - top
        if 0 <= x < pixmap.width() and 0 <= y < pixmap.height():
            sx = self._source.width() / pixmap.width()
            sy = self._source.height() / pixmap.height()
            self._clicked(round(x * sx), round(y * sy))


class GreenScreenCalibrationDialog(QDialog):
    def __init__(self, window, parent=None) -> None:
        super().__init__(parent or window)
        self._window = window
        self._camera = window.camera
        self._frame: np.ndarray | None = None
        self._last_preview_at = 0.0
        self._samples: list[tuple[int, int, int]] = []
        self.setWindowTitle("Calibrer le fond vert")
        screen = window.screen()
        available = screen.availableGeometry() if screen else None
        available_width = available.width() if available else px(1280)
        available_height = available.height() if available else px(800)
        self.setMinimumSize(min(px(760), max(320, available_width - px(32))),
                            min(px(480), max(300, available_height - px(32))))
        self.resize(min(px(1180), int(available_width * 0.94)),
                    min(px(860), int(available_height * 0.92)))

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(px(8), px(8), px(8), px(8))
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        content = QWidget()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel(
            "Clique sur plusieurs zones du tissu vert (plis, ombres et zones éclairées). Ajuste ensuite les seuils jusqu’à ce que "
            "le masque soit blanc sur le fond et noir sur les personnes."
        ))

        previews = QGridLayout()
        self._source_preview = ClickablePreview(self._sample_at)
        self._mask_preview = QLabel("Masque (blanc = fond détouré)")
        self._result_preview = QLabel("Incrustation de contrôle")
        for label in (self._mask_preview, self._result_preview):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumSize(px(200), px(150))
            label.setStyleSheet(f"background: #17152a; border: {px(1)}px solid #777;")
        previews.addLayout(self._captioned("Webcam — cliquer sur le fond vert", self._source_preview), 0, 0)
        previews.addLayout(self._captioned("Masque — blanc = fond", self._mask_preview), 0, 1)
        previews.addLayout(self._captioned("Contrôle — magenta = zone détourée", self._result_preview), 0, 2)
        layout.addLayout(previews, 1)

        settings = QGridLayout()
        self._hue_min, self._hue_max = self._slider_pair(settings, 0, "Teinte min / max", 0, 179,
                                                         window.config.fv_teinte_min,
                                                         window.config.fv_teinte_max)
        self._saturation = self._single_slider(settings, 1, "Saturation minimale", 0, 255,
                                               window.config.fv_saturation_min)
        self._value = self._single_slider(settings, 2, "Luminosité minimale", 0, 255,
                                          window.config.fv_valeur_min)
        layout.addLayout(settings)
        self._sample_status = QLabel("Aucune couleur échantillonnée.")
        layout.addWidget(self._sample_status)

        actions = QHBoxLayout()
        reset = QPushButton("Valeurs par défaut")
        reset.setMinimumHeight(px(56))
        reset.clicked.connect(self._reset_defaults)
        actions.addWidget(reset)
        clear_samples = QPushButton("Effacer les échantillons")
        clear_samples.setMinimumHeight(px(56))
        clear_samples.clicked.connect(self._clear_samples)
        actions.addWidget(clear_samples)
        actions.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        buttons.button(QDialogButtonBox.StandardButton.Save).setMinimumSize(px(140), px(56))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setMinimumSize(px(140), px(56))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        actions.addWidget(buttons)
        layout.addLayout(actions)

        self._hue_min.valueChanged.connect(self._on_hue_min_changed)
        self._saturation.valueChanged.connect(self._refresh_previews)
        self._value.valueChanged.connect(self._refresh_previews)
        self._hue_max.valueChanged.connect(self._on_hue_max_changed)
        self._camera.preview_ready.connect(self._on_preview)
        self._camera.failed.connect(self._on_camera_failed)
        self._camera.set_preview_processor(None)
        self._camera.set_preview_enabled(True)
        self._camera.start_camera()

    @staticmethod
    def _captioned(title: str, widget: QLabel) -> QVBoxLayout:
        box = QVBoxLayout()
        caption = QLabel(title)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(caption)
        box.addWidget(widget, 1)
        return box

    def _slider_pair(self, layout, row, title, minimum, maximum, low, high):
        label = QLabel(title)
        low_slider = QSlider(Qt.Orientation.Horizontal)
        high_slider = QSlider(Qt.Orientation.Horizontal)
        for slider, value in ((low_slider, low), (high_slider, high)):
            slider.setRange(minimum, maximum)
            slider.setValue(value)
            self._prepare_touch_slider(slider)
            slider.setMinimumWidth(px(150))
        numbers = QLabel()
        self._hue_numbers = numbers if row == 0 else None
        def update_numbers(*_):
            numbers.setText(f"{low_slider.value()} – {high_slider.value()}")
        low_slider.valueChanged.connect(update_numbers)
        high_slider.valueChanged.connect(update_numbers)
        update_numbers()
        layout.addWidget(label, row, 0)
        layout.addWidget(low_slider, row, 1)
        layout.addWidget(high_slider, row, 2)
        layout.addWidget(numbers, row, 3)
        return low_slider, high_slider

    def _single_slider(self, layout, row, title, minimum, maximum, value):
        label = QLabel(title)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        self._prepare_touch_slider(slider)
        number = QLabel(str(value))
        slider.valueChanged.connect(number.setNum)
        layout.addWidget(label, row, 0)
        layout.addWidget(slider, row, 1, 1, 2)
        layout.addWidget(number, row, 3)
        return slider

    @staticmethod
    def _prepare_touch_slider(slider: QSlider) -> None:
        slider.setMinimumHeight(px(48))
        slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: {px(8)}px; }} "
            f"QSlider::handle:horizontal {{ width: {px(32)}px; margin: -{px(12)}px 0; }}"
        )

    def _params(self) -> ChromaParams:
        return ChromaParams(self._hue_min.value(), self._hue_max.value(), self._saturation.value(),
                            self._value.value(), self._window.config.fv_adoucissement,
                            self._window.config.fv_despill)

    def _on_hue_min_changed(self, value: int) -> None:
        self._hue_max.setMinimum(value)
        self._refresh_previews()

    def _on_hue_max_changed(self, value: int) -> None:
        self._hue_min.setMaximum(value)
        self._refresh_previews()

    def _set_hue_range(self, minimum: int, maximum: int) -> None:
        minimum, maximum = max(0, min(179, minimum)), max(0, min(179, maximum))
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        low_blocked = self._hue_min.blockSignals(True)
        high_blocked = self._hue_max.blockSignals(True)
        self._hue_min.setRange(0, 179)
        self._hue_max.setRange(0, 179)
        self._hue_min.setValue(minimum)
        self._hue_max.setValue(maximum)
        self._hue_min.setMaximum(maximum)
        self._hue_max.setMinimum(minimum)
        self._hue_min.blockSignals(low_blocked)
        self._hue_max.blockSignals(high_blocked)
        self._hue_numbers.setText(f"{minimum} – {maximum}")
        self._refresh_previews()

    def _sample_at(self, x: int, y: int) -> None:
        if self._frame is None:
            return
        hsv = cv2.cvtColor(self._frame, cv2.COLOR_BGR2HSV)
        radius = 5
        patch = hsv[max(0, y-radius):y+radius+1, max(0, x-radius):x+radius+1]
        if patch.size == 0:
            return
        # Un seul point ne représente pas un tissu plissé et inégalement éclairé.
        # On cumule les médianes des petites zones cliquées pour apprendre sa variation réelle.
        sample = tuple(int(np.median(patch[:, :, channel])) for channel in range(3))
        self._samples.append(sample)
        hues = [value[0] for value in self._samples]
        saturations = [value[1] for value in self._samples]
        brightness = [value[2] for value in self._samples]
        hue_margin = 12
        self._set_hue_range(min(hues) - hue_margin, max(hues) + hue_margin)
        saturation_reference = int(np.percentile(saturations, 25))
        saturation_minimum = max(0, saturation_reference - 8)
        self._saturation.setValue(saturation_minimum)
        self._value.setValue(max(0, min(brightness) - 40))
        low_saturation_note = (
            " La webcam capte ce tissu avec très peu de saturation ; un seuil proche de 0 est alors nécessaire."
            if saturation_reference <= 8 else ""
        )
        self._sample_status.setText(
            f"{len(self._samples)} zone(s) échantillonnée(s) · saturation mesurée {saturation_reference}/255 · "
            f"seuil proposé {saturation_minimum}/255. Ajoute des points dans les zones d’ombre et de lumière."
            f"{low_saturation_note}"
        )

    def _clear_samples(self) -> None:
        self._samples.clear()
        self._sample_status.setText("Échantillons effacés. Clique sur plusieurs zones du tissu pour le recalibrer.")

    def _on_preview(self, image: QImage) -> None:
        remaining = CALIBRATION_PREVIEW_INTERVAL_S - (time.monotonic() - self._last_preview_at)
        if remaining > 0:
            # Laisser le drapeau d'aperçu occupé jusqu'au prochain rafraîchissement évite
            # de convertir et retraiter des images que l'interface ne pourrait pas afficher.
            QTimer.singleShot(max(1, round(remaining * 1000)), self._camera.preview_consumed)
            return
        try:
            rgb = image.convertToFormat(QImage.Format.Format_RGB888)
            pointer = rgb.bits()
            pointer.setsize(rgb.sizeInBytes())
            raw = np.frombuffer(pointer, dtype=np.uint8).reshape(rgb.height(), rgb.bytesPerLine())
            frame = cv2.cvtColor(raw[:, :rgb.width() * 3].reshape(rgb.height(), rgb.width(), 3), cv2.COLOR_RGB2BGR)
            scale = min(1.0, CALIBRATION_PREVIEW_WIDTH / frame.shape[1])
            if scale < 1.0:
                frame = cv2.resize(frame, (CALIBRATION_PREVIEW_WIDTH,
                                           max(1, round(frame.shape[0] * scale))),
                                   interpolation=cv2.INTER_AREA)
            self._frame = frame
            self._source_preview.set_image(bgr_to_qimage(frame))
            self._last_preview_at = time.monotonic()
            self._refresh_previews()
        except Exception:
            log.exception("Mise à jour de l'aperçu de calibration impossible")
        finally:
            self._camera.preview_consumed()

    def _refresh_previews(self, *_args) -> None:
        if self._frame is None:
            return
        mask = ChromaKeySegmenter(self._params()).segment(self._frame)
        backdrop = (mask < 0.5).astype(np.uint8) * 255
        mask_image = cv2.cvtColor(backdrop, cv2.COLOR_GRAY2BGR)
        self._mask_preview.setPixmap(QPixmap.fromImage(bgr_to_qimage(mask_image)).scaled(
            self._mask_preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        control_background = np.full_like(self._frame, (180, 0, 180))
        composite = blend(self._frame, mask, control_background)
        self._result_preview.setPixmap(QPixmap.fromImage(bgr_to_qimage(composite)).scaled(
            self._result_preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _reset_defaults(self) -> None:
        self._samples.clear()
        defaults = DEFAULTS["fond_vert"]
        self._set_hue_range(int(defaults["teinte_min"]), int(defaults["teinte_max"]))
        self._saturation.setValue(int(defaults["saturation_min"]))
        self._value.setValue(int(defaults["valeur_min"]))
        self._sample_status.setText("Valeurs par défaut restaurées (elles seront appliquées à l’enregistrement).")

    def _save(self) -> None:
        if self._hue_min.value() > self._hue_max.value():
            QMessageBox.warning(self, "Réglages invalides", "La teinte minimale doit être inférieure à la teinte maximale.")
            return
        try:
            self._window.config.save_chroma_settings(self._hue_min.value(), self._hue_max.value(),
                                                     self._saturation.value(), self._value.value())
            self._window.close_segmenter()
        except (OSError, ValueError) as exc:
            log.exception("Enregistrement des seuils du fond vert impossible")
            QMessageBox.warning(self, "Enregistrement impossible", f"Les seuils n’ont pas été enregistrés :\n{exc}")
            return
        self.accept()

    def _on_camera_failed(self, message: str) -> None:
        self._source_preview.setText(message)
        self._sample_status.setText("Caméra indisponible : vérifie qu’elle n’est pas utilisée par une autre application.")

    def done(self, result: int) -> None:
        self._camera.set_preview_enabled(False)
        self._camera.set_preview_processor(None)
        self._camera.stop_camera()
        try:
            self._camera.preview_ready.disconnect(self._on_preview)
        except TypeError:
            pass
        try:
            self._camera.failed.disconnect(self._on_camera_failed)
        except TypeError:
            pass
        super().done(result)
