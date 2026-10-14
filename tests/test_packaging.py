import importlib.util
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from app import __version__, cli, paths
from app.config import DEFAULTS
from app.core.models import MODEL_NAMES

ROOT = Path(__file__).resolve().parent.parent


class FakePyInstaller:
    """Fait tourner photobooth.spec sans PyInstaller et note ce qu'il demande."""
    def __init__(self):
        self.analysis, self.exes, self.collect = None, [], None
        outer = self

        class Analysis:
            def __init__(self, scripts, **kw):
                self.scripts_args, self.kw = scripts, kw
                self.pure, self.scripts, self.binaries, self.datas = ["pure"], ["scripts"], ["bin"], ["data"]
                outer.analysis = self

        class PYZ:
            def __init__(self, pure): self.pure = pure

        class EXE:
            def __init__(self, *args, **kw):
                self.args, self.kw = args, kw
                outer.exes.append(self)

        class COLLECT:
            def __init__(self, *args, **kw):
                self.args, self.kw = args, kw
                outer.collect = self

        self.names = dict(Analysis=Analysis, PYZ=PYZ, EXE=EXE, COLLECT=COLLECT)

    def run(self):
        hooks = types.ModuleType("PyInstaller.utils.hooks")
        hooks.collect_all = lambda package: ([("mediapipe/data.bin", "mediapipe")], [("mediapipe/lib.dll", ".")], ["mediapipe.hidden"])
        modules = {"PyInstaller": types.ModuleType("PyInstaller"), "PyInstaller.utils": types.ModuleType("PyInstaller.utils"),
                   "PyInstaller.utils.hooks": hooks}
        source = (ROOT / "photobooth.spec").read_text(encoding="utf-8")
        with mock.patch.dict(sys.modules, modules):
            exec(compile(source, "photobooth.spec", "exec"), {"SPECPATH": str(ROOT), **self.names})


class SpecTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakePyInstaller()
        self.fake.run()

    def test_deux_programmes_borne_et_outils(self):
        by_name = {e.kw["name"]: e for e in self.fake.exes}
        self.assertEqual(set(by_name), {"photobooth", "photobooth-outils"})
        self.assertFalse(by_name["photobooth"].kw["console"])            # la borne n'affiche pas de console noire
        self.assertTrue(by_name["photobooth-outils"].kw["console"])      # les outils affichent leurs résultats
        for exe in self.fake.exes:
            self.assertTrue(exe.kw["exclude_binaries"])
            self.assertTrue(Path(exe.kw["icon"]).is_file())

    def test_point_d_entree_et_donnees(self):
        a = self.fake.analysis
        self.assertTrue(Path(a.scripts_args[0]).samefile(ROOT / "main.py"))
        icon = ROOT / "assets" / "photobooth.ico"
        self.assertIn((str(icon), "assets"), a.kw["datas"])
        self.assertIn(("mediapipe/data.bin", "mediapipe"), a.kw["datas"])        # données de MediaPipe incluses
        self.assertIn(("mediapipe/lib.dll", "."), a.kw["binaries"])
        self.assertIn("mediapipe.hidden", a.kw["hiddenimports"])
        self.assertIn("tkinter", a.kw["excludes"])

    def test_un_seul_dossier_de_sortie_avec_les_deux_exe(self):
        collect = self.fake.collect
        self.assertEqual(collect.kw["name"], "photobooth")
        self.assertEqual(list(collect.args[:2]), self.fake.exes)

    def test_le_chemin_de_l_icone_correspond_a_resource_path(self):
        self.assertTrue(paths.resource_path("assets/photobooth.ico").is_file())


