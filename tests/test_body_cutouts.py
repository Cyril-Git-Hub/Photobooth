import threading
import unittest
from types import SimpleNamespace

import numpy as np

from app.core.body_cutouts import (
    BodyCutoutRenderer,
    build_body_cutout_mask,
    build_body_part_mask,
)


def _pose():
    points = [(0.5, 0.5)] * 33
    points[0] = (0.50, 0.15)
    points[7] = (0.44, 0.18)
    points[8] = (0.56, 0.18)
    points[11] = (0.40, 0.30)
    points[12] = (0.60, 0.30)
    points[13] = (0.30, 0.45)
    points[14] = (0.70, 0.45)
    points[15] = (0.25, 0.60)
    points[16] = (0.75, 0.60)
    points[23] = (0.44, 0.55)
    points[24] = (0.56, 0.55)
    points[25] = (0.43, 0.75)
    points[26] = (0.57, 0.75)
    points[27] = (0.42, 0.95)
    points[28] = (0.58, 0.95)
    points[31] = (0.40, 0.98)
    points[32] = (0.60, 0.98)
    return [SimpleNamespace(x=x, y=y, visibility=1.0, presence=1.0)
            for x, y in points]


class BodyCutoutMaskTests(unittest.TestCase):
    def test_sous_taille_masque_pantalon_et_chaussures_sans_effacer_bras_ni_torse(self):
        labels = np.zeros((200, 200), dtype=np.uint8)
        labels[40:120, 55:145] = 4
        labels[120:190, 70:98] = 6
        labels[120:190, 102:130] = 6
        labels[190:200, 70:98] = 9
        labels[190:200, 102:130] = 10
        labels[130:165, 140:150] = 15

        mask = build_body_part_mask((200, 200, 3), labels, {"sous_taille"})

        self.assertGreater(mask[80, 100], 0.99)
        self.assertLess(mask[150, 84], 0.01)
        self.assertLess(mask[195, 110], 0.01)
        self.assertGreater(mask[145, 145], 0.99)

    def test_sous_taille_preserve_robe_et_jupe_pour_ne_pas_couper_le_haut(self):
        labels = np.zeros((200, 200), dtype=np.uint8)
        labels[50:180, 60:140] = 7
        labels[50:180, 145:185] = 5

        mask = build_body_part_mask((200, 200, 3), labels, {"sous_taille"})

        self.assertGreater(mask[80, 100], 0.99)
        self.assertGreater(mask[150, 100], 0.99)
        self.assertGreater(mask[150, 160], 0.99)

    def test_sous_taille_utilise_la_pose_si_le_pantalon_est_mal_classe(self):
        labels = np.zeros((200, 200), dtype=np.uint8)
        labels[40:190, 55:145] = 4

        mask = build_body_part_mask(
            (200, 200, 3), labels, {"sous_taille"}, _pose())

        self.assertLess(mask[150, 84], 0.1)
        self.assertLess(mask[150, 116], 0.1)
        self.assertLess(mask[110, 100], 0.1)
        self.assertGreater(mask[80, 100], 0.9)
        self.assertGreater(mask[95, 55], 0.9)

    def test_haut_corps_masque_la_zone_au_dessus_des_hanches(self):
        mask = build_body_cutout_mask((200, 200, 3), _pose(), {"haut_corps"})

        self.assertLess(mask[80, 100], 0.01)
        self.assertGreater(mask[150, 100], 0.99)

    def test_une_jambe_est_masquee_sans_supprimer_l_autre(self):
        labels = np.zeros((200, 200), dtype=np.uint8)
        labels[120:180, 76:94] = 6
        labels[120:180, 106:124] = 6
        labels[80:180, 70:95] = 12
        labels[80:180, 105:130] = 13
        labels[180:195, 70:95] = 9
        labels[180:195, 105:130] = 10
        mask = build_body_part_mask(
            (200, 200, 3), labels, {"jambe_gauche"}, _pose())

        self.assertLess(mask[150, 84], 0.01)
        self.assertGreater(mask[150, 116], 0.99)

    def test_repere_hors_image_est_ignore_sans_masquer_le_corps_entier(self):
        landmarks = _pose()
        landmarks[23].x = 20.0
        landmarks[25].x = 20.0
        landmarks[27].x = 20.0

        mask = build_body_cutout_mask((200, 200, 3), landmarks, {"jambe_gauche"})

        self.assertGreater(float(mask.mean()), 0.99)

    def test_un_bras_est_masque_sans_supprimer_l_autre(self):
        mask = build_body_cutout_mask((200, 200, 3), _pose(), {"bras_gauche"})

        self.assertLess(mask[95, 55], 0.1)
        self.assertGreater(mask[95, 145], 0.9)

    def test_tete_est_masquee_sans_couper_le_torse(self):
        mask = build_body_cutout_mask((200, 200, 3), _pose(), {"tete"})

        self.assertLess(mask[35, 100], 0.1)
        self.assertGreater(mask[85, 100], 0.9)

    def test_repere_incomplet_ne_supprime_pas_la_personne(self):
        mask = build_body_cutout_mask((200, 200, 3), _pose()[:10], {"tete"})

        np.testing.assert_array_equal(mask, np.ones((200, 200), dtype=np.float32))


class BodyCutoutRendererTests(unittest.TestCase):
    def test_apercu_rafraichit_le_cache_et_photo_refait_une_inference_fraiche(self):
        processor = object.__new__(BodyCutoutRenderer)
        processor._lock = threading.Lock()
        processor._pose_lock = threading.Lock()
        processor._onnx_lock = threading.Lock()
        processor._last_labels = None
        processor._last_labels_shape = None
        processor._last_inference = 0.0
        processor._landmarker = None
        processor._session = object()
        processor._parts = frozenset({"sous_taille"})
        inferred_values = []

        def infer(frame):
            value = int(frame[0, 0, 0])
            inferred_values.append(value)
            return np.full(frame.shape[:2], value, dtype=np.uint8), None

        processor._infer_parts_and_pose = infer
        mask = np.ones((8, 8), dtype=np.float32)
        first_frame = np.full((8, 8, 3), 1, dtype=np.uint8)
        next_frame = np.full((8, 8, 3), 2, dtype=np.uint8)
        photo_frame = np.full((8, 8, 3), 3, dtype=np.uint8)

        np.testing.assert_array_equal(
            processor.apply_to_mask_preview(first_frame, mask), mask)
        np.testing.assert_array_equal(
            processor.apply_to_mask_preview(next_frame, mask), mask)
        self.assertEqual(inferred_values, [1])
        self.assertTrue(np.all(processor._last_labels == 1))

        photo_mask = processor.apply_to_mask(photo_frame, mask)

        self.assertEqual(inferred_values, [1, 3])
        self.assertTrue(np.all(photo_mask == 1.0))
        self.assertTrue(np.all(processor._last_labels == 3))

    def test_diagnostic_classes_colore_les_pixels_reconnus_comme_pantalon(self):
        processor = object.__new__(BodyCutoutRenderer)
        labels = np.zeros((80, 120), dtype=np.uint8)
        labels[35:55, 45:70] = 6
        processor._segment_parts_preview = lambda frame: (labels, None)
        frame = np.full((80, 120, 3), 80, dtype=np.uint8)

        diagnostic = processor.render_parsing_debug_preview(frame)

        self.assertFalse(np.array_equal(diagnostic[40, 50], frame[40, 50]))
        np.testing.assert_array_equal(diagnostic[70, 90], frame[70, 90])


if __name__ == "__main__":
    unittest.main()
