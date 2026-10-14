import unittest

from app.core.emails import is_valid_email, mask_email, normalize_email


class EmailTests(unittest.TestCase):
    def test_adresses_valides(self):
        for email in ["lea@gmail.com", "lea.martin@orange.fr", "jean-eric_75+photo@sous.domaine.co.uk",
                      "a@b.co", "  LEA@Gmail.COM  ", "1234@free.fr", "o'neil@x.fr".replace("'", "")]:
            self.assertTrue(is_valid_email(email), email)

    def test_adresses_invalides(self):
        for email in ["", "lea", "lea@", "@gmail.com", "lea@gmail", "lea@gmail.", "lea@.com", "lea@@gmail.com",
                      "le a@gmail.com", "lea@gmail..com", "lea..martin@gmail.com", ".lea@gmail.com", "lea.@gmail.com",
                      "lea@gmail.c", "lea@-gmail.com", "lea@gmail-.com", "léa@gmail.com", "lea@gmail.com,fr",
                      "lea@gmail.com lea@free.fr", "a" * 250 + "@gmail.com"]:
            self.assertFalse(is_valid_email(email), email)

    def test_normalisation(self):
        self.assertEqual(normalize_email("  Léa.Martin@Gmail.COM "), "léa.martin@gmail.com")
        self.assertEqual(normalize_email("LEA@FREE.FR"), "lea@free.fr")


    def test_masquage_pour_l_ecran_de_fin(self):
        self.assertEqual(mask_email("lea.martin@gmail.com"), "l***@gmail.com")
        self.assertEqual(mask_email("  A@B.fr "), "a***@b.fr")
        self.assertEqual(mask_email(""), "")
        self.assertEqual(mask_email("pas-une-adresse"), "")


if __name__ == "__main__":
    unittest.main()
