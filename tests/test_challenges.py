import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.core.challenges import Challenge, load_challenges
from app.core.guests import Guest
from app.session import Session
from app.ui.screens.challenge import ChallengeScreen


class ChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_guest_wheel_type_is_loaded_and_requires_single_photo(self):
        definitions = {
            "defis": [
                {"id": "photo", "titre": "Photo", "consigne": "Pose !"},
                {"id": "wheel", "titre": "Roue", "consigne": "Retrouve cette personne.",
                 "type": "guest_wheel", "format": "single"},
                {"id": "invalid-wheel", "titre": "Roue invalide", "consigne": "Retrouve-la.",
                 "type": "guest_wheel", "format": "gif"},
                {"id": "dance", "titre": "Just Dance", "consigne": "Imite les poses.",
                 "type": "dance", "format": "gif"},
                {"id": "invalid-dance", "titre": "Danse", "consigne": "Imite-la.",
                 "type": "dance", "format": "single"},
            ],
            "categories": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "defis.json"
            path.write_text(json.dumps(definitions), encoding="utf-8")

            loaded = load_challenges(path)

        self.assertEqual([(item.id, item.challenge_type) for item in loaded],
                         [("photo", "photo"), ("wheel", "guest_wheel"), ("dance", "dance")])

    def test_guest_wheel_uses_ten_random_pseudos_and_excludes_current_guest(self):
        guests = [Guest(str(index), f"First{index}", pseudo=f"Pseudo{index}")
                  for index in range(20)]
        screen = SimpleNamespace(
            _wheel_guests=[], _wheel_error="",
            config=SimpleNamespace(fichier_invites=Path("invites.xlsx")),
            session=SimpleNamespace(guest_from_list=True, guest_pseudo="Pseudo0"),
        )
        with mock.patch("app.ui.screens.challenge.load_guests", return_value=guests):
            ChallengeScreen._load_wheel_guests(screen)

        self.assertEqual(len(screen._wheel_guests), 10)
        self.assertNotIn("Pseudo0", [guest.pseudo for guest in screen._wheel_guests])
        self.assertEqual(len({guest.pseudo for guest in screen._wheel_guests}), 10)

    def test_guest_wheel_preserves_retained_pseudo(self):
        guests = [Guest(str(index), f"First{index}", pseudo=f"Pseudo{index}")
                  for index in range(20)]
        screen = SimpleNamespace(
            _wheel_guests=[], _wheel_error="",
            config=SimpleNamespace(fichier_invites=Path("invites.xlsx")),
            session=SimpleNamespace(guest_from_list=False, guest_pseudo=""),
        )
        with mock.patch("app.ui.screens.challenge.load_guests", return_value=guests):
            ChallengeScreen._load_wheel_guests(screen, "Pseudo17")

        self.assertEqual(len(screen._wheel_guests), 10)
        self.assertIn("Pseudo17", [guest.pseudo for guest in screen._wheel_guests])

    def test_starting_just_dance_skips_gif_options_and_uses_defaults(self):
        session = Session(dance_pose_ids=[2, 5, 1])
        nav = SimpleNamespace(session=session, destinations=[])
        nav.go_to = nav.destinations.append
        screen = ChallengeScreen(nav)
        screen._current = Challenge(
            id="just-dance", title="Just Dance", instruction="Reproduis les poses.",
            photo_format="gif", background="none", challenge_type="dance")

        screen._start_challenge()

        self.assertEqual(nav.destinations, ["capture"])
        self.assertEqual(session.gif_capture_mode, "spaced")
        self.assertEqual(session.gif_effect, "loop")
        self.assertFalse(session.gif_hold_last)
        self.assertEqual(session.dance_pose_ids, [2, 5, 1])

    def test_challenge_footer_stays_in_place_when_wheel_panel_toggles(self):
        screen = ChallengeScreen(SimpleNamespace())
        screen.resize(1280, 720)
        screen.show()
        self.addCleanup(screen.close)
        self.app.processEvents()
        initial = (screen._back.geometry(), screen._another.geometry())

        screen._wheel_panel.show()
        self.app.processEvents()
        with_wheel = (screen._back.geometry(), screen._another.geometry())
        screen._wheel_panel.hide()
        self.app.processEvents()

        self.assertEqual(initial, with_wheel)
        self.assertEqual(initial, (screen._back.geometry(), screen._another.geometry()))
        self.assertIs(screen._spin.parentWidget(), screen._wheel_panel)
        self.assertEqual(screen._start.text(), "Je relève le défi !")
        self.assertGreater(screen._start.width(), screen._back.width())

    def test_guest_wheel_layout_stays_stable_during_spin(self):
        screen = ChallengeScreen(SimpleNamespace())
        screen.resize(1276, 723)
        screen._wheel_panel.show()
        screen._spin.show()
        screen._gate_hint.show()
        screen._availability.setText(
            "10 invités dans la roue. Lance le tirage, puis retrouve la personne pour faire la photo ensemble.")
        screen._info_panel.setMinimumWidth(max(500, int(screen.width() * 0.4)))
        screen.show()
        self.addCleanup(screen.close)
        self.app.processEvents()
        initial = (
            screen._wheel_panel.geometry(),
            screen._wheel.geometry(),
            screen._info_panel.geometry(),
            screen._spin.geometry(),
        )

        screen._availability.setText("La roue tourne…")
        screen._set_gate_hint("Tirage en cours…")
        self.app.processEvents()
        spinning = (
            screen._wheel_panel.geometry(),
            screen._wheel.geometry(),
            screen._info_panel.geometry(),
            screen._spin.geometry(),
        )

        self.assertEqual(initial, spinning)
        self.assertEqual(
            screen._spin.y() - screen._wheel.geometry().bottom() - 1, 4)

    def test_guest_wheel_start_button_is_disabled_until_draw_finishes(self):
        nav = SimpleNamespace(session=SimpleNamespace(
            challenge_id="", challenge_guest_name=""))
        screen = ChallengeScreen(nav)
        self.addCleanup(screen.close)
        guest = Guest("1", "First", pseudo="Pseudo")
        def load_guests(_retained_name=""):
            screen._wheel_guests = [guest]

        with mock.patch.object(screen, "_load_wheel_guests", side_effect=load_guests):
            screen._show_challenge(Challenge(
                id="wheel", title="Roue", instruction="Trouve la personne.",
                photo_format="single", background="none", challenge_type="guest_wheel"))

        status_height = screen._availability.height()
        self.assertTrue(screen._availability.wordWrap())
        self.assertEqual(
            screen._availability.minimumHeight(), screen._availability.maximumHeight())
        self.assertEqual(screen._start.text(), "Je relève le défi !")
        self.assertFalse(screen._start.isEnabled())
        self.assertFalse(screen._gate_hint.isHidden())

        with mock.patch.object(screen._wheel, "spin"):
            screen._spin_wheel()
        self.assertEqual(screen._availability.text(), "La roue tourne…")
        self.assertEqual(screen._availability.height(), status_height)

        screen._wheel_finished(0)

        self.assertTrue(screen._start.isEnabled())
        self.assertEqual(screen._availability.height(), status_height)
        self.assertFalse(screen._gate_hint.isHidden())
        self.assertIn("Tirage terminé", screen._gate_hint.text())


if __name__ == "__main__":
    unittest.main()
