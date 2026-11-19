import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog

from app.ui.admin_dialog import _show_fullscreen_on_screen


class AdminDialogDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_uses_fullscreen_state_and_target_screen_geometry(self):
        screen = self.app.primaryScreen()
        dialog = QDialog()
        self.addCleanup(dialog.close)

        _show_fullscreen_on_screen(dialog, screen)
        dialog.show()
        self.app.processEvents()

        self.assertTrue(dialog.windowState() & Qt.WindowState.WindowFullScreen)
        self.assertEqual(dialog.windowHandle().screen(), screen)
        self.assertEqual(dialog.geometry(), screen.geometry())


if __name__ == "__main__":
    unittest.main()
