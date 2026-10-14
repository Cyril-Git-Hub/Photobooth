import tempfile
import threading
import unittest
from pathlib import Path

from app.core import mail_queue as mq
from app.core.mail_queue import FAILED, GUEST, ORGANIZER, PENDING, SENT, MailQueue, retry_delay


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class MailQueueTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="données é ")
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "sous dossier" / "envois.sqlite3"
        self.clock = Clock()
        self.queue = MailQueue(self.path, self.clock)

    def add(self, recipient="lea@gmail.com", kind=GUEST, photo="photo é.jpg", **kw):
        return self.queue.enqueue(kind, recipient, Path(photo), "Léa", "Martin", **kw)

    def test_file_creee_dans_un_dossier_accentue(self):
        self.assertTrue(self.path.exists())
        self.assertEqual(self.queue.counts(), {PENDING: 0, SENT: 0, FAILED: 0})

    def test_enqueue_et_lecture(self):
        job_id = self.add(guest_email="lea@gmail.com")
        [job] = self.queue.due_jobs()
        self.assertEqual((job.id, job.kind, job.recipient, job.attempts), (job_id, GUEST, "lea@gmail.com", 0))
        self.assertEqual((job.guest_first_name, job.guest_last_name, job.guest_name), ("Léa", "Martin", "Léa Martin"))
        self.assertEqual(job.photo_path, Path("photo é.jpg"))
        self.assertEqual(job.guest_email, "lea@gmail.com")

    def test_ordre_d_arrivee(self):
        ids = [self.add(f"a{i}@x.fr") for i in range(5)]
        self.assertEqual([j.id for j in self.queue.due_jobs()], ids)
        self.assertEqual(len(self.queue.due_jobs(limit=2)), 2)

    def test_envoye_n_est_plus_du(self):
        job_id = self.add()
        self.queue.mark_sent(job_id)
        self.assertEqual(self.queue.due_jobs(), [])
        self.assertEqual(self.queue.counts()[SENT], 1)

    def test_echec_temporaire_replanifie_avec_delai(self):
        job_id = self.add()
        self.assertEqual(self.queue.mark_retry(job_id, "réseau coupé"), PENDING)
        self.assertEqual(self.queue.due_jobs(), [])                         # patience : 20 s
        self.clock.now += 19; self.assertEqual(self.queue.due_jobs(), [])
        self.clock.now += 2
        [job] = self.queue.due_jobs()
        self.assertEqual(job.attempts, 1)
        self.assertEqual(self.queue.last_errors(), ["réseau coupé"])

    def test_delais_croissants_puis_plafonnes(self):
        self.assertEqual([retry_delay(n) for n in range(1, 8)], [20, 40, 80, 120, 120, 120, 120])
        self.assertEqual(retry_delay(0), 20)

    def test_abandon_apres_trop_d_essais(self):
        job_id = self.add()
        statuses = [self.queue.mark_retry(job_id, "toujours rien") for _ in range(mq.MAX_ATTEMPTS)]
        self.assertEqual(set(statuses[:-1]), {PENDING}); self.assertEqual(statuses[-1], FAILED)
        self.assertEqual(self.queue.counts()[FAILED], 1)

    def test_echec_definitif(self):
        job_id = self.add()
        self.queue.mark_failed(job_id, "adresse refusée")
        self.assertEqual(self.queue.due_jobs(), [])
        self.assertEqual(self.queue.counts(), {PENDING: 0, SENT: 0, FAILED: 1})
        self.assertEqual(self.queue.last_errors(), ["adresse refusée"])

    def test_remise_en_attente_des_echecs(self):
        failed, sent, pending = self.add("a@x.fr"), self.add("b@x.fr"), self.add("c@x.fr")
        self.queue.mark_failed(failed, "refus"); self.queue.mark_sent(sent)
        self.assertEqual(self.queue.requeue_failed(), 1)
        self.assertEqual(self.queue.counts(), {PENDING: 2, SENT: 1, FAILED: 0})
        self.assertEqual(self.queue.requeue_failed(), 0)
        self.assertEqual([j.recipient for j in self.queue.due_jobs()], ["a@x.fr", "c@x.fr"])

    def test_reseau_revenu_supprime_les_delais(self):
        job_id = self.add()
        self.queue.mark_retry(job_id, "coupé")
        self.assertEqual(self.queue.due_jobs(), [])
        self.queue.make_due_now()
        self.assertEqual(len(self.queue.due_jobs()), 1)

    def test_les_erreurs_des_envois_reussis_ne_sont_pas_remontees(self):
        job_id = self.add()
        self.queue.mark_retry(job_id, "coupé"); self.queue.mark_sent(job_id)
        self.assertEqual(self.queue.last_errors(), [])

    def test_persistance_apres_redemarrage(self):
        self.add("a@x.fr"); self.add("b@x.fr", ORGANIZER)
        again = MailQueue(self.path, self.clock)                          # « nouveau lancement »
        self.assertEqual([(j.recipient, j.kind) for j in again.due_jobs()], [("a@x.fr", GUEST), ("b@x.fr", ORGANIZER)])
        self.assertEqual(again.counts()[PENDING], 2)

    def test_acces_simultanes(self):
        errors = []
        def worker(n):
            try:
                for i in range(20):
                    self.add(f"u{n}-{i}@x.fr")
            except Exception as exc:                                       # pragma: no cover
                errors.append(exc)
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.queue.counts()[PENDING], 100)
        self.assertEqual(len({j.id for j in self.queue.due_jobs(limit=500)}), 100)

    def test_marquer_un_envoi_inexistant_ne_plante_pas(self):
        self.queue.mark_sent(999); self.queue.mark_failed(999, "x")
        self.assertEqual(self.queue.mark_retry(999, "x"), PENDING)


if __name__ == "__main__":
    unittest.main()
