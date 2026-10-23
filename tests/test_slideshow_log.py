import json
import tempfile
import unittest
from pathlib import Path

from app.core.screens import pick_second_screen
from app.core.slideshow_log import SlideshowLog


class SlideshowLogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="Photobooth é ")
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.log = SlideshowLog(self.base / "data" / "diaporama.jsonl", self.base)

    def photo(self, relative):
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path

    def test_ajout_et_relecture_dans_l_ordre(self):
        photos = [self.photo(f"photos/2026-10-17/15300{i}_léa.jpg") for i in range(3)]
        for p in photos: self.log.append(p)
        self.assertEqual(self.log.load(), photos)

    def test_pas_de_fichier(self):
        self.assertEqual(self.log.load(), [])

    def test_chemins_relatifs_le_dossier_peut_changer_de_place(self):
        photo = self.photo("photos/2026-10-17/153000.jpg")
        self.log.append(photo)
        content = self.log.path.read_text(encoding="utf-8")
        self.assertIn('"photos/2026-10-17/153000.jpg"', content); self.assertNotIn(str(self.base), content)
        with tempfile.TemporaryDirectory() as other:                       # « on copie le dossier sur un autre PC »
            moved_base = Path(other).resolve()
            (moved_base / "photos" / "2026-10-17").mkdir(parents=True)
            (moved_base / "photos" / "2026-10-17" / "153000.jpg").write_bytes(b"x")
            (moved_base / "data").mkdir()
            (moved_base / "data" / "diaporama.jsonl").write_text(content, encoding="utf-8")
            moved = SlideshowLog(moved_base / "data" / "diaporama.jsonl", moved_base)
            self.assertEqual(moved.load(), [moved_base / "photos" / "2026-10-17" / "153000.jpg"])

    def test_photo_hors_du_dossier_gardee_en_absolu(self):
        with tempfile.TemporaryDirectory() as outside:
            photo = Path(outside) / "ailleurs.jpg"; photo.write_bytes(b"x")
            self.log.append(photo)
            self.assertEqual(self.log.load(), [photo])

    def test_photos_supprimees_ignorees(self):
        a, b = self.photo("photos/a.jpg"), self.photo("photos/b.jpg")
        self.log.append(a); self.log.append(b)
        a.unlink()
        self.assertEqual(self.log.load(), [b])

    def test_doublons_ecartes(self):
        a = self.photo("photos/a.jpg")
        self.log.append(a); self.log.append(a)
        self.assertEqual(self.log.load(), [a])

    def test_lignes_abimees_ignorees(self):
        a = self.photo("photos/a.jpg")
        self.log.append(a)
        with self.log.path.open("a", encoding="utf-8") as f:
            f.write("n'importe quoi\n{\"autre\": 1}\n[1, 2]\n\n{\"path\": 5}\n")
        self.log.append(self.photo("photos/b.jpg"))
        self.assertEqual([p.name for p in self.log.load()], ["a.jpg", "b.jpg"])

    def test_fichier_illisible(self):
        self.log.path.parent.mkdir(parents=True, exist_ok=True)
        self.log.path.write_bytes(b"\xff\xfe\x00 pas de l'utf-8 \xc3")
        with self.assertLogs("app.core.slideshow_log", level="ERROR"):
            self.assertEqual(self.log.load(), [])

    def test_vider(self):
        self.log.append(self.photo("photos/a.jpg"))
        self.log.clear()
        self.assertEqual(self.log.load(), [])
        self.log.clear()                                                    # sans erreur même sans fichier
        SlideshowLog(self.base / "absent.jsonl", self.base).clear()
        self.log.append(self.photo("photos/b.jpg"))
        self.assertEqual(len(self.log.load()), 1)

    def test_le_journal_est_lisible_avec_les_accents(self):
        self.log.append(self.photo("photos/2026-10-17/153000_léa-martin.jpg"))
        line = self.log.path.read_text(encoding="utf-8").strip()
        self.assertIn("léa-martin", line); self.assertIn("time", json.loads(line))


class PickScreenTests(unittest.TestCase):
    def test_un_seul_ecran(self):
        a = object()
        self.assertIsNone(pick_second_screen([a], a))
        self.assertIsNone(pick_second_screen([], a))

    def test_deux_ecrans(self):
        a, b = object(), object()
        self.assertIs(pick_second_screen([a, b], a), b)
        self.assertIs(pick_second_screen([a, b], b), a)

    def test_trois_ecrans_le_premier_autre_que_la_borne(self):
        a, b, c = object(), object(), object()
        self.assertIs(pick_second_screen([a, b, c], a), b)
        self.assertIs(pick_second_screen([a, b, c], b), a)

    def test_ecran_de_la_borne_inconnu(self):
        a, b = object(), object()
        self.assertIsNone(pick_second_screen([a], None))                    # on ne prend pas le seul écran, qui est celui de la borne
        self.assertIs(pick_second_screen([a, b], None), b)


if __name__ == "__main__":
    unittest.main()
