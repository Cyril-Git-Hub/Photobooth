import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.config import Config
from app.core.backup import BackupService


class BackupCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="Photo Booth é ")
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.config = Config.load(base_dir=self.base)
        self.config.ensure_directories()
        self.dest = self.base / "clé USB" / "sauvegarde"
        self.config.dossier_sauvegarde = self.dest
        self.service = BackupService(self.config, poll_seconds=0.05)
        self.addCleanup(self.service.stop)

    def photo(self, relative, content=b"jpeg"):
        path = self.config.dossier_photos / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def wait_for(self, condition, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.02)
        return False


class ProcessTests(BackupCase):
    def test_copie_avec_l_arborescence(self):
        strip = self.photo("2026-10-17/153012_lea.jpg", b"bande")
        pose = self.photo("2026-10-17/poses/153012_lea_pose1.jpg", b"pose")
        self.service.add([strip, pose])
        self.assertEqual(self.service.process(), 2)
        self.assertEqual((self.dest / "2026-10-17" / "153012_lea.jpg").read_bytes(), b"bande")
        self.assertEqual((self.dest / "2026-10-17" / "poses" / "153012_lea_pose1.jpg").read_bytes(), b"pose")
        stats = self.service.stats()
        self.assertEqual((stats.enabled, stats.copied, stats.pending, stats.last_error), (True, 2, 0, ""))
        self.assertEqual(stats.destination, str(self.dest))

    def test_pas_de_fichier_temporaire_laisse(self):
        self.service.add([self.photo("2026-10-17/a.jpg")]); self.service.process()
        self.assertEqual([p.name for p in (self.dest / "2026-10-17").iterdir()], ["a.jpg"])

    def test_deja_copiee_pas_recopiee(self):
        self.service.add([self.photo("2026-10-17/a.jpg")])
        self.assertEqual(self.service.process(), 1)
        self.service.add([self.config.dossier_photos / "2026-10-17" / "a.jpg"])      # ajoutée une 2e fois
        self.assertEqual(self.service.process(), 0)
        self.assertEqual(self.service.stats().pending, 0)

    def test_taille_differente_recopiee(self):
        photo = self.photo("2026-10-17/a.jpg", b"v1")
        self.service.add([photo]); self.service.process()
        (self.dest / "2026-10-17" / "a.jpg").write_bytes(b"corrompu-et-plus-long")
        again = BackupService(self.config)                                          # « relance du logiciel »
        again.start(); self.addCleanup(again.stop)
        self.assertTrue(self.wait_for(lambda: (self.dest / "2026-10-17" / "a.jpg").read_bytes() == b"v1"))

    def test_destination_injoignable_puis_disponible(self):
        blocker = self.base / "usb"; blocker.write_text("pas un dossier")          # clé « débranchée »
        self.config.dossier_sauvegarde = blocker / "photos"
        photos = [self.photo(f"2026-10-17/{n}.jpg", n.encode()) for n in "abc"]
        self.service.add(photos)
        self.assertEqual(self.service.process(), 0)
        stats = self.service.stats()
        self.assertEqual(stats.pending, 3); self.assertTrue(stats.last_error)
        blocker.unlink()                                                            # la clé est rebranchée
        self.assertEqual(self.service.process(), 3)
        stats = self.service.stats()
        self.assertEqual((stats.pending, stats.last_error, stats.copied), (0, "", 3))
        self.assertEqual((blocker / "photos" / "2026-10-17" / "b.jpg").read_bytes(), b"b")

    def test_panne_au_milieu_les_suivantes_attendent_dans_l_ordre(self):
        first, second = self.photo("2026-10-17/1.jpg"), self.photo("2026-10-17/2.jpg")
        self.service.add([first]); self.service.process()
        blocker = self.base / "usb"; blocker.write_text("x")
        self.config.dossier_sauvegarde = blocker / "p"
        self.service.add([second]); self.service.process()
        self.assertEqual(self.service.stats().pending, 1)

    def test_photo_supprimee_avant_la_copie(self):
        photo = self.photo("2026-10-17/a.jpg")
        self.service.add([photo]); photo.unlink()                                   # « Recommencer »
        self.assertEqual(self.service.process(), 0)
        self.assertEqual(self.service.stats().pending, 0)                           # oubliée sans erreur
        self.assertFalse(self.dest.exists())

    def test_photo_hors_du_dossier_des_photos(self):
        outside = self.base / "ailleurs" / "x.jpg"; outside.parent.mkdir(); outside.write_bytes(b"x")
        self.service.add([outside]); self.service.process()
        self.assertTrue((self.dest / "x.jpg").is_file())

    def test_desactivee_rien_n_est_copie(self):
        self.config.dossier_sauvegarde = None
        self.service.add([self.photo("2026-10-17/a.jpg")])
        self.assertEqual(self.service.process(), 0)
        self.assertFalse(self.service.stats().enabled)

    def test_activee_plus_tard_les_premieres_photos_sont_rattrapees(self):
        self.config.dossier_sauvegarde = None
        self.service.add([self.photo("2026-10-17/a.jpg")]); self.service.process()
        self.config.dossier_sauvegarde = self.dest                                  # activée en cours de soirée
        self.assertEqual(self.service.process(), 1)

    def test_journal_inaccessible_la_copie_a_quand_meme_lieu(self):
        class BrokenJournal:
            def append(self, path): raise OSError("disque plein")
            def load(self): return []
        service = BackupService(self.config, journal=BrokenJournal())
        with self.assertLogs("app.core.backup", level="ERROR"):
            service.add([self.photo("2026-10-17/a.jpg")])
        self.assertEqual(service.process(), 1)


