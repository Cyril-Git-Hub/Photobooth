"""Échelle de l'interface (app/ui/scale.py), feuille de style, réglage echelle_interface et garde-fou contre les tailles fixes.

Ces tests n'ont pas besoin de PyQt6 : scale.py et theme.py n'importent que la bibliothèque standard.
"""
import ast
import re
import tempfile
import unittest
from pathlib import Path

from app.config import MAX_MANUAL, MIN_MANUAL, Config, complete_missing
from app.ui import scale, theme

UI_DIR = Path(__file__).resolve().parent.parent / "app" / "ui"


class ScaleTestCase(unittest.TestCase):
    """L'échelle est un état global : on la remet à 1.0 après chaque test."""
    def setUp(self):
        scale.set_scale(1.0)
        self.addCleanup(scale.set_scale, 1.0)


class ComputeScaleTests(unittest.TestCase):
    def test_1080p_est_la_reference(self):
        self.assertEqual(scale.compute_scale(1920, 1080), 1.0)

    def test_portable_1366x768(self):
        self.assertAlmostEqual(scale.compute_scale(1366, 768), 0.711, places=3)

    def test_ecran_1280x720(self):
        self.assertAlmostEqual(scale.compute_scale(1280, 720), 0.667, places=3)

    def test_le_rapport_le_plus_contraignant_l_emporte(self):
        self.assertAlmostEqual(scale.compute_scale(1920, 720), 720 / 1080)       # écran large mais bas : la hauteur décide
        self.assertAlmostEqual(scale.compute_scale(1280, 1080), 1280 / 1920)     # écran haut mais étroit : la largeur décide

    def test_borne_basse(self):
        self.assertEqual(scale.compute_scale(800, 600), scale.MIN_SCALE)
        self.assertEqual(scale.compute_scale(1, 1), scale.MIN_SCALE)

    def test_borne_haute(self):
        self.assertEqual(scale.compute_scale(3840, 2160), scale.MAX_SCALE)
        self.assertEqual(scale.compute_scale(2560, 1440), scale.MAX_SCALE)       # 1440 / 1080 = 1.33 : plafonné à 1.3
        self.assertAlmostEqual(scale.compute_scale(2048, 1152), 1152 / 1080)     # 1.067 : sous la borne, non plafonné

    def test_tailles_invalides_donnent_1(self):
        for size in [(0, 0), (0, 1080), (1920, 0), (-1, 768), (1366, -5)]:
            with self.subTest(size=size):
                self.assertEqual(scale.compute_scale(*size), 1.0)

    def test_les_bornes_ont_les_valeurs_documentees(self):
        self.assertEqual((scale.MIN_SCALE, scale.MAX_SCALE), (0.5, 1.3))
        self.assertEqual((scale.MIN_MANUAL, scale.MAX_MANUAL), (0.4, 2.0))


class ResolveTests(unittest.TestCase):
    def test_sans_reglage_manuel_c_est_l_automatique(self):
        self.assertEqual(scale.resolve(None, 1366, 768), scale.compute_scale(1366, 768))

    def test_le_reglage_manuel_prime_sur_l_ecran(self):
        self.assertEqual(scale.resolve(0.8, 1920, 1080), 0.8)
        self.assertEqual(scale.resolve(1.5, 1280, 720), 1.5)

    def test_le_reglage_manuel_est_borne(self):
        self.assertEqual(scale.resolve(0.1, 1920, 1080), scale.MIN_MANUAL)
        self.assertEqual(scale.resolve(9.0, 1920, 1080), scale.MAX_MANUAL)

    def test_le_manuel_peut_depasser_les_bornes_de_l_automatique(self):
        self.assertEqual(scale.resolve(0.45, 1920, 1080), 0.45)                  # < MIN_SCALE (0.5) mais >= MIN_MANUAL (0.4)
        self.assertEqual(scale.resolve(1.8, 1920, 1080), 1.8)                    # > MAX_SCALE (1.3) mais <= MAX_MANUAL (2.0)


