import unittest
from unittest import mock

import numpy as np

from app.core import webcam


class FakeCap:
    def __init__(self, opened=True, reads=True):
        self.opened, self.reads = opened, reads
        self.released = False
        self.props = {}

    def isOpened(self):
        return self.opened

    def read(self):
        return (True, np.zeros((4, 4, 3), np.uint8)) if self.reads else (False, None)

    def set(self, prop, value):
        self.props[prop] = value
        return True

    def get(self, prop):
        return float(self.props.get(prop, 0))

    def release(self):
        self.released = True


class OpenCaptureTests(unittest.TestCase):
    def open_with(self, caps):
        with mock.patch.object(webcam, "candidate_backends", return_value=list(range(len(caps)))), \
             mock.patch.object(webcam.cv2, "VideoCapture", side_effect=caps):
            return webcam.open_capture(0, 1920, 1080)

    def test_premier_backend_qui_fonctionne(self):
        good = FakeCap()
        self.assertIs(self.open_with([good]), good)
        self.assertEqual(good.props[webcam.cv2.CAP_PROP_FRAME_WIDTH], 1920)
        self.assertEqual(good.props[webcam.cv2.CAP_PROP_FRAME_HEIGHT], 1080)
        self.assertEqual(good.props[webcam.cv2.CAP_PROP_FOURCC], webcam.FOURCC_MJPG)
        self.assertFalse(good.released)

    def test_bascule_sur_le_backend_suivant(self):
        closed, no_image, good = FakeCap(opened=False), FakeCap(reads=False), FakeCap()
        self.assertIs(self.open_with([closed, no_image, good]), good)
        self.assertTrue(closed.released and no_image.released)

    def test_aucune_camera_utilisable(self):
        caps = [FakeCap(opened=False), FakeCap(reads=False)]
        self.assertIsNone(self.open_with(caps))
        self.assertTrue(all(c.released for c in caps))

    def test_backends_selon_la_plateforme(self):
        with mock.patch.object(webcam.sys, "platform", "win32"):
            self.assertEqual(webcam.candidate_backends()[0], webcam.cv2.CAP_DSHOW)
        with mock.patch.object(webcam.sys, "platform", "linux"):
            self.assertEqual(webcam.candidate_backends(), [webcam.cv2.CAP_ANY])


class ShrinkTests(unittest.TestCase):
    def test_reduit_en_gardant_le_format(self):
        out = webcam.shrink(np.zeros((1080, 1920, 3), np.uint8), 960)
        self.assertEqual(out.shape, (540, 960, 3))

    def test_ne_agrandit_pas(self):
        frame = np.zeros((360, 640, 3), np.uint8)
        self.assertIs(webcam.shrink(frame, 960), frame)


if __name__ == "__main__":
    unittest.main()
