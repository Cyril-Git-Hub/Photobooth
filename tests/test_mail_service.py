import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.config import Config
from app.core.mail_queue import FAILED, GUEST, ORGANIZER, PENDING, SENT, MailQueue
from app.core.mail_service import MailService
from app.core.mailer import NetworkError, PermanentMailError, TemporaryMailError


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeSender:
    """Faux SmtpSender : `behaviour(job)` lève une erreur ou renvoie None (= envoyé)."""
    def __init__(self, behaviour=None, configured=True):
        self.behaviour = behaviour or (lambda job: None)
        self.configured = configured
        self.sent, self.attempts = [], []

    def send(self, job, now=None):
        self.attempts.append(job.recipient)
        self.behaviour(job)
        self.sent.append(job.recipient)


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="données é ")
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.config = Config.load(base_dir=self.base)
        self.config.ensure_directories()
        self.config.adresse_organisateur = "orga@fete.fr"
        self.clock = Clock()
        self.queue = MailQueue(self.config.fichier_envois, self.clock)
        self.sender = FakeSender()
        self.reachable = True                       # sonde réseau simulée : aucun test ne doit joindre un vrai serveur
        self.service = MailService(self.config, queue=self.queue, sender_factory=lambda settings: self.sender,
                                   clock=self.clock, poll_seconds=0.05,
                                   connectivity_probe=lambda host, port: self.reachable)
        self.addCleanup(self.service.stop)
        self.photo = self.base / "photo.jpg"
        self.photo.write_bytes(b"jpeg")

    def enqueue(self, email="lea@gmail.com", first="Léa", last="Martin"):
        return self.service.enqueue_photo(self.photo, first, last, email)

    def due(self):
        return [(j.kind, j.recipient) for j in self.queue.due_jobs()]


class EnqueueTests(ServiceCase):
    def test_invite_et_organisateur(self):
        result = self.enqueue()
        self.assertEqual((result.guest, result.organizer, result.configured), (True, True, True))
        self.assertEqual(self.due(), [(GUEST, "lea@gmail.com"), (ORGANIZER, "orga@fete.fr")])
        guest_job, organizer_job = self.queue.due_jobs()
        self.assertEqual((guest_job.guest_name, guest_job.photo_path), ("Léa Martin", self.photo))
        self.assertEqual(organizer_job.guest_email, "lea@gmail.com")          # la copie dit à qui la photo est partie

    def test_invite_sans_adresse_seul_l_organisateur_recoit(self):
        result = self.enqueue(email="")
        self.assertEqual((result.guest, result.organizer), (False, True))
        [job] = self.queue.due_jobs()
        self.assertEqual((job.kind, job.guest_email, job.guest_name), (ORGANIZER, "", "Léa Martin"))

    def test_sans_organisateur(self):
        self.config.adresse_organisateur = ""
        result = self.enqueue()
        self.assertEqual((result.guest, result.organizer), (True, False))
        self.assertEqual(self.due(), [(GUEST, "lea@gmail.com")])

    def test_rien_a_envoyer(self):
        self.config.adresse_organisateur = ""
        result = self.enqueue(email="")
        self.assertEqual((result.guest, result.organizer), (False, False))
        self.assertEqual(self.due(), [])

    def test_meme_adresse_pas_deux_fois(self):
        result = self.enqueue(email="Orga@Fete.fr")
        self.assertEqual((result.guest, result.organizer), (True, False))
        self.assertEqual(self.due(), [(GUEST, "orga@fete.fr")])

    def test_adresses_invalides_ignorees(self):
        self.assertEqual(self.enqueue(email="pas-une-adresse").guest, False)
        self.config.adresse_organisateur = "oups"
        with self.assertLogs("app.core.mail_service", level="WARNING"):
            result = self.enqueue()
        self.assertEqual((result.guest, result.organizer), (True, False))

    def test_adresses_normalisees(self):
        self.enqueue(email="  LEA@Gmail.COM ")
        self.assertEqual(self.due()[0], (GUEST, "lea@gmail.com"))

    def test_non_configure(self):
        self.sender.configured = False
        self.assertFalse(self.enqueue().configured)
        self.assertEqual(len(self.due()), 2)                                  # mis en file quand même

    def test_plusieurs_invites_dans_l_ordre(self):
        self.enqueue("a@x.fr", "A"); self.enqueue("b@x.fr", "B")
        self.assertEqual([r for _, r in self.due()], ["a@x.fr", "orga@fete.fr", "b@x.fr", "orga@fete.fr"])