class PxTests(ScaleTestCase):
    def test_echelle_1_ne_change_rien(self):
        self.assertEqual([scale.px(v) for v in (1, 22, 90, 260, 1080)], [1, 22, 90, 260, 1080])

    def test_reduction_et_agrandissement(self):
        scale.set_scale(0.5)
        self.assertEqual(scale.px(90), 45)
        scale.set_scale(2.0)
        self.assertEqual(scale.px(90), 180)

    def test_zero_reste_zero(self):
        scale.set_scale(0.5)
        self.assertEqual(scale.px(0), 0)
        self.assertEqual(scale.px(0.0), 0)

    def test_le_reste_vaut_au_moins_un_pixel(self):
        scale.set_scale(0.4)
        self.assertEqual(scale.px(1), 1)
        self.assertEqual(scale.px(2), 1)                                         # 0.8 arrondi à 1, jamais 0 (un trait de 0 px disparaîtrait)

    def test_renvoie_un_entier(self):
        scale.set_scale(0.711)
        self.assertIsInstance(scale.px(30), int)
        self.assertEqual(scale.px(30), 21)
        self.assertIsInstance(scale.px(12.5), int)

    def test_get_et_set(self):
        scale.set_scale(0.75)
        self.assertEqual(scale.get_scale(), 0.75)


class WindowedSizeTests(unittest.TestCase):
    class Screen:
        def __init__(self, w, h): self.w, self.h = w, h
        def availableGeometry(self):
            return type("Area", (), {"width": lambda _, w=self.w: w, "height": lambda _, h=self.h: h})()

    def test_grand_ecran_taille_souhaitee(self):
        self.assertEqual(scale.windowed_size(1280, 720, self.Screen(1920, 1040)), (1280, 720))

    def test_ecran_720p_est_plafonne_a_90_pourcent(self):
        self.assertEqual(scale.windowed_size(1280, 720, self.Screen(1280, 680)), (1152, 612))

    def test_chaque_dimension_est_plafonnee_separement(self):
        self.assertEqual(scale.windowed_size(1280, 720, self.Screen(3000, 600)), (1280, 540))
        self.assertEqual(scale.windowed_size(1280, 720, self.Screen(1000, 2000)), (900, 720))

    def test_sans_ecran_ou_ecran_inutilisable_taille_souhaitee(self):
        self.assertEqual(scale.windowed_size(960, 540, None), (960, 540))
        self.assertEqual(scale.windowed_size(960, 540, object()), (960, 540))
        self.assertEqual(scale.windowed_size(960, 540, self.Screen(0, 0)), (960, 540))


class StylesheetTests(ScaleTestCase):
    def test_valeurs_px_multipliees(self):
        self.assertEqual(scale.scale_stylesheet("a { font-size: 56px; padding: 18px 36px; }", 0.5),
                         "a { font-size: 28px; padding: 9px 18px; }")

    def test_le_reste_est_intact(self):
        text = 'QWidget { color: #14122b; font-weight: 700; font-family: "Segoe UI", sans-serif; background: rgb(1, 2, 3); }'
        self.assertEqual(scale.scale_stylesheet(text, 0.5), text)

    def test_echelle_1_ne_change_rien(self):
        self.assertEqual(scale.scale_stylesheet(theme.STYLESHEET, 1.0), theme.STYLESHEET)

    def test_minimum_un_pixel(self):
        self.assertEqual(scale.scale_stylesheet("x { border: 1px; margin: 2px; }", 0.4), "x { border: 1px; margin: 1px; }")

    def test_sans_argument_utilise_l_echelle_courante(self):
        scale.set_scale(0.5)
        self.assertEqual(scale.scale_stylesheet("x { font-size: 40px; }"), "x { font-size: 20px; }")
        self.assertEqual(scale.scale_stylesheet("x { font-size: 40px; }", 1.0), "x { font-size: 40px; }")   # explicite : prioritaire

    def test_la_feuille_du_theme_est_entierement_mise_a_l_echelle(self):
        sources = [int(n) for n in re.findall(r"(\d+)px", theme.STYLESHEET)]
        self.assertGreater(len(sources), 20)                                      # le thème contient bien des tailles à convertir
        for factor in (0.5, 0.711, 1.3):
            with self.subTest(echelle=factor):
                built = [int(n) for n in re.findall(r"(\d+)px", theme.build_stylesheet(factor))]
                self.assertEqual(built, [max(1, round(n * factor)) for n in sources])
        self.assertEqual(theme.build_stylesheet(0.5).count("px"), theme.STYLESHEET.count("px"))   # aucune valeur ajoutée ni perdue

    def test_build_stylesheet_suit_l_echelle_courante(self):
        scale.set_scale(0.5)
        self.assertIn("QLabel#title   { font-size: 28px;", theme.build_stylesheet())
        scale.set_scale(1.0)
        self.assertIn("QLabel#title   { font-size: 56px;", theme.build_stylesheet())


