import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import json
import numpy as np

from app.core.accessories import _match_hand_to_pose, place_accessory
from app.core.accessory_config import AccessoryPlacement, DEFAULT_ACCESSORY_PLACEMENT
from app.core.challenges import load_challenges


def _hand_landmarks():
    points = [(0.5, 0.6)] * 21
    points[1:5] = [(0.46, 0.59), (0.44, 0.57), (0.42, 0.55), (0.40, 0.53)]
    points[5:9] = [(0.44, 0.54), (0.44, 0.50), (0.44, 0.47), (0.44, 0.44)]
    points[9:13] = [(0.49, 0.53), (0.49, 0.49), (0.49, 0.46), (0.49, 0.43)]
    points[13:17] = [(0.54, 0.54), (0.54, 0.50), (0.54, 0.47), (0.54, 0.44)]
    points[17:21] = [(0.58, 0.57), (0.58, 0.54), (0.58, 0.51), (0.58, 0.48)]
    return [SimpleNamespace(x=x, y=y) for x, y in points]


class AccessoryPlacementTests(unittest.TestCase):
    def test_associe_la_main_au_poignet_de_pose_le_plus_fiable(self):
        pose = [SimpleNamespace(x=0.0, y=0.0, visibility=0.0) for _ in range(33)]
        pose[11] = SimpleNamespace(x=0.2, y=0.2, visibility=1.0)
        pose[13] = SimpleNamespace(x=0.3, y=0.3, visibility=1.0)
        pose[15] = SimpleNamespace(x=0.4, y=0.4, visibility=1.0)
        first_hand = _hand_landmarks()
        second_hand = _hand_landmarks()
        for point in first_hand:
            point.x += 0.4
        selected, arm = _match_hand_to_pose(
            [first_hand, second_hand], pose, 200, 200)

        self.assertIs(selected, second_hand)
        self.assertIsNotNone(arm)

    def test_sabre_place_sur_le_poignet_et_suit_le_bras(self):
        image = np.zeros((240, 320, 3), dtype=np.uint8)
        accessory = np.zeros((160, 40, 4), dtype=np.uint8)
        accessory[10:115, 17:23] = (255, 0, 0, 255)
        accessory[115:155, 10:30] = (0, 0, 255, 255)
        landmarks = _hand_landmarks()

        rendered = place_accessory(image, accessory, landmarks, DEFAULT_ACCESSORY_PLACEMENT)

        self.assertFalse(np.array_equal(rendered, image))
        self.assertGreater(int(np.count_nonzero(rendered[:, :, 2])), 0)

    def test_sans_repere_le_resultat_reste_inchange(self):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        accessory = np.ones((100, 30, 4), dtype=np.uint8) * 255

        rendered = place_accessory(image, accessory, [], DEFAULT_ACCESSORY_PLACEMENT)

        self.assertIs(rendered, image)

    def test_rotation_quart_de_tour_oriente_le_sabre_perpendiculairement_a_la_main(self):
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        accessory = np.zeros((100, 20, 4), dtype=np.uint8)
        accessory[:80] = (0, 0, 255, 255)
        landmarks = _hand_landmarks()

        rendered = place_accessory(
            image, accessory, landmarks, AccessoryPlacement(rotation_degrees=90))
        red_pixels = np.argwhere(rendered[:, :, 2] > 0)
        blade_extent = red_pixels.max(axis=0) - red_pixels.min(axis=0)

        self.assertGreater(blade_extent[1], blade_extent[0])

    def test_sens_vers_le_haut_garde_la_lame_en_haut_quand_l_axe_main_s_inverse(self):
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        accessory = np.zeros((100, 20, 4), dtype=np.uint8)
        accessory[:80] = (0, 0, 255, 255)
        points_up = _hand_landmarks()
        points_down = [
            SimpleNamespace(x=point.x, y=1.1 - point.y)
            for point in points_up
        ]
        for points in (points_up, points_down):
            rendered = place_accessory(
                image, accessory, points,
                AccessoryPlacement(
                    rotation_degrees=80, direction="vers_le_haut",
                    image_anchor=(0.5, 0.91)))
            blade_pixels = np.argwhere(rendered[:, :, 2] > 0)

            self.assertLess(float(blade_pixels[:, 0].mean()), 110)

    def test_decalage_transversal_deplace_le_sabre_vers_la_main(self):
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        accessory = np.zeros((100, 20, 4), dtype=np.uint8)
        accessory[:80] = (0, 0, 255, 255)
        landmarks = _hand_landmarks()
        centered = place_accessory(
            image, accessory, landmarks,
            AccessoryPlacement(rotation_degrees=90, image_anchor=(0.5, 0.5)))
        shifted = place_accessory(
            image, accessory, landmarks,
            AccessoryPlacement(
                rotation_degrees=90, image_anchor=(0.5, 0.5), offset=(-0.5, 0.0)))

        centered_x = np.argwhere(centered[:, :, 2] > 0)[:, 1].mean()
        shifted_x = np.argwhere(shifted[:, :, 2] > 0)[:, 1].mean()

        self.assertLess(shifted_x, centered_x)

    def test_couche_derriere_preserve_la_main_devant_l_accessoire(self):
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        image[105:125, 80:120] = (0, 255, 0)
        accessory = np.zeros((100, 20, 4), dtype=np.uint8)
        accessory[:, :] = (0, 0, 255, 255)
        landmarks = _hand_landmarks()
        placement = AccessoryPlacement(
            image_anchor=(0.5, 0.5), size_reference="main",
            size_ratio=3, hand_layer="derriere")

        behind = place_accessory(image, accessory, landmarks, placement)
        in_front = place_accessory(
            image, accessory, landmarks,
            AccessoryPlacement(
                image_anchor=(0.5, 0.5), size_reference="main",
                size_ratio=3, hand_layer="devant"))

        y, x = 112, 100
        np.testing.assert_allclose(behind[y, x], image[y, x], atol=5)
        self.assertFalse(np.array_equal(in_front[y, x], image[y, x]))