class ProcessTests(ServiceCase):
    def test_tout_part(self):
        self.enqueue()
        self.assertEqual(self.service.process_due(), 2)
        self.assertEqual(self.sender.sent, ["lea@gmail.com", "orga@fete.fr"])
        stats = self.service.stats()
        self.assertEqual((stats.pending, stats.sent, stats.failed, stats.online, stats.configured), (0, 2, 0, True, True))
        self.assertEqual(self.service.process_due(), 0)                       # rien de nouveau : rien d'envoyé

    def test_echec_definitif_n_arrete_pas_les_autres(self):
        def behaviour(job):
            if job.recipient == "lea@gmail.com":
                raise PermanentMailError("Adresse refusée par le serveur : lea@gmail.com")
        self.sender.behaviour = behaviour
        self.enqueue()
        self.assertEqual(self.service.process_due(), 1)
        stats = self.service.stats()
        self.assertEqual((stats.pending, stats.sent, stats.failed), (0, 1, 1))
        self.assertIn("Adresse refusée", stats.errors[0])
        self.assertEqual(self.sender.attempts, ["lea@gmail.com", "orga@fete.fr"])
        self.assertTrue(stats.online)                                         # le serveur a répondu

    def test_panne_reseau_arrete_le_cycle_et_replanifie(self):
        self.sender.behaviour = lambda job: (_ for _ in ()).throw(NetworkError("pas de réseau"))
        self.enqueue(); self.enqueue("b@x.fr", "B")
        self.assertEqual(self.service.process_due(), 0)
        self.assertEqual(self.sender.attempts, ["lea@gmail.com"])             # une seule tentative : inutile d'insister
        stats = self.service.stats()
        self.assertEqual((stats.pending, stats.online), (4, False))
        self.assertEqual(self.service.process_due(), 0)                       # le premier envoi patiente 20 s...
        self.assertEqual(self.sender.attempts, ["lea@gmail.com", "orga@fete.fr"])   # ...le suivant, lui, est tenté
        self.assertEqual(stats.errors, ("pas de réseau",))

    def test_reessai_apres_le_delai(self):
        state = {"network": True}
        def behaviour(job):
            if state["network"]:
                raise NetworkError("coupé")
        self.sender.behaviour = behaviour
        self.config.adresse_organisateur = ""
        self.enqueue()
        self.service.process_due()
        self.assertEqual(self.due(), [])                                       # en attente de 20 s
        state["network"] = False
        self.clock.now += 21
        self.assertEqual(self.service.process_due(), 1)
        self.assertEqual(self.queue.counts(), {PENDING: 0, SENT: 1, FAILED: 0})

    def test_reseau_revenu_les_delais_sont_supprimes(self):
        errors = {"lea@gmail.com": TemporaryMailError("serveur occupé"), "orga@fete.fr": NetworkError("coupé")}
        def behaviour(job):
            if job.recipient in errors:
                raise errors[job.recipient]
        self.sender.behaviour = behaviour
        self.enqueue(); self.enqueue("c@x.fr", "C")
        # cycle 1 : Léa -> provisoire (reporté), organisateur -> réseau coupé (reporté, cycle interrompu)
        self.service.process_due()
        self.assertEqual(self.service.stats().online, False)
        # les deux premiers envois sont reportés de 20 s ; ceux de C (invité + copie) n'ont pas été touchés
        self.assertEqual(self.due(), [(GUEST, "c@x.fr"), (ORGANIZER, "orga@fete.fr")])
        errors.clear()
        self.clock.now += 10                                                   # moins que les 20 s de délai
        sent = self.service.process_due()                                      # le 1er part -> réseau revenu -> tout est relâché
        self.assertEqual(sent, 4)
        self.assertEqual(self.queue.counts(), {PENDING: 0, SENT: 4, FAILED: 0})
        self.assertTrue(self.service.stats().online)

    def test_refus_provisoire_n_arrete_pas_les_autres(self):
        self.sender.behaviour = lambda job: (_ for _ in ()).throw(TemporaryMailError("451")) if job.kind == GUEST else None
        self.enqueue()
        self.assertEqual(self.service.process_due(), 1)
        self.assertEqual(self.sender.sent, ["orga@fete.fr"])
        self.assertEqual(self.queue.counts(), {PENDING: 1, SENT: 1, FAILED: 0})

    def test_erreur_imprevue_ne_perd_rien(self):
        self.sender.behaviour = lambda job: (_ for _ in ()).throw(RuntimeError("bug"))
        self.config.adresse_organisateur = ""
        self.enqueue()
        with self.assertLogs("app.core.mail_service", level="ERROR"):
            self.assertEqual(self.service.process_due(), 0)
        self.assertEqual(self.queue.counts()[PENDING], 1)

    def test_non_configure_rien_n_est_tente(self):
        self.sender.configured = False
        self.enqueue()
        self.assertEqual(self.service.process_due(), 0)
        self.assertEqual(self.sender.attempts, [])
        stats = self.service.stats()
        self.assertEqual((stats.pending, stats.configured, stats.online), (2, False, None))

    def test_configuration_corrigee_les_envois_en_attente_partent(self):
        self.sender.configured = False
        self.enqueue()
        self.service.process_due()
        self.sender.configured = True                                          # l'organisateur a rempli config.ini
        self.assertEqual(self.service.process_due(), 2)

    def test_renvoyer_les_echecs(self):
        self.sender.behaviour = lambda job: (_ for _ in ()).throw(PermanentMailError("identifiants refusés"))
        self.enqueue()
        self.service.process_due()
        self.assertEqual(self.service.stats().failed, 2)
        self.sender.behaviour = lambda job: None
        self.assertEqual(self.service.requeue_failed(), 2)
        self.assertEqual(self.service.process_due(), 2)
        self.assertEqual(self.service.requeue_failed(), 0)

    def test_survit_a_un_redemarrage(self):
        self.enqueue()
        again = MailService(self.config, queue=MailQueue(self.config.fichier_envois, self.clock),
                            sender_factory=lambda settings: self.sender, clock=self.clock)
        self.assertEqual(again.process_due(), 2)


