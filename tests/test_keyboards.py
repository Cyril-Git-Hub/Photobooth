import string
import unittest

from app.core.keyboards import BACKSPACE, CLEAR, EMAIL_ROWS, SEARCH_ROWS, Key
from app.core.text_buffer import TextBuffer


def keys(rows):
    return [key for row in rows for key in row]


class KeyboardLayoutTests(unittest.TestCase):
    def test_chaque_lettre_une_seule_fois(self):
        for name, rows in (("mail", EMAIL_ROWS), ("recherche", SEARCH_ROWS)):
            letters = [k.label for k in keys(rows) if len(k.label) == 1 and k.label in string.ascii_lowercase]
            self.assertEqual(sorted(letters), list(string.ascii_lowercase), name)

    def test_disposition_azerty(self):
        for rows in (EMAIL_ROWS, SEARCH_ROWS):
            labels = ["".join(k.label for k in row if len(k.label) == 1) for row in rows]
            self.assertTrue(any(row.startswith("azertyuiop") for row in labels))
            self.assertTrue(any(row.startswith("qsdfghjklm") for row in labels))
            self.assertTrue(any(row.startswith("wxcvbn") for row in labels))

    def test_clavier_mail_a_les_touches_utiles(self):
        inserts = {k.insert_text for k in keys(EMAIL_ROWS)}
        self.assertTrue({"@", ".", "-", "_", ".com", ".fr", "@gmail.com"} <= inserts)
        self.assertTrue(set("1234567890") <= inserts)
        self.assertIn(BACKSPACE, keys(EMAIL_ROWS)); self.assertIn(CLEAR, keys(EMAIL_ROWS))

    def test_clavier_recherche(self):
        inserts = {k.insert_text for k in keys(SEARCH_ROWS)}
        self.assertIn(" ", inserts)
        self.assertNotIn("@", inserts)

    def test_touches_d_action_sans_texte(self):
        self.assertEqual((BACKSPACE.insert_text, CLEAR.insert_text), ("", ""))
        self.assertEqual(Key("Espace", text=" ").insert_text, " ")
        self.assertEqual(Key("a").insert_text, "a")

    def test_aucun_caractere_accentue_ni_majuscule(self):
        for key in keys(EMAIL_ROWS):
            if not key.action:
                self.assertEqual(key.insert_text, key.insert_text.lower())
                self.assertTrue(key.insert_text.isascii(), key.label)

    def test_poids_positifs_et_libelles_non_vides(self):
        for key in keys(EMAIL_ROWS) + keys(SEARCH_ROWS):
            self.assertGreater(key.weight, 0); self.assertTrue(key.label)

    def test_on_peut_taper_une_adresse_complete_avec_les_touches(self):
        buffer = TextBuffer()
        by_label = {k.label: k for k in keys(EMAIL_ROWS)}
        for label in ["l", "e", "a", ".", "m", "a", "r", "t", "i", "n", "@gmail.com"]:
            buffer.insert(by_label[label].insert_text)
        self.assertEqual(buffer.value, "lea.martin@gmail.com")


if __name__ == "__main__":
    unittest.main()
