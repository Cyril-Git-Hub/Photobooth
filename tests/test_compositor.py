import unittest

import numpy as np

from app.core.compositor import SceneRenderer, blend, cover_resize
from app.core.segmentation import Segmenter


class FixedSegmenter(Segmenter):
    """Renvoie un masque donné (ou une suite de masques) et compte les appels."""
    def __init__(self, *masks, despill_to=None):
        self.masks, self.calls, self.despill_to = list(masks), 0, despill_to

    def segment(self, frame):
        mask = self.masks[min(self.calls, len(self.masks) - 1)]
        self.calls += 1
        return mask

    def clean_frame(self, frame, mask):
        if self.despill_to is None:
            return frame
        out = frame.copy(); out[:] = self.despill_to
        return out


def solid(width, height, color):
    image = np.zeros((height, width, 3), np.uint8)
    image[:] = color
    return image


class CoverResizeTests(unittest.TestCase):
    def test_taille_exacte_quel_que_soit_le_format(self):
        for source in [(200, 100), (100, 200), (64, 64), (1920, 1080)]:
            out = cover_resize(solid(*source, (5, 5, 5)), 96, 54)
            self.assertEqual(out.shape, (54, 96, 3), source)

    def test_pas_de_deformation_recadrage_au_centre(self):
        image = np.zeros((100, 200, 3), np.uint8)
        image[:, :100] = (255, 0, 0)       # moitié gauche bleue
        image[:, 100:] = (0, 0, 255)       # moitié droite rouge
        out = cover_resize(image, 100, 100)    # on garde le centre : 50 px de chaque couleur
        self.assertEqual(tuple(out[50, 10]), (255, 0, 0))
        self.assertEqual(tuple(out[50, 90]), (0, 0, 255))
        self.assertEqual(tuple(out[50, 49]), (255, 0, 0))
        self.assertEqual(tuple(out[50, 50]), (0, 0, 255))


class BlendTests(unittest.TestCase):
    def test_masque_plein_vide_et_demi(self):
        frame, background = solid(8, 4, (200, 100, 0)), solid(8, 4, (0, 100, 200))
        full = blend(frame, np.ones((4, 8), np.float32), background)
        empty = blend(frame, np.zeros((4, 8), np.float32), background)
        half = blend(frame, np.full((4, 8), 0.5, np.float32), background)
        self.assertTrue(np.array_equal(full, frame))
        self.assertTrue(np.array_equal(empty, background))
        self.assertTrue(np.all(np.abs(half.astype(int) - [100, 100, 100]) <= 1))
        self.assertEqual(full.dtype, np.uint8)

    def test_tailles_incompatibles(self):
        with self.assertRaises(ValueError):
            blend(solid(8, 4, (0, 0, 0)), np.ones((4, 8), np.float32), solid(9, 4, (0, 0, 0)))
        with self.assertRaises(ValueError):
            blend(solid(8, 4, (0, 0, 0)), np.ones((5, 8), np.float32), solid(8, 4, (0, 0, 0)))


class SceneRendererTests(unittest.TestCase):
    def setUp(self):
        self.frame = solid(64, 36, (0, 200, 0))
        self.background = solid(160, 90, (200, 0, 0))
        left = np.zeros((36, 64), np.float32); left[:, :32] = 1.0       # personne à gauche
        self.left = left

    def test_photo_personne_a_gauche_decor_a_droite(self):
        out = SceneRenderer(FixedSegmenter(self.left), self.background).render_photo(self.frame)
        self.assertEqual(tuple(out[10, 5]), (0, 200, 0))
        self.assertEqual(tuple(out[10, 60]), (200, 0, 0))

    def test_decor_adapte_a_la_taille_de_l_image_et_mis_en_cache(self):
        renderer = SceneRenderer(FixedSegmenter(self.left), self.background)
        renderer.render_photo(self.frame)
        renderer.render_photo(self.frame)
        self.assertEqual(list(renderer._cache), [(64, 36)])
        renderer.render_photo(solid(128, 72, (0, 200, 0)))
        self.assertEqual(len(renderer._cache), 2)

    def test_masque_de_taille_differente_redimensionne(self):
        small = np.zeros((18, 32), np.float32); small[:, :16] = 1.0
        out = SceneRenderer(FixedSegmenter(small), self.background).render_photo(self.frame)
        self.assertEqual(out.shape, self.frame.shape)
        self.assertEqual(tuple(out[10, 5]), (0, 200, 0))

    def test_apercu_sans_image_fantome(self):
        """Une personne qui bouge ne laisse pas de trace : l'aperçu suit exactement le masque courant."""
        empty, full = np.zeros((36, 64), np.float32), np.ones((36, 64), np.float32)
        renderer = SceneRenderer(FixedSegmenter(full, empty, full), self.background)
        self.assertEqual(tuple(renderer.render_preview(self.frame)[0, 0]), (0, 200, 0))   # personne présente
        self.assertEqual(tuple(renderer.render_preview(self.frame)[0, 0]), (200, 0, 0))   # partie : décor pur
        self.assertEqual(tuple(renderer.render_preview(self.frame)[0, 0]), (0, 200, 0))   # revenue : aucune rémanence

    def test_retouche_de_l_image_avant_melange(self):
        seg = FixedSegmenter(np.ones((36, 64), np.float32), despill_to=(7, 8, 9))
        out = SceneRenderer(seg, self.background).render_photo(self.frame)
        self.assertEqual(tuple(out[0, 0]), (7, 8, 9))

    def test_statistiques_dans_les_logs(self):
        renderer = SceneRenderer(FixedSegmenter(self.left), self.background)
        with self.assertLogs("app.core.compositor", level="INFO") as logs:
            for _ in range(60):
                renderer.render_preview(self.frame)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("ms par image", logs.output[0])


if __name__ == "__main__":
    unittest.main()
