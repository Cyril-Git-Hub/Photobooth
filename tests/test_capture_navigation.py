import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.session import Session
from app.ui.screens.capture import CaptureScreen, State


class CaptureNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def make_capture_stub(challenge_type):
        return SimpleNamespace(
            session=SimpleNamespace(
                challenge_type=challenge_type,
                photo_format="gif",
                frame_mode=False,
            ),
            _planned_poses=lambda: 5,
            _state=State.READY,
            _back=Mock(),
            _frame_option=Mock(),
            _mask_option=Mock(),
            _frame_panel=Mock(),
            _mask_panel=Mock(),
            _frame_buttons={},
            _mask_buttons={},
            _action=Mock(),
            _status=Mock(),
            _preview=Mock(),
        )

    def test_just_dance_cancel_button_stays_enabled_during_countdown(self):
        screen = self.make_capture_stub("dance")

        CaptureScreen._set_state(screen, State.COUNTING)

        screen._back.setEnabled.assert_called_once_with(True)
        screen._back.setText.assert_called_once_with("Annuler le défi")

    def test_regular_gif_back_button_remains_disabled_during_countdown(self):
        screen = self.make_capture_stub("photo")

        CaptureScreen._set_state(screen, State.COUNTING)

        screen._back.setEnabled.assert_called_once_with(False)
        screen._back.setText.assert_called_once_with("Retour")

    def test_cancelled_capture_does_not_restart_sequence_from_queued_callback(self):
        screen = self.make_capture_stub("dance")
        screen._active = False
        screen._planned_poses = Mock()

        CaptureScreen._start_sequence(screen)

        screen._planned_poses.assert_not_called()

    def test_single_photo_challenges_can_offer_frames_but_dance_cannot(self):
        for challenge_type, photo_format, expected in (
            ("photo", "single", True),
            ("guest_wheel", "single", True),
            ("dance", "gif", False),
        ):
            with self.subTest(challenge_type=challenge_type):
                nav = SimpleNamespace(
                    session=Session(
                        challenge_id="challenge",
                        challenge_type=challenge_type,
                        photo_format=photo_format,
                    ),
                    config=SimpleNamespace(),
                    camera=Mock(),
                )
                screen = CaptureScreen(nav)
                self.addCleanup(screen.close)
                screen._prepare_mask_gallery = Mock()
                screen._update_preview_processor = Mock()

                self.assertTrue(CaptureScreen._prepare_scene(screen))

                self.assertEqual(not screen._frame_option.isHidden(), expected)


if __name__ == "__main__":
    unittest.main()
