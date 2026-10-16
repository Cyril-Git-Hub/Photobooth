import unittest
from types import SimpleNamespace

from app.core.status import ERROR, WARN, build_badge


def mail(configured=True, online=True, pending=0, failed=0):
    return SimpleNamespace(configured=configured, online=online, pending=pending, failed=failed)


def backup(enabled=True, pending=0, last_error=""):
    return SimpleNamespace(enabled=enabled, pending=pending, last_error=last_error)


class BadgeTests(unittest.TestCase):
    def test_rien_a_signaler(self):
        self.assertIsNone(build_badge(mail(), backup()))
        self.assertIsNone(build_badge(mail(online=None), None))                    # état inconnu : pas d'alarme
        self.assertIsNone(build_badge(None, None))

    def test_hors_ligne(self):
        badge = build_badge(mail(online=False), backup())
        self.assertEqual((badge.text, badge.level), ("Hors-ligne", WARN))

    def test_envois_en_attente_singulier_et_pluriel(self):
        self.assertEqual(build_badge(mail(pending=1), None).text, "1 mail en attente")
        self.assertEqual(build_badge(mail(pending=4), None).text, "4 mails en attente")

    def test_hors_ligne_avec_envois_en_attente(self):
        badge = build_badge(mail(online=False, pending=3), None)
        self.assertEqual((badge.text, badge.level), ("Hors-ligne · 3 mails en attente", WARN))

    def test_echec_passe_en_rouge(self):
        badge = build_badge(mail(pending=2, failed=1), None)
        self.assertEqual((badge.text, badge.level), ("2 mails en attente · 1 mail en échec", ERROR))

    def test_mails_non_configures(self):
        self.assertIsNone(build_badge(mail(configured=False), None))               # pas de mails du tout : pas de bruit
        badge = build_badge(mail(configured=False, pending=5, online=False), None)
        self.assertIn("non configurés (5 en attente)", badge.text); self.assertNotIn("Hors-ligne", badge.text)

    def test_sauvegarde_en_panne(self):
        badge = build_badge(mail(), backup(pending=3, last_error="clé absente"))
        self.assertEqual((badge.text, badge.level), ("Sauvegarde en panne (3 photos)", ERROR))
        self.assertIn("1 photo)", build_badge(mail(), backup(pending=1, last_error="x")).text)

    def test_sauvegarde_en_cours_sans_panne_ou_desactivee(self):
        self.assertIsNone(build_badge(mail(), backup(pending=3, last_error="")))   # copie normale en cours
        self.assertIsNone(build_badge(mail(), backup(enabled=False, pending=3, last_error="x")))
        self.assertIsNone(build_badge(mail(), backup(pending=0, last_error="ancienne erreur")))

    def test_tout_en_meme_temps(self):
        badge = build_badge(mail(online=False, pending=2), backup(pending=1, last_error="x"))
        self.assertEqual(badge.text, "Hors-ligne · 2 mails en attente · sauvegarde en panne (1 photo)")
        self.assertEqual(badge.level, ERROR)

    def test_majuscule_au_debut_seulement(self):
        self.assertTrue(build_badge(mail(pending=2), None).text[0].isdigit())
        self.assertEqual(build_badge(mail(online=False), None).text[0], "H")


if __name__ == "__main__":
    unittest.main()
