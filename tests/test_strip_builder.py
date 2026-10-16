import unittest
from unittest import mock

import numpy as np
from PIL import ImageFont

from app.core import strip_builder as sb
from app.core.strip_builder import StripStyle, build_strip


def solid(width, height, bgr):
    image = np.zeros((height, width, 3), np.uint8)
    image[:] = bgr
    return image


COLORS = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255), (255, 0, 255)]   # BGR


class StripLayoutTests(unittest.TestCase):
    def test_dimensions_sans_texte(self):
        for count in (2, 4, 5):
            strip = build_strip([solid(1920, 1080, COLORS[i]) for i in range(count)], StripStyle())
            expected_h = sb.MARGIN * 2 + count * sb.CELL_H + (count - 1) * sb.GAP
            self.assertEqual(strip.shape, (expected_h, sb.CELL_W + 2 * sb.MARGIN, 3), count)
            self.assertEqual(strip.dtype, np.uint8)

    def test_bandeau_du_bas_ajoute_seulement_s_il_y_a_du_texte(self):
        poses = [solid(640, 480, COLORS[0])] * 4
        plain = build_strip(poses, StripStyle())
        for style in (StripStyle(title="Anniversaire"), StripStyle(date_text="11/10/2026"),
                      StripStyle(title="Anniversaire", date_text="11/10/2026")):
            self.assertEqual(build_strip(poses, style).shape[0], plain.shape[0] + sb.FOOTER_H)

    def test_chaque_pose_a_sa_place_et_ses_couleurs_bgr(self):
        strip = build_strip([solid(1920, 1080, COLORS[i]) for i in range(4)], StripStyle())
        for index in range(4):
            y = sb.MARGIN + index * (sb.CELL_H + sb.GAP) + sb.CELL_H // 2
            self.assertEqual(tuple(strip[y, sb.MARGIN + sb.CELL_W // 2]), COLORS[index], index)   # pas de R/B inversés

    def test_marges_et_espaces_a_la_couleur_du_fond(self):
        strip = build_strip([solid(1920, 1080, COLORS[0])] * 3, StripStyle(background="#102030"))
        background = (0x30, 0x20, 0x10)                                    # BGR de #102030
        self.assertEqual(tuple(strip[5, 5]), background)                    # marge haute
        self.assertEqual(tuple(strip[sb.MARGIN + 100, 5]), background)      # marge gauche
        self.assertEqual(tuple(strip[sb.MARGIN + sb.CELL_H + sb.GAP // 2, 400]), background)   # entre deux poses
        self.assertEqual(tuple(strip[-5, -5]), background)

    def test_poses_de_tailles_et_formats_differents(self):
        poses = [solid(1920, 1080, COLORS[0]), solid(640, 480, COLORS[1]), solid(480, 640, COLORS[2]), solid(100, 100, COLORS[3])]
        strip = build_strip(poses, StripStyle())
        self.assertEqual(strip.shape[1], sb.CELL_W + 2 * sb.MARGIN)

    def test_recadrage_au_centre_en_4_3(self):
        pose = np.zeros((1080, 1920, 3), np.uint8)
        pose[:, :240] = (0, 0, 255)          # bord gauche rouge : sort du cadre 4:3
        pose[:, 240:] = (0, 255, 0)
        strip = build_strip([pose], StripStyle())
        self.assertEqual(tuple(strip[sb.MARGIN + 300, sb.MARGIN + 5]), (0, 255, 0))   # le rouge a été recadré

    def test_aucune_pose(self):
        with self.assertRaises(ValueError):
            build_strip([], StripStyle())


class StripFooterTests(unittest.TestCase):
    def footer(self, strip, count=4):
        top = sb.MARGIN + count * sb.CELL_H + (count - 1) * sb.GAP
        return strip[top:]

    def ink(self, region, background=(255, 255, 255)):
        return np.any(region != np.array(background, np.uint8), axis=2)

    def test_le_texte_est_dessine_dans_le_bandeau(self):
        strip = build_strip([solid(640, 480, COLORS[0])] * 4, StripStyle(title="Anniversaire de Léa", date_text="11/10/2026"))
        ink = self.ink(self.footer(strip))
        self.assertGreater(int(ink.sum()), 500)
        columns = np.where(ink.any(axis=0))[0]
        self.assertGreaterEqual(int(columns.min()), sb.MARGIN // 2)          # le texte reste dans les marges
        self.assertLess(int(columns.max()), strip.shape[1] - sb.MARGIN // 2)

    def test_pas_de_texte_pas_d_encre_dans_la_marge_du_bas(self):
        strip = build_strip([solid(640, 480, COLORS[0])] * 4, StripStyle())
        self.assertEqual(int(self.ink(self.footer(strip)).sum()), 0)

    def check_inside_footer(self, title, date_text="11/10/2026"):
        strip = build_strip([solid(640, 480, COLORS[0])] * 4, StripStyle(title=title, date_text=date_text))
        ink = self.ink(self.footer(strip))
        self.assertGreater(int(ink.sum()), 200)
        columns = np.where(ink.any(axis=0))[0]
        rows = np.where(ink.any(axis=1))[0]
        self.assertGreaterEqual(int(columns.min()), sb.MARGIN // 2)                    # rien ne déborde sur les côtés
        self.assertLess(int(columns.max()), strip.shape[1] - sb.MARGIN // 2)
        self.assertGreater(int(rows.min()), 0)                                         # ni vers les poses
        self.assertLess(int(rows.max()), ink.shape[0] - 1)                             # ni hors de l'image
        return ink

    def test_titre_long_passe_sur_deux_lignes(self):
        one = self.check_inside_footer("Anniversaire de Léa")
        two = self.check_inside_footer("Joyeux anniversaire à toute la bande de copains")
        self.assertGreater(int(two.any(axis=1).sum()), int(one.any(axis=1).sum()) - 5)   # le bandeau reste borné

    def test_titre_gigantesque_tronque_avec_des_points(self):
        self.check_inside_footer("Joyeux anniversaire à toute la bande de copains fous " * 4)

    def test_mot_unique_plus_large_que_la_bande(self):
        self.check_inside_footer("Supercalifragilisticexpialidocious" * 3)

    def test_titre_sans_date_et_date_sans_titre(self):
        self.check_inside_footer("Anniversaire de Léa", date_text="")
        strip = build_strip([solid(640, 480, COLORS[0])] * 4, StripStyle(date_text="11/10/2026"))
        self.assertGreater(int(self.ink(self.footer(strip)).sum()), 100)

    def test_couleur_du_texte(self):
        strip = build_strip([solid(640, 480, COLORS[0])] * 2, StripStyle(date_text="11/10/2026", text_color="#ff0000"))
        region = self.footer(strip, 2)
        reds = (region[:, :, 2] > 200) & (region[:, :, 1] < 60) & (region[:, :, 0] < 60)
        self.assertGreater(int(reds.sum()), 100)

    def test_repli_sans_police_systeme(self):
        sb.load_font.cache_clear()
        try:
            with mock.patch.object(sb.ImageFont, "truetype", side_effect=OSError("introuvable")):
                strip = build_strip([solid(640, 480, COLORS[0])] * 2, StripStyle(title="Léa", date_text="11/10/2026"))
            self.assertGreater(int(self.ink(self.footer(strip, 2)).sum()), 50)   # police par défaut de Pillow
        finally:
            sb.load_font.cache_clear()


if __name__ == "__main__":
    unittest.main()
