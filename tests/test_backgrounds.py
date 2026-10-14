import random
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from app.core import backgrounds


def write_png(path: Path, width=64, height=36, color=(10, 20, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((height, width, 3), color, np.uint8)
    ok, buf = cv2.imencode(".png", image)
    path.write_bytes(buf.tobytes())


class ScanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fonds é ")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_dossier_absent_ou_vide(self):
        self.assertEqual(backgrounds.scan_backgrounds(self.root / "inexistant"), [])
        self.assertEqual(backgrounds.scan_backgrounds(self.root), [])

    def test_themes_tries_et_filtres(self):
        write_png(self.root / "séries" / "b.png")
        write_png(self.root / "séries" / "A.PNG")
        write_png(self.root / "films" / "x.jpg.png")
        (self.root / "films" / "notes.txt").write_text("pas une image")
        (self.root / "vide").mkdir()
        write_png(self.root / "_brouillon" / "z.png")      # dossier ignoré
        write_png(self.root / ".cache" / "z.png")           # dossier caché ignoré
        write_png(self.root / "films" / ".cachee.png")      # fichier caché ignoré
        themes = backgrounds.scan_backgrounds(self.root)
        self.assertEqual([t.name for t in themes], ["films", "séries"])
        self.assertEqual([p.name for p in themes[1].images], ["A.PNG", "b.png"])
        self.assertEqual(len(themes[0].images), 1)

    def test_images_a_la_racine_dans_un_theme_divers(self):
        write_png(self.root / "libre.png")
        write_png(self.root / "films" / "x.png")
        self.assertEqual([t.name for t in backgrounds.scan_backgrounds(self.root)], ["films", "Divers"])

    def test_tirage_aleatoire(self):
        write_png(self.root / "a" / "1.png")
        write_png(self.root / "b" / "2.png")
        themes = backgrounds.scan_backgrounds(self.root)
        picks = {backgrounds.random_background(themes, random.Random(i)).name for i in range(20)}
        self.assertEqual(picks, {"1.png", "2.png"})
        self.assertIsNone(backgrounds.random_background([]))


class LoadImageTests(unittest.TestCase):
    def test_chemin_accentue(self):
        with tempfile.TemporaryDirectory(prefix="dé cors ") as tmp:
            path = Path(tmp) / "forêt.png"
            write_png(path, 64, 36, (1, 2, 3))
            image = backgrounds.load_image(path)
            self.assertEqual(image.shape, (36, 64, 3))
            self.assertEqual(tuple(image[0, 0]), (1, 2, 3))

    def test_fichiers_invalides(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "casse.png"
            bad.write_bytes(b"pas une image")
            empty = Path(tmp) / "vide.png"
            empty.write_bytes(b"")
            for path in (bad, empty, Path(tmp) / "absent.png"):
                with self.assertLogs("app.core.backgrounds", level="ERROR"):
                    self.assertIsNone(backgrounds.load_image(path))

    def test_tres_grande_image_reduite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "grande.png"
            write_png(path, 5000, 100)
            self.assertEqual(backgrounds.load_image(path).shape[1], backgrounds.MAX_BACKGROUND_WIDTH)


if __name__ == "__main__":
    unittest.main()