class BatchFilesTests(unittest.TestCase):
    def read(self, name):
        raw = (ROOT / name).read_bytes()
        raw.decode("ascii")                                              # pas d'accents : sinon affichage de travers sous cmd
        return raw

    def test_fins_de_ligne_windows(self):
        for name in ("construire.bat", "lancer.bat"):
            raw = self.read(name)
            self.assertIn(b"\r\n", raw, name); self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), name)

    def test_lancer_relance_apres_une_erreur_seulement(self):
        text = self.read("lancer.bat").decode()
        self.assertIn('start "" /wait "%~dp0photobooth.exe"', text)
        self.assertIn("if %code% EQU 0 goto fin", text)                  # arrêt normal : on ne relance pas
        self.assertIn("GEQ 5", text)                                     # et pas à l'infini
        self.assertIn("%*", text)

    def test_construire_enchaine_les_bonnes_etapes(self):
        text = self.read("construire.bat").decode()
        for expected in ("requirements-build.txt", "PyInstaller --noconfirm --clean photobooth.spec",
                         "photobooth-outils.exe", "--autotest", "MODE_EMPLOI.md", "lancer.bat", "models"):
            self.assertIn(expected, text)
        for needed in ("photobooth.spec", "requirements-build.txt", "MODE_EMPLOI.md", "lancer.bat", "requirements.txt"):
            self.assertTrue((ROOT / needed).is_file(), needed)

    def test_les_codes_de_sortie_de_main_correspondent_a_lancer(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("EXIT_OK, EXIT_ERROR = 0, 1", source)


class IconTests(unittest.TestCase):
    def test_icone_valide_a_toutes_les_tailles(self):
        with Image.open(ROOT / "assets" / "photobooth.ico") as icon:
            self.assertEqual(set(icon.info["sizes"]), {(n, n) for n in (16, 24, 32, 48, 64, 128, 256)})

    def test_le_script_de_generation_produit_une_icone_valide(self):
        spec = importlib.util.spec_from_file_location("creer_icone", ROOT / "tools" / "creer_icone.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        image = module.draw_icon(128)
        self.assertEqual((image.size, image.mode), ((128, 128), "RGBA"))
        self.assertEqual(image.getpixel((0, 0))[3], 0)                   # coins transparents
        self.assertEqual(image.getpixel((64, 100))[3], 255)


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "MODE_EMPLOI.md").read_text(encoding="utf-8")
        self.flat = {key for section in DEFAULTS.values() for key in section}

    def test_les_reglages_cites_existent(self):
        tokens = set(re.findall(r"`([a-z_]+)(?: = [^`]*)?`", self.text))
        cited = {t for t in tokens if "_" in t} | {"titre", "expediteur", "miroir"} & tokens
        self.assertTrue(cited >= {"code_admin", "ia_modele", "apercu_largeur", "second_ecran_active", "mot_de_passe_application"})
        for key in cited:
            self.assertIn(key, self.flat, f"« {key} » est cité dans MODE_EMPLOI.md mais n'existe pas dans config.ini")

    def test_les_valeurs_citees_sont_valides(self):
        self.assertIn("ia_modele = multiclasse", self.text); self.assertIn("multiclasse", MODEL_NAMES)
        self.assertIn("1234", self.text); self.assertEqual(DEFAULTS["general"]["code_admin"], "1234")

    def test_les_options_en_ligne_de_commande_existent(self):
        parser = cli.build_parser()
        for flag in set(re.findall(r"(--[a-z][a-z-]*)", self.text)):
            self.assertIn(flag, parser._option_string_actions, f"{flag} n'existe pas")

    def test_les_programmes_cites_sont_ceux_du_spec(self):
        spec = (ROOT / "photobooth.spec").read_text(encoding="utf-8")
        for exe in ("photobooth-outils.exe", "lancer.bat"):
            self.assertIn(exe, self.text)
        self.assertIn('name="photobooth-outils"', spec); self.assertIn('name="photobooth"', spec)

    def test_dossiers_cites_crees_par_la_borne(self):
        for name in ("fonds", "photos", "models", "logs", "invites.xlsx", "config.ini"):
            self.assertIn(name, self.text)

    def test_version(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")


class WrapperTests(unittest.TestCase):
    def test_les_scripts_de_tools_appellent_app_cli(self):
        for script, function in (("tester_mail", cli.test_mail), ("telecharger_modele", cli.download_models)):
            spec = importlib.util.spec_from_file_location(script, ROOT / "tools" / f"{script}.py")
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            self.assertIs(module.main, function)


class PathsTests(unittest.TestCase):
    def test_dossier_du_logiciel_dans_l_executable(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", str(ROOT / "dist" / "photobooth" / "photobooth.exe")):
            self.assertEqual(paths.app_dir(), (ROOT / "dist" / "photobooth").resolve())

    def test_dossier_du_logiciel_en_developpement(self):
        self.assertEqual(paths.app_dir(), ROOT)

    def test_ressources_dans_l_executable_et_en_developpement(self):
        self.assertEqual(paths.resource_path("assets/x.ico"), ROOT / "assets" / "x.ico")
        with mock.patch.object(sys, "_MEIPASS", "/opt/photobooth/_internal", create=True):
            self.assertEqual(paths.resource_path("assets/x.ico"), Path("/opt/photobooth/_internal/assets/x.ico"))


if __name__ == "__main__":
    unittest.main()
