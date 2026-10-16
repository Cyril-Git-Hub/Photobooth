import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.core.export import HEADER, export_unsent
from app.core.mail_queue import FAILED, GUEST, ORGANIZER, MailQueue

NOW = datetime(2026, 10, 17, 22, 5, 9)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="Photo Booth é ")
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.queue = MailQueue(self.base / "data" / "envois.sqlite3")
        self.exports = self.base / "exports"

    def photo(self, name, content=b"jpeg"):
        path = self.base / "photos" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def add(self, email, first, last, photo, kind=GUEST):
        return self.queue.enqueue(kind, email, photo, first, last, email)

    def rows(self, result):
        with (result.folder / "envois.csv").open(encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f, delimiter=";"))

    def test_rien_a_exporter(self):
        self.assertIsNone(export_unsent(self.queue, self.exports, NOW))
        self.assertFalse(self.exports.exists())                              # pas de dossier vide créé
        sent = self.add("a@x.fr", "A", "B", self.photo("a.jpg")); self.queue.mark_sent(sent)
        self.assertIsNone(export_unsent(self.queue, self.exports, NOW))

    def test_photos_et_tableau(self):
        self.add("lea@gmail.com", "Léa", "Martin", self.photo("1.jpg", b"photo-lea"))
        self.add("hugo@free.fr", "Hugo", "", self.photo("2.jpg", b"photo-hugo"))
        result = export_unsent(self.queue, self.exports, NOW)
        self.assertEqual((result.exported, result.missing), (2, 0))
        self.assertEqual(result.folder, self.exports / "envois-20261017-220509")
        self.assertEqual((result.folder / "001_lea-martin.jpg").read_bytes(), b"photo-lea")
        self.assertEqual((result.folder / "002_hugo.jpg").read_bytes(), b"photo-hugo")
        rows = self.rows(result)
        self.assertEqual(tuple(rows[0]), HEADER)
        self.assertEqual(rows[1][:5], ["lea@gmail.com", "Léa", "Martin", "001_lea-martin.jpg", "en attente"])
        self.assertEqual(rows[2][:5], ["hugo@free.fr", "Hugo", "", "002_hugo.jpg", "en attente"])
        self.assertTrue((result.folder / "LISEZMOI.txt").read_text(encoding="utf-8").startswith("Envois de photos"))

    def test_excel_lit_les_accents_et_le_separateur(self):
        self.add("lea@gmail.com", "Léa", "Martin", self.photo("1.jpg"))
        result = export_unsent(self.queue, self.exports, NOW)
        raw = (result.folder / "envois.csv").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))                      # BOM UTF-8 : Excel affiche « Léa » correctement
        self.assertIn(b";", raw); self.assertEqual(raw.count(b"\r\n"), 2)

    def test_seuls_les_envois_non_partis_aux_invites(self):
        sent = self.add("a@x.fr", "Sent", "", self.photo("a.jpg")); self.queue.mark_sent(sent)
        failed = self.add("b@x.fr", "Failed", "", self.photo("b.jpg")); self.queue.mark_failed(failed, "adresse refusée")
        self.add("c@x.fr", "Pending", "", self.photo("c.jpg"))
        self.add("orga@fete.fr", "Copie", "", self.photo("d.jpg"), kind=ORGANIZER)      # ta propre copie : inutile à exporter
        result = export_unsent(self.queue, self.exports, NOW)
        rows = self.rows(result)
        self.assertEqual([(r[0], r[4]) for r in rows[1:]], [("b@x.fr", "en échec"), ("c@x.fr", "en attente")])
        self.assertEqual(rows[1][5], "adresse refusée")
        self.assertEqual(sorted(p.name for p in result.folder.glob("*.jpg")), ["001_failed.jpg", "002_pending.jpg"])

    def test_photo_introuvable_signalee_sans_bloquer(self):
        self.add("a@x.fr", "A", "", self.photo("a.jpg"))
        gone = self.photo("g.jpg"); self.add("g@x.fr", "Gone", "", gone); gone.unlink()
        result = export_unsent(self.queue, self.exports, NOW)
        self.assertEqual((result.exported, result.missing), (1, 1))
        rows = self.rows(result)
        self.assertEqual(rows[2][3:5], ["", "photo introuvable"])

    def test_deux_exports_la_meme_seconde(self):
        self.add("a@x.fr", "A", "", self.photo("a.jpg"))
        first, second = export_unsent(self.queue, self.exports, NOW), export_unsent(self.queue, self.exports, NOW)
        self.assertNotEqual(first.folder, second.folder)
        self.assertTrue(first.folder.is_dir() and second.folder.is_dir())

    def test_noms_dangereux_dans_excel_neutralises(self):
        self.add("a@x.fr", "=HYPERLINK(\"http://x\")", "+cmd", self.photo("a.jpg"))
        row = self.rows(export_unsent(self.queue, self.exports, NOW))[1]
        self.assertEqual((row[1][0], row[2][0]), ("'", "'"))                   # plus de formule
        self.assertEqual(row[0], "a@x.fr")                                     # l'adresse, elle, reste intacte

    def test_destinataire_commencant_par_un_operateur_excel_est_neutralise(self):
        self.add("+cmd@x.fr", "Plus", "", self.photo("plus.jpg"))
        self.add("-cmd@x.fr", "Moins", "", self.photo("moins.jpg"))
        rows = self.rows(export_unsent(self.queue, self.exports, NOW))[1:]
        self.assertEqual([row[0] for row in rows], ["'+cmd@x.fr", "'-cmd@x.fr"])

    def test_nom_vide_ou_sans_lettres_latines(self):
        self.add("a@x.fr", "", "", self.photo("a.jpg"))
        self.add("b@x.fr", "日本", "", self.photo("b.jpg"))
        result = export_unsent(self.queue, self.exports, NOW)
        self.assertEqual(sorted(p.name for p in result.folder.glob("*.jpg")), ["001_invite.jpg", "002_invite.jpg"])

    def test_l_export_ne_modifie_pas_la_file(self):
        self.add("a@x.fr", "A", "", self.photo("a.jpg"))
        export_unsent(self.queue, self.exports, NOW)
        self.assertEqual(self.queue.counts()["pending"], 1)                    # les envois partiront quand même


if __name__ == "__main__":
    unittest.main()
