"""Fonctionnement hors-ligne : la file d'attente survit aux pannes réseau, le réseau est surveillé, tout peut être relancé ou exporté."""
import tempfile
import time
import unittest
from pathlib import Path

from app.core import mail_queue as mq
from app.core.mail_queue import FAILED, GUEST, ORGANIZER, PENDING, SENT, MailQueue
from app.core.mail_service import PROBE_INTERVAL, MailService
from app.core.mailer import NetworkError, TemporaryMailError
from tests.test_mail_service import Clock, FakeSender, ServiceCase


class QueueNetworkTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="données é ")
        self.addCleanup(self._tmp.cleanup)
        self.clock = Clock()
        self.queue = MailQueue(Path(self._tmp.name) / "envois.sqlite3", self.clock)

    def add(self, kind=GUEST, recipient="lea@gmail.com", first="Léa"):
        return self.queue.enqueue(kind, recipient, Path("photo.jpg"), first, "Martin", "lea@gmail.com")

    def attempts(self):
        self.clock.now += 10_000
        return [j.attempts for j in self.queue.due_jobs()]

    def test_une_panne_reseau_n_abandonne_jamais_l_envoi(self):
        job = self.add()
        statuses = {self.queue.mark_retry(job, "coupé", network=True) for _ in range(300)}
        self.assertEqual(statuses, {PENDING})
        self.assertEqual(self.attempts(), [len(mq.RETRY_DELAYS)])              # le compteur plafonne : jamais de limite
        self.assertEqual(self.queue.counts()[FAILED], 0)

    def test_delai_maximal_pendant_une_longue_panne(self):
        job = self.add()
        for _ in range(20):
            self.queue.mark_retry(job, "coupé", network=True)
        self.clock.now += max(mq.RETRY_DELAYS) - 1
        self.assertEqual(self.queue.due_jobs(), [])
        self.clock.now += 2
        self.assertEqual(len(self.queue.due_jobs()), 1)

    def test_une_panne_reseau_n_efface_pas_les_refus_precedents(self):
        job = self.add()
        for _ in range(mq.MAX_ATTEMPTS - 1):
            self.queue.mark_retry(job, "451 réessayez plus tard")
        self.queue.mark_retry(job, "coupé", network=True)
        self.assertEqual(self.attempts(), [mq.MAX_ATTEMPTS - 1])
        self.assertEqual(self.queue.mark_retry(job, "451 encore"), FAILED)     # le dernier refus compte toujours

    def test_les_refus_du_serveur_restent_limites(self):
        job = self.add()
        statuses = [self.queue.mark_retry(job, "451") for _ in range(mq.MAX_ATTEMPTS)]
        self.assertEqual(statuses[-1], FAILED); self.assertEqual(set(statuses[:-1]), {PENDING})

    def test_envois_non_partis(self):
        pending, failed, sent = self.add(first="A"), self.add(first="B"), self.add(first="C")
        organizer = self.add(ORGANIZER, "orga@fete.fr", "A")
        self.queue.mark_failed(failed, "adresse refusée"); self.queue.mark_sent(sent)
        self.queue.mark_retry(pending, "coupé", network=True)
        unsent = self.queue.unsent_jobs(GUEST)
        self.assertEqual([(u.job.guest_first_name, u.status) for u in unsent], [("A", PENDING), ("B", FAILED)])
        self.assertEqual(unsent[0].last_error, "coupé"); self.assertEqual(unsent[1].last_error, "adresse refusée")
        self.assertEqual(unsent[0].created_at, 1000.0)
        self.assertEqual([u.job.id for u in self.queue.unsent_jobs(ORGANIZER)], [organizer])
        self.assertEqual(self.queue.unsent_jobs("autre"), [])


