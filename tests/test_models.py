import unittest

from app.core.models import AUXILIARY_MODELS, DEFAULT_DOWNLOADS, DOWNLOAD_MODELS, MODEL_NAMES, MODELS


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

    def test_modele_pose_est_optionnel_et_telechargeable(self):
        spec = AUXILIARY_MODELS["pose"]
        self.assertIs(DOWNLOAD_MODELS["pose"], spec)
        self.assertTrue(spec.url.startswith("https://") and spec.url.endswith(spec.filename))
        self.assertEqual(spec.filename, "pose_landmarker_lite.task")
        self.assertNotIn("pose", DEFAULT_DOWNLOADS)

    def test_modele_main_est_optionnel_et_telechargeable(self):
        spec = AUXILIARY_MODELS["main"]
        self.assertIs(DOWNLOAD_MODELS["main"], spec)
        self.assertTrue(spec.url.startswith("https://") and spec.url.endswith(spec.filename))
        self.assertEqual(spec.filename, "hand_landmarker.task")
        self.assertNotIn("main", DEFAULT_DOWNLOADS)


if __name__ == "__main__":
    unittest.main()