class ConfigEchelleTests(unittest.TestCase):
    def load(self, ini: str | None) -> Config:
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        if ini is not None:
            (base / "config.ini").write_text(ini, encoding="utf-8")
        return Config.load(base_dir=base)

    def test_automatique_par_defaut(self):
        self.assertIsNone(self.load(None).echelle_interface)

    def test_auto_et_vide_sont_automatiques(self):
        for value in ("auto", "AUTO", ""):
            with self.subTest(value=value):
                self.assertIsNone(self.load(f"[general]\nechelle_interface = {value}\n").echelle_interface)

    def test_valeur_manuelle_point_ou_virgule(self):
        self.assertEqual(self.load("[general]\nechelle_interface = 0.75\n").echelle_interface, 0.75)
        self.assertEqual(self.load("[general]\nechelle_interface = 0,8\n").echelle_interface, 0.8)
        self.assertEqual(self.load("[general]\nechelle_interface = 1\n").echelle_interface, 1.0)

    def test_les_bornes_sont_acceptees(self):
        self.assertEqual(self.load(f"[general]\nechelle_interface = {MIN_MANUAL}\n").echelle_interface, MIN_MANUAL)
        self.assertEqual(self.load(f"[general]\nechelle_interface = {MAX_MANUAL}\n").echelle_interface, MAX_MANUAL)

    def test_valeurs_invalides_ou_hors_limites_retombent_sur_l_automatique_avec_avertissement(self):
        for value in ("beaucoup", "0.3", "2.5", "-1", "0", "1.2.3"):
            with self.subTest(value=value):
                with self.assertLogs("app.config", level="WARNING") as logs:
                    cfg = self.load(f"[general]\nechelle_interface = {value}\n")
                self.assertIsNone(cfg.echelle_interface)
                self.assertTrue(any("echelle_interface" in line for line in logs.output))

    def test_le_fichier_genere_documente_le_reglage(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        Config.load(base_dir=Path(tmp.name))
        text = (Path(tmp.name) / "config.ini").read_text(encoding="utf-8")
        self.assertIn("echelle_interface = auto", text)
        with self.assertNoLogs("app.config", level="WARNING"):
            Config.load(base_dir=Path(tmp.name))                                 # et se relit sans avertissement

    def test_un_ancien_config_recoit_le_reglage(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.ini"
        path.write_text("[general]\nnb_poses = 5\n", encoding="utf-8")
        self.assertIn("general.echelle_interface", complete_missing(path))
        self.assertIn("nb_poses = 5", path.read_text(encoding="utf-8"))
        self.assertIsNone(Config.load(path, base_dir=Path(tmp.name)).echelle_interface)


class NoUnscaledFixedSizeTests(unittest.TestCase):
    """Garde-fou : aucune taille numérique « en dur » dans l'interface (elle doit passer par px()), sinon les boutons du bas
    redeviennent inaccessibles sur un petit écran."""

    SIZE_METHODS = re.compile(r"^(setFixed|setMinimum|setMaximum)(Size|Width|Height)$|^(setSpacing|addSpacing|setContentsMargins|setIconSize"
                              r"|setColumnMinimumWidth|setRowMinimumHeight|setHorizontalSpacing|setVerticalSpacing)$")

    @classmethod
    def violations(cls, source: str, filename: str = "?") -> list[str]:
        found = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if cls.SIZE_METHODS.match(name) or name == "QSize":
                args = list(node.args) + [kw.value for kw in node.keywords]
                if any(isinstance(a, ast.Constant) and isinstance(a.value, (int, float)) and a.value != 0 for a in args):
                    found.append(f"{filename}:{node.lineno} {name}(…) avec une taille numérique non mise à l'échelle")
        return found

    def test_le_detecteur_detecte(self):
        self.assertEqual(len(self.violations("w.setMinimumSize(300, px(80))")), 1)
        self.assertEqual(len(self.violations("g.setSpacing(16)")), 1)
        self.assertEqual(self.violations("w.setMinimumSize(px(300), px(80)); g.setSpacing(0); l.setContentsMargins(0, 0, 0, 0)"), [])

    def test_aucune_taille_fixe_dans_l_interface(self):
        problems = []
        for path in sorted(UI_DIR.rglob("*.py")):
            problems += self.violations(path.read_text(encoding="utf-8"), str(path.relative_to(UI_DIR.parent.parent)))
        self.assertEqual(problems, [])

    def test_aucun_px_en_dur_hors_de_la_feuille_de_style(self):
        for path in sorted(UI_DIR.rglob("*.py")):
            if path.name in ("theme.py", "scale.py"):
                continue
            with self.subTest(fichier=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"\d+px", "feuille de style locale non mise à l'échelle")


if __name__ == "__main__":
    unittest.main()
