import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.session import Session
from app.ui.screens.format_select import FormatSelectScreen


class FormatSelectMaskResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.session = Session()
        self.navigation = SimpleNamespace(session=self.session, destinations=[])
        self.navigation.go_to = self.navigation.destinations.append
        self.screen = FormatSelectScreen(self.navigation)
        first = Path("mask-one.png")
        self.session.virtual_mask_path = first
        self.session.virtual_mask_paths = [first, Path("mask-two.png")]

    def assert_masks_cleared(self):
        self.assertIsNone(self.session.virtual_mask_path)
        self.assertEqual(self.session.virtual_mask_paths, [])

    def test_selecting_single_photo_clears_masks(self):
        self.screen._choose("single")
        self.assert_masks_cleared()
        self.assertEqual(self.navigation.destinations, ["background_select"])

    def test_selecting_photobooth_clears_masks(self):
        self.screen._choose("strip")
        self.assert_masks_cleared()
        self.assertEqual(self.navigation.destinations, ["background_select"])

    def test_selecting_gif_clears_masks(self):
        self.screen._choose_gif()
        self.assert_masks_cleared()
        self.assertEqual(self.navigation.destinations, ["gif_options"])


if __name__ == "__main__":
    unittest.main()