class ProbeTests(ServiceCase):
    def setUp(self):
        super().setUp()
        self.probes = []
        self.service._probe_fn = lambda host, port: self.probes.append((host, port)) or self.reachable

    def go_offline(self):
        self.sender.behaviour = lambda job: (_ for _ in ()).throw(NetworkError("coupé"))
        self.enqueue()
        self.service.process_due()          # le 1er envoi échoue : le cycle s'arrête, le 2e n'a pas encore été tenté
        self.service.process_due()          # le cycle suivant tente (et reporte) le 2e
        self.assertIs(self.service.stats().online, False)

    def test_pas_de_verification_sans_compte_d_envoi(self):
        self.sender.configured = False
        self.service._probe_if_due()
        self.assertEqual(self.probes, [])
        self.assertIsNone(self.service.stats().online)

    def test_la_verification_cible_le_serveur_configure(self):
        self.config.smtp_hote, self.config.smtp_port = "smtp.free.fr", 465
        self.service._probe_if_due()
        self.assertEqual(self.probes, [("smtp.free.fr", 465)])

    def test_en_ligne_connu_avant_tout_envoi(self):
        self.assertIsNone(self.service.stats().online)
        self.service._probe_if_due()
        self.assertIs(self.service.stats().online, True)

    def test_hors_ligne_detecte_avant_tout_envoi(self):
        self.reachable = False
        with self.assertLogs("app.core.mail_service", level="WARNING"):
            self.service._probe_if_due()
        self.assertIs(self.service.stats().online, False)
        self.assertEqual(self.sender.attempts, [])                              # rien n'a été tenté : c'est la sonde qui le sait

    def test_la_panne_n_est_signalee_qu_une_fois(self):
        self.reachable = False
        with self.assertLogs("app.core.mail_service", level="WARNING") as logs:
            self.service.probe(); self.service.probe(); self.service.probe()
        self.assertEqual(len(logs.output), 1)

    def test_intervalle_entre_deux_verifications(self):
        self.service._probe_if_due(); self.service._probe_if_due()
        self.assertEqual(len(self.probes), 1)
        self.clock.now += PROBE_INTERVAL - 1; self.service._probe_if_due()
        self.assertEqual(len(self.probes), 1)
        self.clock.now += 2; self.service._probe_if_due()
        self.assertEqual(len(self.probes), 2)

    def test_reseau_revenu_avec_envois_en_attente_ils_repartent_sans_attendre(self):
        self.go_offline()
        self.assertEqual(self.due(), [])                                        # en attente du prochain essai
        self.reachable = True
        self.service.probe()
        self.assertEqual(len(self.due()), 2)                                    # délais supprimés
        self.assertIs(self.service.stats().online, False)                       # mais seul un vrai envoi dira « en ligne »
        self.sender.behaviour = lambda job: None
        self.assertEqual(self.service.process_due(), 2)
        self.assertIs(self.service.stats().online, True)

    def test_reseau_joignable_mais_envoi_toujours_en_echec_pas_de_faux_en_ligne(self):
        self.go_offline()
        self.reachable = True
        self.service.probe()
        self.service.process_due()                                              # le serveur accepte la connexion mais l'envoi échoue
        self.assertIs(self.service.stats().online, False)

    def test_reseau_revenu_sans_envoi_en_attente(self):
        self.reachable = False
        self.service.probe()
        self.assertIs(self.service.stats().online, False)
        self.reachable = True
        with self.assertLogs("app.core.mail_service", level="INFO"):
            self.service.probe()
        self.assertIs(self.service.stats().online, True)

    def test_coupure_puis_retour_de_bout_en_bout(self):
        self.go_offline()
        self.clock.now += PROBE_INTERVAL + 1                                    # la vérification suivante est due
        self.reachable = True
        self.sender.behaviour = lambda job: None
        self.service._probe_if_due()
        self.assertEqual(self.service.process_due(), 2)
        self.assertEqual(self.service.stats().sent, 2)

    def test_verification_en_arriere_plan(self):
        service = MailService(self.config, queue=self.queue, sender_factory=lambda settings: self.sender,
                              poll_seconds=0.02, probe_interval=0.02,
                              connectivity_probe=lambda host, port: self.reachable)
        self.addCleanup(service.stop)
        service.start()
        self.assertTrue(self.wait_for(lambda: service.stats().online is True))
        self.reachable = False
        self.assertTrue(self.wait_for(lambda: service.stats().online is False))
        self.reachable = True
        self.assertTrue(self.wait_for(lambda: service.stats().online is True))

    @staticmethod
    def wait_for(condition, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.01)
        return False


class RetryAndExportTests(ServiceCase):
    def test_tout_renvoyer_maintenant(self):
        self.sender.behaviour = lambda job: (_ for _ in ()).throw(NetworkError("coupé"))
        self.enqueue()
        self.service.process_due(); self.service.process_due()                  # les deux envois sont reportés
        self.assertEqual(self.due(), [])
        job_id = self.queue.enqueue(GUEST, "x@y.fr", self.photo, "X", "", "x@y.fr")
        self.queue.mark_failed(job_id, "refus")
        self.sender.behaviour = lambda job: None
        self.assertEqual(self.service.retry_now(), 1)                           # 1 échec remis en attente
        self.assertEqual(len(self.due()), 3)                                    # et plus aucun délai
        self.assertEqual(self.service.process_due(), 3)

    def test_export_de_secours(self):
        self.assertIsNone(self.service.export_unsent())                         # rien à exporter
        self.enqueue()
        result = self.service.export_unsent()
        self.assertEqual((result.exported, result.missing), (1, 0))
        self.assertEqual(result.folder.parent, self.config.dossier_exports)
        self.assertTrue((result.folder / "envois.csv").is_file())
        self.assertEqual(self.queue.counts()[PENDING], 2)                       # l'export ne retire rien de la file

    def test_une_longue_coupure_n_abandonne_aucun_envoi(self):
        self.sender.behaviour = lambda job: (_ for _ in ()).throw(NetworkError("coupé"))
        self.enqueue()
        for _ in range(150):
            self.clock.now += 300
            self.service.process_due()
        self.assertEqual(self.queue.counts(), {PENDING: 2, SENT: 0, FAILED: 0})
        self.sender.behaviour = lambda job: None
        self.clock.now += 300
        self.assertEqual(self.service.process_due(), 2)

    def test_les_refus_provisoires_finissent_par_etre_abandonnes(self):
        self.sender.behaviour = lambda job: (_ for _ in ()).throw(TemporaryMailError("451"))
        self.enqueue()
        for _ in range(mq.MAX_ATTEMPTS + 5):
            self.clock.now += 300
            self.service.process_due()
        self.assertEqual(self.queue.counts(), {PENDING: 0, SENT: 0, FAILED: 2})


if __name__ == "__main__":
    unittest.main()
