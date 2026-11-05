import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from app.ui.screensaver import (
    DEFAULT_PHOTOS, MAX_PHOTOS, PHOTO_SPEED_MAX, PHOTO_SPEED_MIN, PHOTO_TILT_MAX, ScreensaverOverlay,
)


class ScreensaverAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paths = []
        for index in range(MAX_PHOTOS + 2):
            path = Path(self._tmp.name) / f"photo-{index}.png"
            image = QImage(32, 24, QImage.Format.Format_RGB32)
            image.fill(index)
            self.assertTrue(image.save(str(path)))
            self.paths.append(path)
        self.overlay = ScreensaverOverlay(None, lambda _position: None)
        self.overlay.setGeometry(0, 0, 800, 600)
        self.addCleanup(self.overlay.close)

    def test_uses_default_photo_count_and_respects_the_maximum(self):
        self.overlay.set_photos(self.paths)
        self.assertEqual(len(self.overlay._photos), DEFAULT_PHOTOS)
        self.overlay.set_photos(self.paths, MAX_PHOTOS)
        self.assertEqual(len(self.overlay._photos), MAX_PHOTOS)
        for photo in self.overlay._photos:
            bound_width, bound_height = self.overlay._photo_bounds(photo)
            self.assertGreaterEqual(photo.x - bound_width / 2, 0)
            self.assertLessEqual(photo.x + bound_width / 2, self.overlay.width())
            self.assertGreaterEqual(photo.y - bound_height / 2, 0)
            self.assertLessEqual(photo.y + bound_height / 2, self.overlay.height())
            self.assertLessEqual(abs(photo.angle), PHOTO_TILT_MAX)
            self.assertTrue(PHOTO_SPEED_MIN <= abs(photo.vx) <= PHOTO_SPEED_MAX)
            self.assertTrue(PHOTO_SPEED_MIN <= abs(photo.vy) <= PHOTO_SPEED_MAX)

    def test_rejects_photo_count_outside_supported_range(self):
        for count in (0, MAX_PHOTOS + 1):
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.overlay.set_photos(self.paths, count)

    def test_message_and_photos_move_when_animation_advances(self):
        self.overlay.set_photos(self.paths)
        self.overlay._message_x = self.overlay.width() / 2
        self.overlay._message_y = self.overlay.height() / 2
        photo = self.overlay._photos[0]
        photo.x = self.overlay.width() / 2
        photo.y = self.overlay.height() / 2
        message_start = (self.overlay._message_x, self.overlay._message_y)
        photo_start = (photo.x, photo.y)

        self.overlay._advance()

        self.assertNotEqual(message_start, (self.overlay._message_x, self.overlay._message_y))
        self.assertNotEqual(photo_start, (self.overlay._photos[0].x, self.overlay._photos[0].y))
        self.assertAlmostEqual(abs(photo.x - photo_start[0]), abs(photo.vx))
        self.assertAlmostEqual(abs(photo.y - photo_start[1]), abs(photo.vy))

    def test_animation_timer_only_runs_while_visible(self):
        self.overlay.show()
        self.assertTrue(self.overlay._timer.isActive())
        self.overlay.hide()
        self.assertFalse(self.overlay._timer.isActive())


if __name__ == "__main__":
    unittest.main()
