import unittest
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtWidgets import QApplication

from app.ui.widgets.dance_pose import generate_pose_sequence, stamp_dance_pose


class DancePoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sequence_has_requested_length_and_no_repeats_until_all_poses_used(self):
        sequence = generate_pose_sequence(12)

        self.assertEqual(len(sequence), 12)
        self.assertEqual(len(set(sequence)), 12)

    def test_long_sequences_repeat_only_after_the_first_complete_round(self):
        sequence = generate_pose_sequence(20)

        self.assertEqual(len(sequence), 20)
        self.assertEqual(len(set(sequence[:12])), 12)

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
