import unittest

from app.core.models import DEFAULT_DOWNLOADS, MODEL_NAMES, MODELS


class ModelsTests(unittest.TestCase):
    def test_modeles_coherents(self):
        self.assertEqual(MODEL_NAMES, ("paysage", "carre", "multiclasse"))
        filenames = [spec.filename for spec in MODELS.values()]
        self.assertEqual(len(set(filenames)), len(filenames))
        for name, spec in MODELS.items():
            self.assertTrue(spec.url.startswith("https://") and spec.url.endswith(spec.filename), name)
            self.assertTrue(spec.filename.endswith(".tflite"), name)
            width, height = spec.input_size
            self.assertGreater(width, 0); self.assertGreater(height, 0)

    def test_paysage_est_au_format_16_9(self):
        width, height = MODELS["paysage"].input_size
        self.assertAlmostEqual(width / height, 16 / 9, places=2)

    def test_telechargements_par_defaut(self):
        self.assertTrue(set(DEFAULT_DOWNLOADS) <= set(MODEL_NAMES))
        self.assertNotIn("multiclasse", DEFAULT_DOWNLOADS)   # le plus gros reste optionnel


if __name__ == "__main__":
    unittest.main()
