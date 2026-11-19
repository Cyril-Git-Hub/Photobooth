import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.ui.screens.review import ReviewScreen


class ReviewCancelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_cancel_discards_gif_and_returns_to_challenge(self):
        with tempfile.TemporaryDirectory() as directory:
            gif = Path(directory) / "dance.gif"
            gif.write_bytes(b"gif")
            session = SimpleNamespace(
                photos=[gif], poses=[], photo_source_frame=object(),
                photo_style="cartoon", photo_style_person_only=True, challenge_id="just-dance",
            )
            nav = SimpleNamespace(session=session, destinations=[])
            nav.go_to = nav.destinations.append
            screen = ReviewScreen(nav)

            screen._cancel_result()

            self.assertFalse(gif.exists())
            self.assertEqual(session.photos, [])
            self.assertEqual(nav.destinations, ["challenge"])
            self.assertIsNone(session.photo_source_frame)
            self.assertEqual(session.photo_style, "original")

    def test_cancel_classic_gif_returns_to_format_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            gif = Path(directory) / "classic.gif"
            gif.write_bytes(b"gif")
            session = SimpleNamespace(
                photos=[gif], poses=[], photo_source_frame=None,
                photo_style="original", photo_style_person_only=False, challenge_id="",
            )
            nav = SimpleNamespace(session=session, destinations=[])
            nav.go_to = nav.destinations.append
            screen = ReviewScreen(nav)

            screen._cancel_result()

            self.assertFalse(gif.exists())
            self.assertEqual(session.photos, [])
            self.assertEqual(nav.destinations, ["format_select"])


if __name__ == "__main__":
    unittest.main()
