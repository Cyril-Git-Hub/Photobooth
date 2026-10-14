import tempfile
import unittest
from datetime import datetime
from unittest import mock
from pathlib import Path

import cv2
import numpy as np

from app.config import Config
from app.core import storage


def make_frame(width=128, height=72):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 2] = np.linspace(0, 255, width, dtype=np.uint8)  # dégradé rouge
    return frame


def read_jpeg(path: Path):
    # np.fromfile gère les chemins accentués, contrairement à cv2.imread sous Windows
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


class SlugifyTests(unittest.TestCase):
    def test_accents_et_espaces(self):
        self.assertEqual(storage.slugify("Léa Martin"), "lea-martin")
        self.assertEqual(storage.slugify("  Jean-Éric O'Neil  "), "jean-eric-o-neil")

    def test_caracteres_interdits_dans_un_nom_de_fichier(self):
        self.assertEqual(storage.slugify('a/b\\c:d*e?"f<g>h|i'), "a-b-c-d-e-f-g-h-i")

    def test_vide_ou_non_latin(self):
        self.assertEqual(storage.slugify(""), "")
        self.assertEqual(storage.slugify("日本語"), "")

    def test_longueur_limitee(self):
        self.assertLessEqual(len(storage.slugify("a" * 200)), 40)


class SavePhotoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="dossier é à ")
        self.addCleanup(self._tmp.cleanup)
        self.config = Config.load(base_dir=Path(self._tmp.name))
        self.now = datetime(2026, 10, 17, 15, 30, 12)

    def test_chemin_et_contenu(self):
        path = storage.save_photo(self.config, make_frame(), "Léa Martin", now=self.now)
        self.assertEqual(path.parent.name, "2026-10-17")
        self.assertEqual(path.name, "153012_lea-martin.jpg")
        image = read_jpeg(path)
        self.assertEqual(image.shape, (72, 128, 3))

    def test_sans_nom_d_invite(self):
        path = storage.save_photo(self.config, make_frame(), now=self.now)
        self.assertEqual(path.name, "153012.jpg")

    def test_deux_photos_dans_la_meme_seconde(self):
        first = storage.save_photo(self.config, make_frame(), "Léa", now=self.now)
        second = storage.save_photo(self.config, make_frame(), "Léa", now=self.now)
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())

    def test_pas_de_fichier_temporaire_restant(self):
        path = storage.save_photo(self.config, make_frame(), now=self.now)
        self.assertEqual([p.name for p in path.parent.iterdir()], [path.name])

    def test_image_invalide_leve_une_erreur(self):
        with self.assertRaises(Exception):
            storage.save_photo(self.config, np.zeros((0, 0, 3), dtype=np.uint8), now=self.now)


class SaveStripTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="dossier é à ")
        self.addCleanup(self._tmp.cleanup)
        self.config = Config.load(base_dir=Path(self._tmp.name))
        self.now = datetime(2026, 10, 17, 15, 30, 12)
        self.strip = make_frame(88, 270)
        self.poses = [make_frame(128, 72) for _ in range(3)]

    def test_bande_et_poses(self):
        strip_path, pose_paths = storage.save_strip(self.config, self.strip, self.poses, "Léa Martin", now=self.now)
        self.assertEqual(strip_path.name, "153012_lea-martin.jpg")
        self.assertEqual(strip_path.parent.name, "2026-10-17")
        self.assertEqual([p.name for p in pose_paths],
                         [f"153012_lea-martin_pose{i}.jpg" for i in (1, 2, 3)])
        self.assertTrue(all(p.parent == strip_path.parent / "poses" for p in pose_paths))
        self.assertEqual(read_jpeg(strip_path).shape, (270, 88, 3))
        self.assertEqual(read_jpeg(pose_paths[0]).shape, (72, 128, 3))

    def test_les_poses_ne_sont_pas_dans_le_dossier_du_jour(self):
        strip_path, _ = storage.save_strip(self.config, self.strip, self.poses, now=self.now)
        self.assertEqual([p.name for p in strip_path.parent.glob("*.jpg")], [strip_path.name])   # un diaporama ne les verra pas

    def test_deux_bandes_dans_la_meme_seconde(self):
        first, _ = storage.save_strip(self.config, self.strip, self.poses, "Léa", now=self.now)
        second, second_poses = storage.save_strip(self.config, self.strip, self.poses, "Léa", now=self.now)
        self.assertNotEqual(first, second)
        self.assertTrue(all(p.exists() for p in second_poses))

    def test_un_echec_ne_laisse_aucun_fichier(self):
        real = storage._write_jpeg
        calls = {"n": 0}
        def failing(frame, dest):
            calls["n"] += 1
            if calls["n"] == 3:                        # bande OK, pose 1 OK, pose 2 en échec
                raise OSError("disque plein")
            real(frame, dest)
        with mock.patch.object(storage, "_write_jpeg", side_effect=failing):
            with self.assertRaises(OSError):
                storage.save_strip(self.config, self.strip, self.poses, "Léa", now=self.now)
        leftovers = [p for p in self.config.dossier_photos.rglob("*") if p.is_file()]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
