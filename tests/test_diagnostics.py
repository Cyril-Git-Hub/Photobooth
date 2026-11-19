import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from openpyxl import Workbook

from app import diagnostics as dg
from app.config import Config
from app.core.segmentation import SegmentationError
from tests.smtp_server import FakeSmtpServer

GIB = 1e9


def fake_modules(missing=(), no_contrib=False):
    def import_module(name):
        if name in missing:
            raise ImportError(f"No module named '{name}'")
        module = SimpleNamespace(__version__="1.2.3", PYQT_VERSION_STR="6.9")
        if name == "cv2" and not no_contrib:
            module.ximgproc = object()
        return module
    return import_module


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="Photobooth é ")
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.config = Config.load(base_dir=self.base)
        self.config.ensure_directories()
        self.config.fichier_modele_ia.write_bytes(b"modele")
        image = self.config.dossier_fonds / "films" / "decor.jpg"
        image.write_bytes(b"x")
        workbook = Workbook(); sheet = workbook.active
        for row in (["nom", "prénom", "mail"], ["Martin", "Léa", "lea@gmail.com"], ["Dupont", "Camille", None]):
            sheet.append(row)
        workbook.save(self.config.fichier_invites)
        self.config.expediteur, self.config.mot_de_passe_application = "photo@fete.fr", "secret"
        self.config.adresse_organisateur = "orga@fete.fr"
        self.probes = dg.Probes(import_module=fake_modules(), open_camera=lambda c: (1920, 1080),
                                load_model=lambda c: 25.0, can_connect=lambda h, p: True,
                                disk_usage=lambda p: SimpleNamespace(free=50 * GIB))

    def run_checks(self, screens=2):
        return {c.name: c for c in dg.run_checks(self.config, screens, self.probes)}

    def status(self, name, **kw):
        return self.run_checks(**kw)[name].status


class AllGoodTests(Case):
    def test_tout_est_pret(self):
        checks = dg.run_checks(self.config, 2, self.probes)
        self.assertTrue(all(c.status == dg.OK for c in checks), [c for c in checks if c.status != dg.OK])
        self.assertEqual(dg.exit_code(checks), 0)
        self.assertTrue(dg.format_report(checks).endswith("Tout est prêt."))

    def test_toutes_les_rubriques_attendues(self):
        names = set(self.run_checks())
        self.assertTrue({"Logiciel", "Configuration", "Bibliothèques", "Dossier photos", "Dossier données",
                         "Dossier journaux", "Espace disque", "Caméra", "Détourage", "Décors", "Invités", "Mails",
                         "Écrans"} <= names)

    def test_rapport_ecrit_dans_les_logs(self):
        report, code = dg.run(self.config, 2, self.probes)
        self.assertEqual(code, 0)
        self.assertEqual((self.config.dossier_logs / "diagnostic.txt").read_text(encoding="utf-8"), report + "\n")
        self.assertIn("[OK]", report); self.assertIn("1920x1080", report); self.assertIn("2 invité(s), dont 1 avec", report)

    def test_details_utiles(self):
        checks = self.run_checks()
        self.assertIn("25 ms par image", checks["Détourage"].detail)
        self.assertIn("1 image(s) dans 1 thème(s)", checks["Décors"].detail)
        self.assertIn("50.0 Go libres", checks["Espace disque"].detail)
        self.assertIn("Photobooth 1.0.0", checks["Logiciel"].detail)


class LibrariesTests(Case):
    def test_bibliotheque_obligatoire_manquante(self):
        self.probes.import_module = fake_modules(missing={"PyQt6.QtCore"})
        check = self.run_checks()["Bibliothèques"]
        self.assertEqual(check.status, dg.FAIL); self.assertIn("PyQt6", check.detail)
        self.assertEqual(dg.exit_code(dg.run_checks(self.config, 2, self.probes)), 1)

    def test_mediapipe_obligatoire_en_mode_ia(self):
        self.probes.import_module = fake_modules(missing={"mediapipe"})
        self.assertEqual(self.status("Bibliothèques"), dg.FAIL)

    def test_mediapipe_inutile_en_mode_fond_vert(self):
        self.config.mode_detourage = "fond_vert"
        self.probes.import_module = fake_modules(missing={"mediapipe"})
        check = self.run_checks()["Bibliothèques"]
        self.assertEqual(check.status, dg.OK); self.assertIn("non utilisé", check.detail)

    def test_dll_manquante_n_est_pas_une_importerror(self):
        def import_module(name):
            if name == "cv2":
                raise OSError("DLL load failed")
            return SimpleNamespace(__version__="1")
        self.probes.import_module = import_module
        check = self.run_checks()["Bibliothèques"]
        self.assertEqual(check.status, dg.FAIL); self.assertIn("DLL load failed", check.detail)

    def test_opencv_sans_contrib(self):
        self.probes.import_module = fake_modules(no_contrib=True)
        self.assertEqual(self.status("OpenCV contrib"), dg.WARN)