class ChallengeAccessoryTests(unittest.TestCase):
    def test_accessoire_png_est_resolu_relativement_au_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "defis").mkdir()
            accessory = root / "defis" / "sabre.png"
            accessory.write_bytes(b"png")
            challenge_file = root / "defis.json"
            challenge_file.write_text(
                json.dumps({
                    "profils_accessoires": {"arme_main": {}},
                    "defis": [{"id": "sabre", "titre": "Jedi", "consigne": "Pose !",
                               "format": "single", "decor": "none",
                               "accessoire": {"profil": "arme_main", "image": "defis/sabre.png"}}],
                }),
                encoding="utf-8",
            )

            loaded = load_challenges(challenge_file)

        challenge = next(item for item in loaded if item.id == "sabre")
        self.assertEqual(challenge.accessory.image, accessory)
        self.assertEqual(challenge.accessory.placement, DEFAULT_ACCESSORY_PLACEMENT)

    def test_defis_partagent_un_profil_et_peuvent_le_surcharger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "defis").mkdir()
            for name in ("sabre", "katana"):
                (root / "defis" / f"{name}.png").write_bytes(b"png")
            challenge_file = root / "defis.json"
            challenge_file.write_text(json.dumps({
                "profils_accessoires": {
                    "arme_main": {
                        "ancrage_corps": "main",
                        "orientation": "axe_main",
                        "ancrage_image": {"x": 0.5, "y": 0.8},
                        "taille": {"repere": "avant_bras", "ratio": 2.4},
                    },
                },
                "defis": [
                    {"id": name, "titre": name, "consigne": "Pose !",
                     "format": "single", "decor": "none",
                     "accessoire": {"profil": "arme_main", "image": f"defis/{name}.png"}}
                    for name in ("sabre", "katana")
                ],
            }), encoding="utf-8")

            loaded = load_challenges(challenge_file)

        self.assertEqual([item.accessory.image.name for item in loaded], ["sabre.png", "katana.png"])
        self.assertEqual(loaded[0].accessory.placement, loaded[1].accessory.placement)
        self.assertEqual(loaded[0].accessory.placement.size_ratio, 2.4)

    def test_profil_accessoire_configure_la_couche_de_la_main(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sabre.png").write_bytes(b"png")
            challenge_file = root / "defis.json"
            challenge_file.write_text(json.dumps({
                "profils_accessoires": {"arme_main": {"couche": "derriere"}},
                "defis": [{
                    "id": "sabre", "titre": "Jedi", "consigne": "Pose !",
                    "format": "single", "decor": "none",
                    "accessoire": {"profil": "arme_main", "image": "sabre.png"},
                }],
            }), encoding="utf-8")

            loaded = load_challenges(challenge_file)

        self.assertEqual(loaded[0].accessory.placement.hand_layer, "derriere")

    def test_parametres_locaux_remplacent_ceux_du_profil(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            accessory = root / "sabre.png"
            accessory.write_bytes(b"png")
            challenge_file = root / "defis.json"
            challenge_file.write_text(json.dumps({
                "profils_accessoires": {"arme_main": {"taille": {"ratio": 2.4}}},
                "defis": [{
                    "id": "sabre", "titre": "Jedi", "consigne": "Pose !",
                    "format": "single", "decor": "none",
                    "accessoire": {
                        "profil": "arme_main", "image": "sabre.png",
                        "placement": {"taille": {"ratio": 1.5}, "rotation_deg": 12},
                    },
                }],
            }), encoding="utf-8")

            loaded = load_challenges(challenge_file)

        self.assertEqual(loaded[0].accessory.placement.size_ratio, 1.5)
        self.assertEqual(loaded[0].accessory.placement.rotation_degrees, 12)

    def test_accessoire_n_est_accepte_que_pour_une_photo_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            accessory = root / "sabre.png"
            accessory.write_bytes(b"png")
            challenge_file = root / "defis.json"
            challenge_file.write_text(
                '{"defis":[{"id":"gif-sabre","titre":"Jedi","consigne":"Pose !",'
                '"format":"gif","decor":"none","accessoire":"sabre.png"}]}',
                encoding="utf-8",
            )

            loaded = load_challenges(challenge_file)

        self.assertNotIn("gif-sabre", [item.id for item in loaded])


if __name__ == "__main__":
    unittest.main()
