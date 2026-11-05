import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.core.challenges import load_challenges
from app.core.guests import Guest
from app.ui.screens.challenge import ChallengeScreen


class ChallengeTests(unittest.TestCase):
    def test_guest_wheel_type_is_loaded_and_requires_single_photo(self):
        definitions = {
            "defis": [
                {"id": "photo", "titre": "Photo", "consigne": "Pose !"},
                {"id": "wheel", "titre": "Roue", "consigne": "Retrouve cette personne.",
                 "type": "guest_wheel", "format": "single"},
                {"id": "invalid-wheel", "titre": "Roue invalide", "consigne": "Retrouve-la.",
                 "type": "guest_wheel", "format": "gif"},
            ],
            "categories": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "defis.json"
            path.write_text(json.dumps(definitions), encoding="utf-8")

            loaded = load_challenges(path)

        self.assertEqual([(item.id, item.challenge_type) for item in loaded],
                         [("photo", "photo"), ("wheel", "guest_wheel")])

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


if __name__ == "__main__":
    unittest.main()