class FoldersAndDiskTests(Case):
    def test_dossier_non_inscriptible(self):
        blocker = self.base / "fichier"; blocker.write_text("x")
        self.config.dossier_photos = blocker / "photos"
        check = self.run_checks()["Dossier photos"]
        self.assertEqual(check.status, dg.FAIL); self.assertIn("écriture impossible", check.detail)

    def test_espace_disque(self):
        for free, expected in [(0.05 * GIB, dg.FAIL), (1 * GIB, dg.WARN), (2 * GIB, dg.OK), (500 * GIB, dg.OK)]:
            self.probes.disk_usage = lambda p, f=free: SimpleNamespace(free=f)
            self.assertEqual(self.status("Espace disque"), expected, free)

    def test_mesure_impossible(self):
        def boom(path): raise OSError("inaccessible")
        self.probes.disk_usage = boom
        self.assertEqual(self.status("Espace disque"), dg.WARN)


class CameraAndModelTests(Case):
    def test_camera_introuvable(self):
        self.probes.open_camera = lambda c: None
        check = self.run_checks()["Caméra"]
        self.assertEqual(check.status, dg.FAIL); self.assertIn("Teams", check.detail)

    def test_camera_en_erreur(self):
        def boom(config): raise RuntimeError("pilote")
        self.probes.open_camera = boom
        self.assertEqual(self.status("Caméra"), dg.FAIL)

    def test_modele_absent(self):
        self.config.fichier_modele_ia.unlink()
        check = self.run_checks()["Détourage"]
        self.assertEqual(check.status, dg.FAIL); self.assertIn("--telecharger-modeles", check.detail)

    def test_modele_illisible(self):
        def boom(config): raise SegmentationError("Le modèle de détourage est illisible :\nfichier corrompu")
        self.probes.load_model = boom
        check = self.run_checks()["Détourage"]
        self.assertEqual(check.status, dg.FAIL); self.assertEqual(check.detail, "Le modèle de détourage est illisible :")

    def test_erreur_imprevue_au_chargement(self):
        def boom(config): raise MemoryError()
        self.probes.load_model = boom
        self.assertEqual(self.status("Détourage"), dg.FAIL)

    def test_modele_lent(self):
        self.probes.load_model = lambda c: 300.0
        check = self.run_checks()["Détourage"]
        self.assertEqual(check.status, dg.WARN); self.assertIn("apercu_largeur", check.detail)

    def test_mode_fond_vert_sans_modele(self):
        self.config.mode_detourage = "fond_vert"
        self.config.fichier_modele_ia.unlink()
        self.probes.load_model = lambda c: self.fail("le modèle ne doit pas être chargé")
        self.assertEqual(self.status("Détourage"), dg.OK)


class ContentTests(Case):
    def test_aucun_decor(self):
        (self.config.dossier_fonds / "films" / "decor.jpg").unlink()
        self.assertEqual(self.status("Décors"), dg.WARN)

    def test_liste_d_invites_absente(self):
        self.config.fichier_invites.unlink()
        self.assertEqual(self.status("Invités"), dg.WARN)

    def test_liste_vide(self):
        workbook = Workbook(); workbook.active.append(["nom", "prénom", "mail"]); workbook.save(self.config.fichier_invites)
        self.assertEqual(self.status("Invités"), dg.WARN)

    def test_liste_illisible(self):
        self.config.fichier_invites.write_text("pas un excel", encoding="utf-8")
        check = self.run_checks()["Invités"]
        self.assertEqual(check.status, dg.FAIL); self.assertIn("Excel", check.detail)


class MailAndScreensTests(Case):
    def test_mail_non_configure(self):
        self.config.expediteur = ""
        self.assertEqual(self.status("Mails"), dg.WARN)

    def test_serveur_injoignable(self):
        self.probes.can_connect = lambda h, p: False
        check = self.run_checks()["Mails"]
        self.assertEqual(check.status, dg.WARN); self.assertIn("injoignable", check.detail)

    def test_remarques_sur_la_configuration_du_mail(self):
        self.config.mot_de_passe_application = ""
        check = self.run_checks()["Mails"]
        self.assertEqual(check.status, dg.WARN); self.assertIn("mot de passe", check.detail)
        self.config.mot_de_passe_application, self.config.adresse_organisateur = "x", ""
        self.assertIn("adresse_organisateur vide", self.run_checks()["Mails"].detail)

    def test_ecrans(self):
        self.assertEqual(self.status("Écrans", screens=2), dg.OK)
        self.assertEqual(self.status("Écrans", screens=1), dg.WARN)
        self.assertNotIn("Écrans", self.run_checks(screens=None))
        self.config.second_ecran_active = False
        self.assertEqual(self.status("Écrans", screens=1), dg.OK)