class ThreadTests(ServiceCase):
    def wait_for(self, condition, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.02)
        return False

    def test_envoi_en_arriere_plan_et_reveil_immediat(self):
        self.service._poll = 30.0                                              # sans réveil, rien ne partirait avant 30 s
        self.service.start()
        time.sleep(0.1)
        self.enqueue()
        self.assertTrue(self.wait_for(lambda: self.service.stats().sent == 2))
        self.service.stop()
        self.assertFalse(self.service._thread.is_alive())

    def test_les_envois_du_disque_partent_au_demarrage(self):
        self.enqueue()
        self.service.start()
        self.assertTrue(self.wait_for(lambda: self.service.stats().sent == 2))

    def test_demarrer_deux_fois_ne_cree_qu_un_thread(self):
        self.service.start(); first = self.service._thread
        self.service.start()
        self.assertIs(self.service._thread, first)
        self.assertEqual(sum(t.name == "envoi-mails" for t in threading.enumerate()), 1)

    def test_arret_idempotent_et_redemarrage(self):
        self.service.stop(); self.service.start(); self.service.stop(); self.service.stop()
        self.service.start()
        self.enqueue()
        self.assertTrue(self.wait_for(lambda: self.service.stats().sent == 2))

    def test_le_thread_survit_a_une_erreur_interne(self):
        calls = {"n": 0}
        original = self.service.process_due
        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return original()
        self.service.process_due = flaky
        self.enqueue()
        with self.assertLogs("app.core.mail_service", level="ERROR"):
            self.service.start()
            self.assertTrue(self.wait_for(lambda: self.service.stats().sent == 2))

    def test_rechargement_des_reglages(self):
        built = []
        service = MailService(self.config, queue=self.queue,
                              sender_factory=lambda settings: built.append(settings) or self.sender, poll_seconds=0.05)
        self.config.expediteur = "nouveau@fete.fr"
        service.reload_settings()
        self.assertEqual([s.sender for s in built], ["", "nouveau@fete.fr"])


if __name__ == "__main__":
    unittest.main()
