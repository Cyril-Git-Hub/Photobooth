import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from app.ui.capture_display import CaptureDisplayController


class CaptureDisplayGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.photos = []
        for index in range(4):
            path = Path(self._tmp.name) / f"photo-{index}.png"
            image = QImage(32, 24, QImage.Format.Format_RGB32)
            image.fill(index)
            self.assertTrue(image.save(str(path)))
            self.photos.append(path)

        self.main = SimpleNamespace(
            theme=None,
            current_name="home",
            config=SimpleNamespace(dp_duree=6),
            slideshow=SimpleNamespace(photos=lambda: list(self.photos)),
        )
        self.main.screen = lambda: object()
        self.screen = object()
        self.controller = CaptureDisplayController(self.main)
        self.addCleanup(self.controller.close)
        self.image = QImage(16, 12, QImage.Format.Format_RGB32)

    def refresh_with_fake_window(self):
        window = mock.Mock()
        window.width.return_value = 800
        window.height.return_value = 600
        with (mock.patch("app.ui.capture_display.pick_third_screen", return_value=self.screen),
              mock.patch("app.ui.capture_display.CaptureDisplayWindow", return_value=window)):
            self.controller.refresh()
        return window

    def test_idle_third_screen_rotates_random_party_photos(self):
        seen = []
        self.controller._load_gallery_photo = mock.Mock(
            side_effect=lambda path: (seen.append(path), self.image)[1])

        window = self.refresh_with_fake_window()
        for _ in range(len(self.photos) - 1):
            self.controller._timer.stop()
            self.controller._advance_gallery()

        self.assertEqual(set(seen), set(self.photos))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(window.set_gallery_photo.call_count, len(self.photos))
        self.assertTrue(self.controller._timer.isActive())

    def test_live_camera_preview_pauses_gallery_and_it_resumes_afterward(self):
        self.controller._load_gallery_photo = mock.Mock(return_value=self.image)
        window = self.refresh_with_fake_window()
        window.set_gallery_photo.reset_mock()

        with mock.patch("app.ui.capture_display.pick_third_screen", return_value=self.screen):
            self.main.current_name = "capture"
            self.controller.refresh()
            self.assertFalse(self.controller._timer.isActive())
            self.assertFalse(window.set_gallery_photo.called)

            self.main.current_name = "review"
            self.controller.refresh()

        self.assertTrue(window.set_gallery_photo.called)
        self.assertTrue(self.controller._timer.isActive())


if __name__ == "__main__":
    unittest.main()
