import unittest

from app.core.text_buffer import TextBuffer


def typed(*chunks, **kwargs):
    buffer = TextBuffer(**kwargs)
    for chunk in chunks:
        buffer.insert(chunk)
    return buffer.value


class TextBufferTests(unittest.TestCase):
    def test_saisie_et_effacement(self):
        buffer = TextBuffer()
        for c in "lea":
            buffer.insert(c)
        self.assertEqual(buffer.value, "lea")
        buffer.backspace(); self.assertEqual(buffer.value, "le")
        buffer.clear(); self.assertEqual(buffer.value, "")
        buffer.backspace(); self.assertEqual(buffer.value, "")           # pas d'erreur sur un champ vide

    def test_une_seule_arobase(self):
        self.assertEqual(typed("lea", "@", "@"), "lea@")
        self.assertEqual(typed("lea", "@", "x", "@"), "lea@x")

    def test_un_domaine_remplace_le_domaine_deja_saisi(self):
        self.assertEqual(typed("lea", "@gmail.com", "@orange.fr"), "lea@orange.fr")
        self.assertEqual(typed("lea", "@", "gma", "@gmail.com"), "lea@gmail.com")
        self.assertEqual(typed("lea", "@gmail.com"), "lea@gmail.com")

    def test_suffixes_et_points(self):
        self.assertEqual(typed("lea@gmail", ".com"), "lea@gmail.com")
        self.assertEqual(typed("lea@orange.", ".fr"), "lea@orange.fr")     # pas de double point
        self.assertEqual(typed(".com"), "")                                 # pas de point en tête
        self.assertEqual(typed("."), "")
        self.assertEqual(typed("lea.", "."), "lea.")

    def test_majuscules_ramenees_en_minuscules(self):
        self.assertEqual(typed("LeA@Gmail.COM"), "lea@gmail.com")

    def test_espaces(self):
        self.assertEqual(typed("le a", " ", "x"), "leax")                   # adresse mail : jamais d'espace
        self.assertEqual(typed("jean", " ", "pierre", allow_space=True), "jean pierre")

    def test_longueur_maximale(self):
        buffer = TextBuffer(max_length=10)
        for c in "abcdefghijklmnop":
            buffer.insert(c)
        self.assertEqual(buffer.value, "abcdefghij")
        buffer.insert("@gmail.com")                                          # ne rentre pas : ignoré en entier
        self.assertEqual(buffer.value, "abcdefghij")

    def test_prerempli_et_set(self):
        buffer = TextBuffer(text="Lea@Gmail.com")
        self.assertEqual(buffer.value, "lea@gmail.com")
        buffer.set("autre@free.fr"); self.assertEqual(buffer.value, "autre@free.fr")
        buffer.set(""); self.assertEqual(buffer.value, "")

    def test_caracteres_de_controle_ignores(self):
        self.assertEqual(typed("a\tb\n", "c\x00"), "abc")


if __name__ == "__main__":
    unittest.main()
