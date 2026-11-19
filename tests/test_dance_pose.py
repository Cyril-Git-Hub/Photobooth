import unittest
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

from app.ui.widgets.dance_pose import (
    draw_dance_pose, generate_pose_sequence, stamp_dance_pose,
)
from app.ui.widgets.preview_widget import PreviewWidget


class DancePoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sequence_has_requested_length_and_no_repeats_until_all_poses_used(self):
        sequence = generate_pose_sequence(12)

        self.assertEqual(len(sequence), 12)
        self.assertEqual(len(set(sequence)), 12)

    def test_long_sequences_repeat_only_after_the_first_complete_round(self):
        sequence = generate_pose_sequence(24)

        self.assertEqual(len(sequence), 24)
        self.assertEqual(len(set(sequence[:20])), 20)

    def test_all_twenty_poses_render_as_distinct_figures(self):
        rendered = set()
        for pose_index in range(20):
            image = QImage(160, 160, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            draw_dance_pose(painter, QRectF(0, 0, 160, 160), pose_index)
            painter.end()
            pixels = image.bits()
            pixels.setsize(image.sizeInBytes())
            rendered.add(bytes(pixels))

        self.assertEqual(len(rendered), 20)

    def test_pose_is_rendered_on_a_light_background(self):
        image = QImage(160, 160, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        draw_dance_pose(painter, QRectF(0, 0, 160, 160), 0)
        painter.end()

        self.assertEqual(image.pixelColor(80, 10).name(), "#f4f6ef")

    def test_pose_remains_prominent_in_capture_overlay_dimensions(self):
        image = QImage(200, 140, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        draw_dance_pose(painter, QRectF(20, 10, 160, 100), 0)
        painter.end()

        dark_pixels = sum(
            image.pixelColor(x, y).red() < 40
            for y in range(image.height())
            for x in range(image.width())
        )
        self.assertGreater(dark_pixels, 1000)

    def test_live_preview_stores_the_active_pose_for_its_paint_event(self):
        preview = PreviewWidget()
        preview.resize(800, 450)
        preview.set_dance_pose(7, 3, 5)

        self.assertEqual(preview._dance_pose, 7)
        self.assertEqual((preview._dance_step, preview._dance_total), (3, 5))

    def test_live_preview_paints_the_figure_inside_its_pose_card(self):
        preview = PreviewWidget()
        preview.resize(800, 450)
        preview.set_dance_pose(0, 1, 5)
        image = QImage(800, 450, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        preview._paint_dance_pose(painter)
        painter.end()

        self.assertLess(image.pixelColor(668, 103).red(), 40)

    def test_non_positive_count_returns_empty_sequence(self):
        self.assertEqual(generate_pose_sequence(0), [])
        self.assertEqual(generate_pose_sequence(-1), [])

    def test_stamp_dance_pose_adds_visible_overlay_without_changing_frame_size(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)

        result = stamp_dance_pose(frame, 3, 2, 5)

        self.assertEqual(result.shape, frame.shape)
        self.assertGreater(np.count_nonzero(result), 0)


if __name__ == "__main__":
    unittest.main()