class BackupCheckTests(Case):
    def test_non_configuree(self):
        check = self.run_checks()["Sauvegarde"]
        self.assertEqual(check.status, dg.OK); self.assertIn("facultatif", check.detail)

    def test_dossier_accessible(self):
        self.config.dossier_sauvegarde = self.base / "clé USB" / "photos"
        check = self.run_checks()["Sauvegarde"]
        self.assertEqual(check.status, dg.OK); self.assertTrue(self.config.dossier_sauvegarde.is_dir())

    def test_destination_injoignable_n_empeche_pas_de_demarrer(self):
        blocker = self.base / "fichier"; blocker.write_text("x")
        self.config.dossier_sauvegarde = blocker / "photos"                    # clé débranchée, par exemple
        check = self.run_checks()["Sauvegarde"]
        self.assertEqual(check.status, dg.WARN); self.assertIn("dès qu'il sera disponible", check.detail)
        self.assertEqual(dg.exit_code(dg.run_checks(self.config, 2, self.probes)), 0)


class ReportTests(Case):
    def test_resume_selon_la_gravite(self):
        ok, warn, fail = dg.Check("a", dg.OK, "x"), dg.Check("b", dg.WARN, "y"), dg.Check("c", dg.FAIL, "z")
        self.assertTrue(dg.format_report([ok]).endswith("Tout est prêt."))
        self.assertIn("1 point(s) d'attention", dg.format_report([ok, warn]))
        self.assertIn("1 problème(s) à corriger", dg.format_report([ok, warn, fail]))
        self.assertEqual((dg.exit_code([ok, warn]), dg.exit_code([fail])), (0, 1))

    def test_marqueurs(self):
        report = dg.format_report([dg.Check("a", dg.OK, "x"), dg.Check("b", dg.WARN, "y"), dg.Check("c", dg.FAIL, "z")])
        for marker in ("[OK]", "[ATTENTION]", "[ECHEC]"):
            self.assertIn(marker, report)

    def test_dossier_de_logs_inaccessible_ne_plante_pas(self):
        blocker = self.base / "bloque"; blocker.write_text("x")
        self.config.base_dir = blocker                                   # logs = fichier/logs : impossible à créer
        report, code = dg.run(self.config, 2, self.probes)
        self.assertIn("Diagnostic Photobooth", report)


class DefaultProbesTests(Case):
    def test_connexion_au_serveur(self):
        with FakeSmtpServer() as server:
            self.assertTrue(dg._default_can_connect("127.0.0.1", server.port))
            port = server.port
        self.assertFalse(dg._default_can_connect("127.0.0.1", port))

    def test_camera(self):
        class Cap:
            def get(self, prop): return {3: 1280.0, 4: 720.0}.get(int(prop), 0.0)
            def release(self): self.released = True
        cap = Cap()
        import cv2
        with mock.patch("app.core.webcam.open_capture", return_value=cap):
            with mock.patch.object(cv2, "CAP_PROP_FRAME_WIDTH", 3), mock.patch.object(cv2, "CAP_PROP_FRAME_HEIGHT", 4):
                self.assertEqual(dg._default_open_camera(self.config), (1280, 720))
        self.assertTrue(cap.released)
        with mock.patch("app.core.webcam.open_capture", return_value=None):
            self.assertIsNone(dg._default_open_camera(self.config))

    def test_chargement_du_modele_mesure_le_temps_et_ferme(self):
        class Segmenter:
            calls, closed = 0, False
            def segment(self, frame): Segmenter.calls += 1
            def close(self): Segmenter.closed = True
        with mock.patch.object(dg, "create_segmenter", return_value=Segmenter()):
            ms = dg._default_load_model(self.config)
        self.assertGreaterEqual(ms, 0); self.assertEqual(Segmenter.calls, 4); self.assertTrue(Segmenter.closed)

    def test_modele_qui_plante_est_quand_meme_ferme(self):
        class Segmenter:
            closed = False
            def segment(self, frame): raise RuntimeError("boom")
            def close(self): Segmenter.closed = True
        with mock.patch.object(dg, "create_segmenter", return_value=Segmenter()):
            with self.assertRaises(RuntimeError):
                dg._default_load_model(self.config)
        self.assertTrue(Segmenter.closed)


if __name__ == "__main__":
    unittest.main()