class ThreadTests(BackupCase):
    def test_copie_en_arriere_plan_et_reveil_immediat(self):
        self.service._poll = 30.0                                                   # sans réveil, rien ne partirait avant 30 s
        self.service.start(); time.sleep(0.1)
        self.service.add([self.photo("2026-10-17/a.jpg", b"x")])
        self.assertTrue(self.wait_for(lambda: self.service.stats().copied == 1))
        self.service.stop()
        self.assertFalse(self.service._thread.is_alive())

    def test_reprise_apres_redemarrage(self):
        photos = [self.photo(f"2026-10-17/{n}.jpg") for n in "ab"]
        self.service.add(photos)                                                    # journalisées, jamais copiées
        again = BackupService(self.config, poll_seconds=0.05)
        again.start(); self.addCleanup(again.stop)
        self.assertTrue(self.wait_for(lambda: (self.dest / "2026-10-17" / "b.jpg").is_file()))
        self.assertEqual(again.stats().pending, 0)

    def test_une_seule_instance_du_thread_et_arret_idempotent(self):
        self.service.start(); first = self.service._thread
        self.service.start()
        self.assertIs(self.service._thread, first)
        self.assertEqual(sum(t.name == "sauvegarde-photos" for t in threading.enumerate()), 1)
        self.service.stop(); self.service.stop()

    def test_le_thread_survit_a_une_erreur(self):
        calls = {"n": 0}
        original = self.service.process
        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return original()
        self.service.process = flaky
        self.service.add([self.photo("2026-10-17/a.jpg")])
        with self.assertLogs("app.core.backup", level="ERROR"):
            self.service.start()
            self.assertTrue(self.wait_for(lambda: self.service.stats().copied == 1))

    def test_reessayer_maintenant_reveille_le_thread(self):
        blocker = self.base / "usb"; blocker.write_text("x")
        self.config.dossier_sauvegarde = blocker / "p"
        self.service._poll = 30.0
        self.service.start()
        self.service.add([self.photo("2026-10-17/a.jpg")])
        self.assertTrue(self.wait_for(lambda: self.service.stats().last_error != ""))
        blocker.unlink()
        self.service.retry_now()                                                    # clé rebranchée : pas d'attente de 30 s
        self.assertTrue(self.wait_for(lambda: self.service.stats().copied == 1))


if __name__ == "__main__":
    unittest.main()
