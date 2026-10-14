import random
import tempfile
import unittest
from pathlib import Path

from app.core.playlist import Playlist


class PlaylistCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="photos é ")
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def photo(self, name):
        path = self.dir / f"{name}.jpg"
        path.write_bytes(b"x")
        return path

    def names(self, playlist, count):
        return [getattr(playlist.next(), "stem", None) for _ in range(count)]


class ChronologicalTests(PlaylistCase):
    def test_boucle_dans_l_ordre(self):
        playlist = Playlist()
        playlist.load([self.photo(n) for n in "abc"])
        self.assertEqual(self.names(playlist, 7), ["a", "b", "c", "a", "b", "c", "a"])

    def test_vide(self):
        playlist = Playlist()
        self.assertIsNone(playlist.next()); self.assertEqual(len(playlist), 0)

    def test_une_seule_photo(self):
        playlist = Playlist(); playlist.load([self.photo("a")])
        self.assertEqual(self.names(playlist, 3), ["a", "a", "a"])

    def test_la_nouvelle_photo_passe_en_premier_puis_rejoint_la_boucle(self):
        playlist = Playlist()
        playlist.load([self.photo(n) for n in "abc"])
        self.assertEqual(self.names(playlist, 2), ["a", "b"])
        self.assertTrue(playlist.add(self.photo("d")))
        # d s'affiche aussitôt ; la boucle reprend là où elle en était (c) ; d la rejoint en fin de boucle
        self.assertEqual(self.names(playlist, 6), ["d", "c", "d", "a", "b", "c"])

    def test_plusieurs_nouvelles_photos_dans_l_ordre_d_arrivee(self):
        playlist = Playlist(); playlist.load([self.photo("a")])
        playlist.add(self.photo("x")); playlist.add(self.photo("y"))
        self.assertEqual(self.names(playlist, 3), ["x", "y", "a"])

    def test_photo_deja_connue_ignoree(self):
        playlist = Playlist(); a = self.photo("a")
        playlist.load([a])
        self.assertFalse(playlist.add(a)); self.assertEqual(len(playlist), 1)
        self.assertEqual(self.names(playlist, 2), ["a", "a"])                  # pas de passage prioritaire en double

    def test_chargement_sans_doublon(self):
        playlist = Playlist(); a = self.photo("a")
        playlist.load([a, a, self.photo("b"), a])
        self.assertEqual(len(playlist), 2)

    def test_photo_supprimee_du_disque_ignoree(self):
        playlist = Playlist(); a, b, c = (self.photo(n) for n in "abc")
        playlist.load([a, b, c])
        self.assertEqual(self.names(playlist, 1), ["a"])
        b.unlink()
        self.assertEqual(self.names(playlist, 3), ["c", "a", "c"])
        self.assertEqual(len(playlist), 2)

    def test_toutes_les_photos_supprimees(self):
        playlist = Playlist(); photos = [self.photo(n) for n in "ab"]
        playlist.load(photos)
        for p in photos: p.unlink()
        self.assertIsNone(playlist.next()); self.assertEqual(len(playlist), 0)

    def test_nouvelle_photo_supprimee_avant_d_etre_affichee(self):
        playlist = Playlist(); playlist.load([self.photo("a")])
        gone = self.photo("g"); playlist.add(gone); gone.unlink()
        self.assertEqual(self.names(playlist, 2), ["a", "a"])

    def test_retrait_ajuste_la_position(self):
        playlist = Playlist(); a, b, c, d = (self.photo(n) for n in "abcd")
        playlist.load([a, b, c, d])
        self.names(playlist, 3)                                                # a, b, c affichées
        playlist.remove(a)                                                     # retirer une photo déjà passée
        self.assertEqual(self.names(playlist, 3), ["d", "b", "c"])             # on ne saute pas « d »
        playlist.remove(Path("inconnue.jpg"))                                  # sans effet

    def test_vider(self):
        playlist = Playlist(); playlist.load([self.photo("a")]); playlist.add(self.photo("b"))
        playlist.clear()
        self.assertIsNone(playlist.next()); self.assertEqual(len(playlist), 0)

    def test_chemins_accentues(self):
        playlist = Playlist(); p = self.dir / "lèa & zoé.jpg"; p.write_bytes(b"x")
        playlist.load([p]); self.assertEqual(playlist.next(), p)


class RandomTests(PlaylistCase):
    def test_chaque_photo_une_fois_par_tour(self):
        playlist = Playlist("aleatoire", random.Random(1))
        playlist.load([self.photo(n) for n in "abcdef"])
        for _ in range(4):
            self.assertEqual(sorted(self.names(playlist, 6)), list("abcdef"))

    def test_jamais_deux_fois_de_suite_la_meme(self):
        for seed in range(30):
            playlist = Playlist("aleatoire", random.Random(seed))
            playlist.load([self.photo(n) for n in "abc"])
            sequence = self.names(playlist, 30)
            self.assertTrue(all(x != y for x, y in zip(sequence, sequence[1:])), (seed, sequence))

    def test_ordre_reproductible_avec_une_graine(self):
        photos = [self.photo(n) for n in "abcdef"]
        first, second = Playlist("aleatoire", random.Random(7)), Playlist("aleatoire", random.Random(7))
        first.load(photos); second.load(photos)
        self.assertEqual(self.names(first, 12), self.names(second, 12))

    def test_ce_n_est_pas_l_ordre_chronologique(self):
        playlist = Playlist("aleatoire", random.Random(3))
        playlist.load([self.photo(n) for n in "abcdefgh"])
        self.assertNotEqual(self.names(playlist, 8), list("abcdefgh"))

    def test_nouvelle_photo_en_premier_puis_dans_le_tour_suivant(self):
        playlist = Playlist("aleatoire", random.Random(2))
        playlist.load([self.photo(n) for n in "abc"])
        self.names(playlist, 1)
        playlist.add(self.photo("z"))
        self.assertEqual(self.names(playlist, 1), ["z"])
        remaining = self.names(playlist, 2)                                    # fin du tour en cours : a, b, c sans doublon
        self.assertEqual(len(set(remaining)), 2)
        next_round = self.names(playlist, 4)
        self.assertEqual(sorted(next_round), ["a", "b", "c", "z"])             # z fait désormais partie des tours

    def test_photos_supprimees_ecartees(self):
        playlist = Playlist("aleatoire", random.Random(4)); photos = [self.photo(n) for n in "abc"]
        playlist.load(photos); photos[1].unlink()
        self.assertEqual(sorted(self.names(playlist, 2)), ["a", "c"])
        self.assertEqual(len(playlist), 2)

    def test_vide_et_changement_d_ordre(self):
        playlist = Playlist("aleatoire")
        self.assertIsNone(playlist.next())
        playlist.load([self.photo(n) for n in "abc"])
        self.names(playlist, 1)
        playlist.set_order("chronologique")
        self.assertEqual(self.names(playlist, 3), ["a", "b", "c"])
        playlist.set_order("aleatoire")
        self.assertEqual(sorted(self.names(playlist, 3)), ["a", "b", "c"])

if __name__ == "__main__":
    unittest.main()
