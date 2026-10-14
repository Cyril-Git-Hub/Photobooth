import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import cli
from app.config import Config
from tests.smtp_server import FakeSmtpServer

class TesterMailTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config = Config.load(base_dir=Path(self._tmp.name))
        self.config.expediteur = "photo@fete.fr"
        self.config.adresse_organisateur = "orga@fete.fr"
        self.config.mail_securite = "aucune"

    def run_tool(self, *args, port=1):
        self.config.smtp_hote, self.config.smtp_port = "127.0.0.1", port
        out = io.StringIO()
        with mock.patch.object(cli.Config, "load", return_value=self.config), contextlib.redirect_stdout(out):
            code = cli.test_mail(list(args))
        return code, out.getvalue()

    def test_envoi_reussi_a_l_organisateur(self):
        with FakeSmtpServer() as server:
            code, output = self.run_tool(port=server.port)
            [received] = server.messages
        self.assertEqual(code, 0)
        self.assertIn("OK : mail envoyé à orga@fete.fr", output)
        self.assertEqual(received.rcpt_to, ["orga@fete.fr"])
        self.assertNotIn("secret", output)

    def test_destinataire_en_argument(self):
        with FakeSmtpServer() as server:
            code, _ = self.run_tool("Autre@Exemple.fr", port=server.port)
            self.assertEqual(server.messages[0].rcpt_to, ["autre@exemple.fr"])
        self.assertEqual(code, 0)

    def test_mot_de_passe_refuse(self):
        self.config.mot_de_passe_application = "faux"
        with FakeSmtpServer(user="photo@fete.fr", password="bon") as server:
            code, output = self.run_tool(port=server.port)
        self.assertEqual(code, 1)
        self.assertIn("à corriger dans config.ini", output); self.assertIn("mot de passe d'application", output)
        self.assertIn("mot de passe : renseigné", output); self.assertNotIn("faux", output)

    def test_serveur_injoignable(self):
        with FakeSmtpServer() as server:
            port = server.port
        code, output = self.run_tool(port=port)
        self.assertEqual(code, 1); self.assertIn("(réseau)", output)

    def test_non_configure(self):
        self.config.expediteur = ""
        code, output = self.run_tool()
        self.assertEqual(code, 2); self.assertIn("renseigne la section [mail]", output)

    def test_destinataire_invalide_ou_absent(self):
        code, output = self.run_tool("pas-une-adresse")
        self.assertEqual(code, 2); self.assertIn("invalide", output)
        self.config.adresse_organisateur = ""
        code, output = self.run_tool()
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
