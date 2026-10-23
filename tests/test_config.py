import tempfile
import unittest
from unittest import mock
from pathlib import Path

from app.config import DEFAULTS, TEMPLATE, THEMES_PAR_DEFAUT, Config, complete_missing
from app.session import Session


def write_ini(base: Path, content: str, encoding: str = "utf-8") -> None:
    (base / "config.ini").write_text(content, encoding=encoding)


class ConfigTests(unittest.TestCase):
    def test_fichier_par_defaut_cree(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = Config.load(base_dir=base)
            self.assertTrue((base / "config.ini").exists())
            self.assertEqual(cfg.mode_detourage, "ia")
            self.assertEqual(cfg.nb_poses, 4)
            self.assertEqual(cfg.dossier_photos, base.resolve() / "photos")
            self.assertEqual(cfg.fichier_invites, base.resolve() / "invites.xlsx")

    def test_option_miroir_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = Config.load(base_dir=base)  # défaut : aperçu et photo en miroir
            self.assertTrue(cfg.miroir)
            self.assertFalse(hasattr(cfg, "photo_miroir"))
            write_ini(base, "[general]\nmiroir = no\n")
            cfg.reload()
            self.assertFalse(cfg.miroir)

    def test_anciennes_cles_de_miroir_ignorees(self):
        # un config.ini de l'étape 3 contient apercu_miroir / photo_miroir : sans effet, sans erreur
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[general]\napercu_miroir = false\nphoto_miroir = true\n")
            with self.assertNoLogs("app.config", level="WARNING"):
                cfg = Config.load(base_dir=base)
            self.assertTrue(cfg.miroir)

    def test_options_de_detourage(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = Config.load(base_dir=base)
            self.assertTrue(cfg.apercu_incruste)
            self.assertEqual(cfg.apercu_largeur, 960)
            self.assertFalse(cfg.ia_inverser_masque)
            self.assertEqual(cfg.ia_modele, "paysage")
            self.assertEqual(cfg.fichier_modele_ia, base.resolve() / "models" / "selfie_segmenter_landscape.tflite")
            self.assertEqual((cfg.fv_teinte_min, cfg.fv_teinte_max), (35, 85))
            write_ini(base, "[general]\nia_inverser_masque = true\napercu_incruste = no\n"
                            "[fond_vert]\nteinte_min = 40\nteinte_max = 80\nadoucissement = 5\ndespill = false\n")
            cfg.reload()
            self.assertTrue(cfg.ia_inverser_masque)
            self.assertFalse(cfg.apercu_incruste)
            self.assertEqual((cfg.fv_teinte_min, cfg.fv_teinte_max, cfg.fv_adoucissement), (40, 80, 5))
            self.assertFalse(cfg.fv_despill)

    def test_choix_du_modele_ia(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[general]\nia_modele = CARRE\n[chemins]\ndossier_modeles = mes modeles\n")
            cfg = Config.load(base_dir=base)
            self.assertEqual(cfg.ia_modele, "carre")
            self.assertEqual(cfg.fichier_modele_ia, base.resolve() / "mes modeles" / "selfie_segmenter.tflite")
            write_ini(base, "[general]\nia_modele = banane\n")
            with self.assertLogs("app.config", level="WARNING"):
                self.assertEqual(Config.load(base_dir=base).ia_modele, "paysage")

    def test_ancienne_cle_fichier_modele_ignoree(self):
        # un config.ini de l'étape 4 contient fichier_modele_ia : sans effet, sans erreur
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[chemins]\nfichier_modele_ia = models/selfie_segmenter.tflite\n")
            with self.assertNoLogs("app.config", level="WARNING"):
                cfg = Config.load(base_dir=base)
            self.assertEqual(cfg.fichier_modele_ia.name, "selfie_segmenter_landscape.tflite")

    def test_teintes_incoherentes_et_hors_limites(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[fond_vert]\nteinte_min = 90\nteinte_max = 50\nsaturation_min = 999\nadoucissement = -1\n")
            with self.assertLogs("app.config", level="WARNING"):
                cfg = Config.load(base_dir=base)
            self.assertEqual((cfg.fv_teinte_min, cfg.fv_teinte_max), (35, 85))
            self.assertEqual(cfg.fv_saturation_min, 70)
            self.assertEqual(cfg.fv_adoucissement, 2)

    def test_largeur_d_apercu(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[general]\napercu_largeur = 640\n")
            self.assertEqual(Config.load(base_dir=base).apercu_largeur, 640)
            write_ini(base, "[general]\napercu_largeur = 50\n")
            with self.assertLogs("app.config", level="WARNING"):
                self.assertEqual(Config.load(base_dir=base).apercu_largeur, 960)

    def test_options_photomaton(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = Config.load(base_dir=base)
            self.assertEqual((cfg.nb_poses, cfg.pm_decompte_entre_poses, cfg.pm_titre), (4, 2, ""))
            self.assertEqual((cfg.pm_couleur_fond, cfg.pm_couleur_texte), ("#ffffff", "#1c1c1c"))
            write_ini(base, "[general]\nnb_poses = 5\n[photomaton]\ndecompte_entre_poses = 3\n"
                            "titre = Anniversaire de Léa\ncouleur_fond = #1A1A2E\ncouleur_texte = #FFD166\n")
            cfg.reload()
            self.assertEqual((cfg.nb_poses, cfg.pm_decompte_entre_poses), (5, 3))
            self.assertEqual(cfg.pm_titre, "Anniversaire de Léa")
            self.assertEqual((cfg.pm_couleur_fond, cfg.pm_couleur_texte), ("#1a1a2e", "#ffd166"))

    def test_couleurs_photomaton_invalides(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[photomaton]\ncouleur_fond = rouge\ncouleur_texte = #12345\ndecompte_entre_poses = 0\n")
            with self.assertLogs("app.config", level="WARNING") as logs:
                cfg = Config.load(base_dir=base)
            self.assertEqual((cfg.pm_couleur_fond, cfg.pm_couleur_texte), ("#ffffff", "#1c1c1c"))
            self.assertEqual(cfg.pm_decompte_entre_poses, 2)
            self.assertEqual(len(logs.output), 3)

    def test_mail_obligatoire(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertFalse(Config.load(base_dir=base).mail_obligatoire)
            write_ini(base, "[mail]\nobligatoire = true\n")
            self.assertTrue(Config.load(base_dir=base).mail_obligatoire)

    def test_reglages_du_mail_par_defaut(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config.load(base_dir=Path(tmp))
            self.assertEqual((cfg.mail_securite, cfg.mail_utilisateur, cfg.mail_nom_expediteur), ("auto", "", "Photobooth"))
            self.assertEqual(cfg.mail_objet, "Ta photo du photobooth est prête !")
            self.assertTrue(cfg.mail_message.startswith("{salutation}\n\nTa photo"))     # vrais retours à la ligne
            self.assertEqual(cfg.fichier_envois, Path(tmp).resolve() / "data" / "envois.sqlite3")

    def test_message_du_mail_personnalise(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[mail]\nobjet = Ta photo, {prenom} !\nmessage = Coucou {prenom}\\n\\nVoilà ta photo.\n"
                            "securite = SSL\nutilisateur = compte\nnom_expediteur = Les Photos de Léa\n")
            cfg = Config.load(base_dir=base)
            self.assertEqual(cfg.mail_objet, "Ta photo, {prenom} !")
            self.assertEqual(cfg.mail_message, "Coucou {prenom}\n\nVoilà ta photo.")
            self.assertEqual((cfg.mail_securite, cfg.mail_utilisateur, cfg.mail_nom_expediteur), ("ssl", "compte", "Les Photos de Léa"))

    def test_mail_vide_ou_securite_invalide(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[mail]\nobjet =\nmessage =\nnom_expediteur =\nsecurite = banane\n")
            with self.assertLogs("app.config", level="WARNING"):
                cfg = Config.load(base_dir=base)
            self.assertEqual(cfg.mail_securite, "auto")
            self.assertEqual(cfg.mail_objet, "Ta photo du photobooth est prête !")      # valeurs par défaut conservées
            self.assertIn("{salutation}", cfg.mail_message)
            self.assertEqual(cfg.mail_nom_expediteur, "Photobooth")

    def test_le_fichier_genere_contient_le_message_sur_une_ligne(self):
        with tempfile.TemporaryDirectory() as tmp:
            Config.load(base_dir=Path(tmp))
            text = (Path(tmp) / "config.ini").read_text(encoding="utf-8")
            line = next(l for l in text.splitlines() if l.startswith("message = "))
            self.assertIn("\\n\\n", line)                                                # \n littéraux, pas de vrais sauts de ligne
            with self.assertNoLogs("app.config", level="WARNING"):
                Config.load(base_dir=Path(tmp))

    def test_completion_ajoute_les_reglages_du_mail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            path.write_text("[mail]\nsmtp_hote = smtp.free.fr\nexpediteur = moi@free.fr\nmot_de_passe_application = x\n", encoding="utf-8")
            added = complete_missing(path)
            self.assertIn("mail.message", added); self.assertIn("mail.objet", added); self.assertIn("mail.securite", added)
            cfg = Config.load(path, base_dir=Path(tmp))
            self.assertEqual((cfg.smtp_hote, cfg.expediteur), ("smtp.free.fr", "moi@free.fr"))
            self.assertIn("{salutation}\n\n", cfg.mail_message)                          # le message complété est relu intact

    def test_reglages_du_diaporama(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = Config.load(base_dir=base)
            self.assertEqual((cfg.dp_duree, cfg.dp_ordre, cfg.second_ecran_active), (6, "chronologique", True))
            self.assertEqual(cfg.fichier_diaporama, base.resolve() / "data" / "diaporama.jsonl")
            write_ini(base, "[diaporama]\nduree = 10\nordre = ALEATOIRE\n[general]\nsecond_ecran_active = no\n")
            cfg.reload()
            self.assertEqual((cfg.dp_duree, cfg.dp_ordre, cfg.second_ecran_active), (10, "aleatoire", False))

    def test_diaporama_valeurs_invalides(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[diaporama]\nduree = 1\nordre = banane\n")
            with self.assertLogs("app.config", level="WARNING") as logs:
                cfg = Config.load(base_dir=base)
            self.assertEqual((cfg.dp_duree, cfg.dp_ordre), (6, "chronologique"))
            self.assertEqual(len(logs.output), 2)

    def test_completion_ajoute_la_section_diaporama(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            path.write_text("[general]\nnb_poses = 5\n", encoding="utf-8")
            self.assertIn("[diaporama]", complete_missing(path))
            self.assertEqual(Config.load(path, base_dir=Path(tmp)).dp_duree, 6)

    def test_voyant_sauvegarde_et_exports(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            base = Path(tmp)
            cfg = Config.load(base_dir=base)
            self.assertTrue(cfg.indicateur_organisateur)
            self.assertIsNone(cfg.dossier_sauvegarde)                            # désactivée par défaut
            self.assertEqual(cfg.dossier_exports, base.resolve() / "exports")
            write_ini(base, "[general]\nindicateur_organisateur = no\n[sauvegarde]\ndossier = copies photos\n")
            cfg.reload()
            self.assertFalse(cfg.indicateur_organisateur)
            self.assertEqual(cfg.dossier_sauvegarde, base.resolve() / "copies photos")    # relatif au dossier du logiciel
            write_ini(base, f"[sauvegarde]\ndossier = {other}\n")
            cfg.reload()
            self.assertEqual(cfg.dossier_sauvegarde, Path(other))
            write_ini(base, "[sauvegarde]\ndossier =   \n")
            cfg.reload()
            self.assertIsNone(cfg.dossier_sauvegarde)                            # vide ou espaces : désactivée

    def test_completion_ajoute_la_sauvegarde_et_le_voyant(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            path.write_text("[general]\nnb_poses = 5\n", encoding="utf-8")
            added = complete_missing(path)
            self.assertIn("[sauvegarde]", added); self.assertIn("general.indicateur_organisateur", added)
            cfg = Config.load(path, base_dir=Path(tmp))
            self.assertIsNone(cfg.dossier_sauvegarde); self.assertTrue(cfg.indicateur_organisateur)

    def test_dossier_des_modeles_cree(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config.load(base_dir=Path(tmp))
            cfg.ensure_directories()
            self.assertTrue(cfg.fichier_modele_ia.parent.is_dir())

    def test_ancien_config_sans_les_nouvelles_cles(self):
        # un config.ini créé à l'étape 2 doit continuer à fonctionner
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[general]\nmode_detourage = ia\nnb_poses = 4\n")
            with self.assertNoLogs("app.config", level="WARNING"):
                cfg = Config.load(base_dir=base)
            self.assertTrue(cfg.miroir)

    def test_le_fichier_genere_se_relit_sans_avertissement(self):
        with tempfile.TemporaryDirectory() as tmp:
            Config.load(base_dir=Path(tmp))  # crée le fichier
            with self.assertNoLogs("app.config", level="WARNING"):
                cfg = Config.load(base_dir=Path(tmp))
            self.assertEqual(cfg.inactivite_secondes, 60)

    def test_valeurs_invalides_remplacees_par_defaut(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[general]\nmode_detourage = banane\nnb_poses = abc\n"
                            "duree_decompte = 99\nplein_ecran = peut-etre\n")
            with self.assertLogs("app.config", level="WARNING"):
                cfg = Config.load(base_dir=base)
            self.assertEqual(cfg.mode_detourage, "ia")
            self.assertEqual(cfg.nb_poses, 4)
            self.assertEqual(cfg.duree_decompte, 3)
            self.assertTrue(cfg.plein_ecran)

    def test_fichier_partiel_complete_par_defaut(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[general]\nnb_poses = 5\nmode_detourage = FOND_VERT\n")
            cfg = Config.load(base_dir=base)
            self.assertEqual(cfg.nb_poses, 5)
            self.assertEqual(cfg.mode_detourage, "fond_vert")
            self.assertEqual(cfg.smtp_port, 587)

    def test_chemin_absolu_conserve(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            base = Path(tmp)
            target = Path(other) / "mes photos"
            write_ini(base, f"[chemins]\ndossier_photos = {target}\n")
            cfg = Config.load(base_dir=base)
            self.assertEqual(cfg.dossier_photos, target)

    def test_pourcent_dans_le_mot_de_passe(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[mail]\nmot_de_passe_application = ab%cd\n")
            self.assertEqual(Config.load(base_dir=base).mot_de_passe_application, "ab%cd")

    def test_bom_du_bloc_notes_toleree(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "[general]\nnb_poses = 5\n", encoding="utf-8-sig")
            self.assertEqual(Config.load(base_dir=base).nb_poses, 5)

    def test_fichier_illisible_ne_plante_pas(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_ini(base, "ceci n'est pas un fichier ini\n")
            with self.assertLogs("app.config", level="ERROR"):
                cfg = Config.load(base_dir=base)
            self.assertEqual(cfg.nb_poses, 4)

    def test_reload_en_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = Config.load(base_dir=base)
            write_ini(base, "[general]\nnb_poses = 5\n")
            same_object = cfg
            cfg.reload()
            self.assertIs(cfg, same_object)
            self.assertEqual(cfg.nb_poses, 5)

    def test_creation_des_dossiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config.load(base_dir=Path(tmp))
            cfg.ensure_directories()
            self.assertTrue(cfg.dossier_photos.is_dir())
            self.assertTrue(cfg.dossier_logs.is_dir())
            for theme in THEMES_PAR_DEFAUT:
                self.assertTrue((cfg.dossier_fonds / theme).is_dir())

    def test_les_fonds_existants_ne_sont_pas_touches(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "fonds" / "mon-theme").mkdir(parents=True)
            cfg = Config.load(base_dir=base)
            cfg.ensure_directories()
            self.assertEqual([p.name for p in cfg.dossier_fonds.iterdir()], ["mon-theme"])


STEP2_INI = """# Mon fichier
[general]
# commentaire perso
mode_detourage = fond_vert
nb_poses = 5
code_admin = 9999

[chemins]
dossier_photos = D:/mes photos

[mail]
smtp_hote = smtp.free.fr
expediteur = moi@free.fr
mot_de_passe_application = a%b#c
"""


class CompleteMissingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "config.ini"
        self.path.write_text(STEP2_INI, encoding="utf-8")

    def parsed(self):
        import configparser
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(self.path, encoding="utf-8")
        return parser

    def test_tous_les_reglages_du_modele_apparaissent(self):
        added = complete_missing(self.path)
        self.assertGreater(len(added), 20)
        parser = self.parsed()
        for section, keys in DEFAULTS.items():
            self.assertTrue(parser.has_section(section), section)
            for key in keys:
                self.assertTrue(parser.has_option(section, key), f"{section}.{key}")

    def test_les_valeurs_de_l_utilisateur_sont_intactes(self):
        complete_missing(self.path)
        parser = self.parsed()
        self.assertEqual(parser["general"]["mode_detourage"], "fond_vert")
        self.assertEqual(parser["general"]["nb_poses"], "5")
        self.assertEqual(parser["general"]["code_admin"], "9999")
        self.assertEqual(parser["chemins"]["dossier_photos"], "D:/mes photos")
        self.assertEqual(parser["mail"]["smtp_hote"], "smtp.free.fr")
        self.assertEqual(parser["mail"]["mot_de_passe_application"], "a%b#c")
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Mon fichier\n[general]\n# commentaire perso\n"))   # ses lignes et commentaires

    def test_le_reglage_manquant_va_dans_sa_section(self):
        complete_missing(self.path)
        parser = self.parsed()
        self.assertEqual(parser["general"]["miroir"], "true")             # dans [general], pas à la fin du fichier
        self.assertEqual(parser["chemins"]["dossier_modeles"], "models")
        self.assertEqual(parser["mail"]["obligatoire"], "false")
        self.assertEqual(parser["photomaton"]["decompte_entre_poses"], "2")

    def test_commentaires_du_modele_ajoutes_avec_les_reglages(self):
        complete_missing(self.path)
        self.assertIn("# Image en miroir", self.path.read_text(encoding="utf-8"))

    def test_sauvegarde_de_l_ancienne_version(self):
        complete_missing(self.path)
        self.assertEqual(self.path.with_suffix(".ini.bak").read_text(encoding="utf-8"), STEP2_INI)

    def test_idempotent(self):
        complete_missing(self.path)
        after_first = self.path.read_text(encoding="utf-8")
        self.assertEqual(complete_missing(self.path), [])
        self.assertEqual(self.path.read_text(encoding="utf-8"), after_first)

    def test_charge_ensuite_sans_avertissement_et_memes_valeurs(self):
        before = Config.load(self.path, base_dir=self.path.parent)
        complete_missing(self.path)
        with self.assertNoLogs("app.config", level="WARNING"):
            after = Config.load(self.path, base_dir=self.path.parent)
        for field in ("mode_detourage", "nb_poses", "code_admin", "dossier_photos", "smtp_hote", "expediteur",
                      "mot_de_passe_application"):
            self.assertEqual(getattr(after, field), getattr(before, field), field)

    def test_fichier_genere_par_defaut_deja_complet(self):
        base = Path(self._tmp.name) / "neuf"
        Config.load(base_dir=base)                                         # crée config.ini depuis le modèle
        self.assertEqual(complete_missing(base / "config.ini"), [])
        self.assertFalse((base / "config.ini.bak").exists())

    def test_fichier_absent_ou_illisible_non_touche(self):
        self.assertEqual(complete_missing(self.path.with_name("absent.ini")), [])
        self.path.write_text("ceci n'est pas un ini\n[general\n", encoding="utf-8")
        self.assertEqual(complete_missing(self.path), [])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "ceci n'est pas un ini\n[general\n")

    def test_section_vide_et_fichier_sans_retour_a_la_ligne_final(self):
        self.path.write_text("[general]\n\n[mail]\nsmtp_hote = x", encoding="utf-8")
        complete_missing(self.path)
        parser = self.parsed()
        self.assertEqual(parser["mail"]["smtp_hote"], "x")
        self.assertEqual(parser["general"]["miroir"], "true")
        self.assertTrue(parser.has_section("fond_vert"))

    def test_bom_et_fin_de_ligne_windows(self):
        self.path.write_bytes(("\ufeff" + STEP2_INI.replace("\n", "\r\n")).encode("utf-8"))
        complete_missing(self.path)
        self.assertEqual(self.parsed()["general"]["nb_poses"], "5")

    def test_en_tete_de_section_suivi_d_un_commentaire(self):
        self.path.write_text("[general] # mes réglages\nnb_poses = 5\n[mail]\nsmtp_hote = x\n", encoding="utf-8")
        added = complete_missing(self.path)                   # ne doit pas planter
        self.assertIn("general.miroir", added)
        parser = self.parsed()
        self.assertEqual(parser["general"]["nb_poses"], "5")
        self.assertEqual(parser["general"]["miroir"], "true")

    def test_nom_de_section_avec_espaces_est_une_autre_section(self):
        # configparser (et donc Config.load) ne reconnaît pas « [ general ] » comme [general] : on ne devine pas
        self.path.write_text("[ general ]\nnb_poses = 5\n", encoding="utf-8")
        complete_missing(self.path)
        parser = self.parsed()
        self.assertEqual(parser[" general "]["nb_poses"], "5")      # la ligne de l'utilisateur est conservée telle quelle
        self.assertTrue(parser.has_section("general"))

    def test_une_erreur_imprevue_ne_bloque_jamais_le_demarrage(self):
        before = self.path.read_text(encoding="utf-8")
        with mock.patch("app.config._template_sections", side_effect=RuntimeError("boom")):
            with self.assertLogs("app.config", level="ERROR"):
                self.assertEqual(complete_missing(self.path), [])
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_echec_d_ecriture_ne_bloque_pas(self):
        before = self.path.read_text(encoding="utf-8")
        with mock.patch.object(Path, "write_text", side_effect=OSError("lecture seule")):
            with self.assertLogs("app.config", level="ERROR"):
                self.assertEqual(complete_missing(self.path), [])
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

class SessionTests(unittest.TestCase):
    def test_reset(self):
        s = Session(guest_first_name="Léa", guest_last_name="Martin", email="a@b.fr")
        s.photos.append(Path("x.jpg"))
        self.assertEqual(s.display_name, "Léa Martin")
        s.reset()
        self.assertEqual(s.display_name, "")
        self.assertEqual(s.email, "")
        self.assertEqual(s.photos, [])

    def test_reset_vide_aussi_les_poses(self):
        s = Session(); s.poses.append(Path("pose1.jpg")); s.photo_format = "strip"
        s.reset()
        self.assertEqual((s.poses, s.photo_format), ([], "single"))

    def test_reset_ne_partage_pas_la_liste(self):
        a = Session()
        a.reset()
        a.photos.append(Path("x.jpg"))
        b = Session()
        self.assertEqual(b.photos, [])


if __name__ == "__main__":
    unittest.main()
