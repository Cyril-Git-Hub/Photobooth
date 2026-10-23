import contextlib
import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from app import __version__, cli
from app.config import Config
from app.core.models import MODELS


class ParserTests(unittest.TestCase):
    def parse(self, *argv):
        return cli.build_parser().parse_args(list(argv))

    def test_valeurs_par_defaut(self):
        args = self.parse()
        self.assertEqual((args.windowed, args.version, args.autotest, args.test_mail, args.telecharger_modeles),
                         (False, False, False, None, None))

    def test_test_mail_avec_ou_sans_adresse(self):
        self.assertEqual(self.parse("--test-mail").test_mail, "")
        self.assertEqual(self.parse("--test-mail", "moi@x.fr").test_mail, "moi@x.fr")
        args = self.parse("--test-mail", "--windowed")
        self.assertEqual((args.test_mail, args.windowed), ("", True))

    def test_telechargement(self):
        self.assertEqual(self.parse("--telecharger-modeles").telecharger_modeles, [])
        args = self.parse("--telecharger-modeles", "carre", "paysage", "--force")
        self.assertEqual((args.telecharger_modeles, args.force, args.tous), (["carre", "paysage"], True, False))

    def test_options_de_la_borne(self):
        args = self.parse("--windowed", "--diaporama-fenetre", "--config", "autre.ini")
        self.assertEqual((args.windowed, args.diaporama_fenetre, args.config), (True, True, Path("autre.ini")))

    def test_option_inconnue_refusee(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse("--nimporte-quoi")


class RunToolsTests(unittest.TestCase):
    def run_tools(self, *argv):
        return cli.run_tools(cli.build_parser().parse_args(list(argv)))

    def test_rien_a_faire_lance_la_borne(self):
        self.assertIsNone(self.run_tools()); self.assertIsNone(self.run_tools("--windowed", "--autotest"))

    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.run_tools("--version"), 0)
        self.assertEqual(out.getvalue().strip(), f"Photobooth {__version__}")

    def test_envoi_de_test(self):
        with mock.patch.object(cli, "test_mail", return_value=4) as fake:
            self.assertEqual(self.run_tools("--test-mail"), 4); fake.assert_called_with([])
            self.assertEqual(self.run_tools("--test-mail", "a@b.fr"), 4); fake.assert_called_with(["a@b.fr"])

    def test_telechargement_des_modeles(self):
        with mock.patch.object(cli, "download_models", return_value=0) as fake:
            self.run_tools("--telecharger-modeles"); fake.assert_called_with([])
            self.run_tools("--telecharger-modeles", "carre", "--tous", "--force"); fake.assert_called_with(["carre", "--tous", "--force"])


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="Photobooth é ")
        self.addCleanup(self._tmp.cleanup)
        self.config = Config.load(base_dir=Path(self._tmp.name))
        self.requests = []

    def download(self, *args, payload=b"x" * 60_000, error=None):
        def urlopen(url, timeout=None):
            self.requests.append(url)
            if error:
                raise error
            return io.BytesIO(payload)
        out = io.StringIO()
        with mock.patch.object(cli.Config, "load", return_value=self.config), \
             mock.patch.object(cli.urllib.request, "urlopen", side_effect=urlopen), contextlib.redirect_stdout(out):
            code = cli.download_models(list(args))
        return code, out.getvalue()

    def files(self):
        folder = self.config.dossier_modeles
        return sorted(p.name for p in folder.iterdir()) if folder.exists() else []

    def test_par_defaut_paysage_et_carre(self):
        code, output = self.download()
        self.assertEqual(code, 0)
        self.assertEqual(self.files(), sorted([MODELS["paysage"].filename, MODELS["carre"].filename]))
        self.assertEqual(self.requests, [MODELS["paysage"].url, MODELS["carre"].url])
        self.assertIn("OK", output)

    def test_dossier_models_de_la_configuration(self):
        self.config.dossier_modeles = Path(self._tmp.name) / "mes modèles"
        self.download("carre")
        self.assertEqual([p.name for p in self.config.dossier_modeles.iterdir()], [MODELS["carre"].filename])

    def test_modele_precis_et_tous(self):
        self.download("multiclasse")
        self.assertEqual(self.files(), [MODELS["multiclasse"].filename])
        self.requests.clear()
        self.download("--tous")
        self.assertEqual(len(self.files()), 3); self.assertEqual(self.requests, [MODELS["paysage"].url, MODELS["carre"].url])

    def test_deja_present_pas_retelecharge(self):
        self.download(); self.requests.clear()
        code, output = self.download()
        self.assertEqual((code, self.requests), (0, [])); self.assertIn("déjà présent", output)

    def test_force(self):
        self.download(); self.requests.clear()
        self.download("--force")
        self.assertEqual(len(self.requests), 2)

    def test_modele_inconnu(self):
        code, output = self.download("banane")
        self.assertEqual(code, 2); self.assertEqual(self.requests, []); self.assertIn("paysage, carre, multiclasse", output)

    def test_erreur_reseau_aucun_fichier_a_moitie_ecrit(self):
        code, output = self.download(error=urllib.error.URLError("pas de réseau"))
        self.assertEqual(code, 1); self.assertEqual(self.files(), [])
        self.assertEqual(len(self.requests), 2)                               # les deux modèles ont été tentés
        self.assertIn("connexion internet", output)

    def test_fichier_trop_petit(self):
        code, output = self.download(payload=b"<html>erreur</html>")
        self.assertEqual(code, 1); self.assertEqual(self.files(), []); self.assertIn("trop petit", output)


if __name__ == "__main__":
    unittest.main()
