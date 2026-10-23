import email
import smtplib
import socket
import ssl
import tempfile
import unittest
from datetime import datetime
from email import policy
from pathlib import Path
from unittest import mock

from app.core.mail_queue import GUEST, ORGANIZER, MailJob
from app.core.mailer import (
    MSG_AUTH, MailSettings, NetworkError, PermanentMailError, SmtpSender, TemporaryMailError,
    build_message, classify, render, text_to_html,
)
from tests.smtp_server import FakeSmtpServer

NOW = datetime(2026, 10, 17, 15, 30, 12)
SUBJECT = "Ta photo du photobooth est prête !"
BODY = "{salutation}\n\nVoici ta photo du {date}{titre}.\n\nÀ bientôt !"


def settings(**kw):
    base = dict(host="127.0.0.1", port=2525, security="aucune", sender="photo@fete.fr", display_name="Photobooth de Léa",
                organizer="orga@fete.fr", subject_template=SUBJECT, body_template=BODY, event_title="")
    base.update(kw)
    return MailSettings(**base)


class WithPhoto(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="photos é ")
        self.addCleanup(self._tmp.cleanup)
        self.photo = Path(self._tmp.name) / "153012_lea-martin.jpg"
        self.photo.write_bytes(b"\xff\xd8\xff\xe0FAKE-JPEG-DATA\xff\xd9")

    def job(self, kind=GUEST, recipient="lea@gmail.com", first="Léa", last="Martin", guest_email="lea@gmail.com", photo=None):
        return MailJob(1, kind, recipient, first, last, guest_email, photo or self.photo, 0)


class RenderTests(unittest.TestCase):
    def test_variables(self):
        self.assertEqual(render("{a} et {b}", {"a": "x", "b": "y"}), "x et y")

    def test_variable_inconnue_laissee_telle_quelle(self):
        self.assertEqual(render("Salut {prenom} {inconnue}", {"prenom": "Léa"}), "Salut Léa {inconnue}")

    def test_accolades_mal_formees(self):
        for template in ["Salut {prenom", "Salut }", "{0}", "{prenom!x}"]:
            self.assertEqual(render(template, {"prenom": "Léa"}), template)

    def test_html_echappe(self):
        out = text_to_html("Salut <b>Léa</b> & co\nligne 2\n\nParagraphe 2")
        self.assertIn("&lt;b&gt;Léa&lt;/b&gt; &amp; co<br>ligne 2", out)
        self.assertEqual(out.count("<p "), 2)
        self.assertNotIn("<b>", out)


class BuildMessageTests(WithPhoto):
    def parse(self, message):
        return email.message_from_bytes(message.as_bytes(), policy=policy.default)

    def test_mail_invite(self):
        msg = self.parse(build_message(settings(event_title=""), self.job(), NOW))
        self.assertEqual(msg["Subject"], SUBJECT)
        self.assertEqual(msg["From"], "Photobooth de Léa <photo@fete.fr>")
        self.assertEqual(msg["To"], "Léa Martin <lea@gmail.com>")
        self.assertIn("@fete.fr>", msg["Message-ID"])
        plain = msg.get_body(preferencelist=("plain",)).get_content()
        self.assertTrue(plain.startswith("Salut Léa !\n\nVoici ta photo du 17/10/2026."))
        html = msg.get_body(preferencelist=("html",)).get_content()
        self.assertIn("Salut Léa !", html)

    def test_piece_jointe(self):
        msg = self.parse(build_message(settings(), self.job(), NOW))
        [attachment] = list(msg.iter_attachments())
        self.assertEqual(attachment.get_content_type(), "image/jpeg")
        self.assertEqual(attachment.get_filename(), "photobooth_153012_lea-martin.jpg")
        self.assertEqual(attachment.get_content(), b"\xff\xd8\xff\xe0FAKE-JPEG-DATA\xff\xd9")

    def test_salutation_sans_prenom(self):
        msg = self.parse(build_message(settings(), self.job(first="", last="", guest_email=""), NOW))
        self.assertEqual(msg["To"], "lea@gmail.com")
        self.assertTrue(msg.get_body(preferencelist=("plain",)).get_content().startswith("Salut !\n\n"))

    def test_titre_de_la_fete(self):
        msg = self.parse(build_message(settings(event_title=" de Léa"), self.job(), NOW))
        self.assertIn("du 17/10/2026 de Léa.", msg.get_body(preferencelist=("plain",)).get_content())

    def test_variables_personnalisees(self):
        s = settings(subject_template="Photo de {nom_complet}", body_template="{prenom} / {nom} / {date}")
        msg = self.parse(build_message(s, self.job(), NOW))
        self.assertEqual(msg["Subject"], "Photo de Léa Martin")
        self.assertEqual(msg.get_body(preferencelist=("plain",)).get_content().strip(), "Léa / Martin / 17/10/2026")

    def test_prenom_avec_caracteres_speciaux_echappes_en_html(self):
        msg = self.parse(build_message(settings(), self.job(first="<script>"), NOW))
        html = msg.get_body(preferencelist=("html",)).get_content()
        self.assertNotIn("<script>", html); self.assertIn("&lt;script&gt;", html)

    def test_objet_sur_une_ligne(self):
        msg = self.parse(build_message(settings(subject_template="Ligne 1\nLigne 2"), self.job(), NOW))
        self.assertEqual(msg["Subject"], "Ligne 1 Ligne 2")

    def test_copie_organisateur_avec_adresse_invite(self):
        msg = self.parse(build_message(settings(), self.job(ORGANIZER, "orga@fete.fr"), NOW))
        self.assertEqual(msg["To"], "orga@fete.fr")
        self.assertEqual(msg["Subject"], "[Photobooth] Léa Martin")
        self.assertIn("envoyée à lea@gmail.com", msg.get_body(preferencelist=("plain",)).get_content())
        self.assertEqual(len(list(msg.iter_attachments())), 1)

    def test_copie_organisateur_sans_adresse_invite(self):
        msg = self.parse(build_message(settings(), self.job(ORGANIZER, "orga@fete.fr", "", "", ""), NOW))
        self.assertEqual(msg["Subject"], "[Photobooth] invité sans nom")
        self.assertIn("pas donné d'adresse mail", msg.get_body(preferencelist=("plain",)).get_content())

    def test_photo_introuvable_est_definitif(self):
        with self.assertRaises(PermanentMailError) as ctx:
            build_message(settings(), self.job(photo=self.photo.with_name("absente.jpg")), NOW)
        self.assertIn("absente.jpg", str(ctx.exception))

    def test_adresse_destinataire_invalide_est_definitif(self):
        with self.assertRaises(PermanentMailError):
            build_message(settings(), self.job(recipient="pas une adresse <>"), NOW)


class ClassifyTests(unittest.TestCase):
    def test_classement(self):
        cases = [
            (smtplib.SMTPAuthenticationError(535, b"bad"), PermanentMailError),
            (smtplib.SMTPRecipientsRefused({"a@x.fr": (550, b"no such user")}), PermanentMailError),
            (smtplib.SMTPRecipientsRefused({"a@x.fr": (451, b"later")}), TemporaryMailError),
            (smtplib.SMTPSenderRefused(553, b"sender not allowed", "x@y.fr"), PermanentMailError),
            (smtplib.SMTPDataError(552, b"message too large"), PermanentMailError),
            (smtplib.SMTPDataError(451, b"try later"), TemporaryMailError),
            (smtplib.SMTPResponseException(421, b"service unavailable"), TemporaryMailError),
            (smtplib.SMTPNotSupportedError("STARTTLS not supported"), PermanentMailError),
            (smtplib.SMTPServerDisconnected("closed"), NetworkError),
            (smtplib.SMTPConnectError(421, b"busy"), NetworkError),
            (ConnectionRefusedError(), NetworkError),
            (TimeoutError("timed out"), NetworkError),
            (socket.timeout("timed out"), NetworkError),
            (socket.gaierror(-2, "Name or service not known"), NetworkError),
            (ssl.SSLError("handshake"), NetworkError),
            (OSError("réseau injoignable"), NetworkError),
            (ssl.SSLCertVerificationError("certificat"), PermanentMailError),
            (smtplib.SMTPException("autre"), TemporaryMailError),
            (ValueError("bug"), TemporaryMailError),
        ]
        for exc, expected in cases:
            result = classify(exc, "a@x.fr")
            self.assertIs(type(result), expected, repr(exc))

    def test_messages_utiles(self):
        self.assertEqual(str(classify(smtplib.SMTPAuthenticationError(535, b"x"))), MSG_AUTH)
        self.assertIn("a@x.fr", str(classify(smtplib.SMTPRecipientsRefused({"a@x.fr": (550, b"x")}), "a@x.fr")))
        self.assertIn("552", str(classify(smtplib.SMTPDataError(552, b"too large"))))


class FakeSMTP:
    """Faux smtplib.SMTP : enregistre les appels."""
    instances = []

    def __init__(self, host, port, timeout=None, context=None, **kw):
        self.args = (host, port, timeout, context)
        self.calls, self.sent, self.closed = [], [], False
        self.fail_on = {}
        FakeSMTP.instances.append(self)

    def _do(self, name, *args, **kw):
        self.calls.append(name)
        if name in self.fail_on:
            raise self.fail_on[name]

    def ehlo(self): self._do("ehlo")
    def starttls(self, context=None): self._do("starttls")
    def login(self, user, password): self._do("login"); self.login_args = (user, password)
    def send_message(self, message, from_addr=None, to_addrs=None):
        self._do("send"); self.sent.append((message, from_addr, to_addrs))
    def quit(self): self.calls.append("quit"); self.closed = True
    def close(self): self.calls.append("close"); self.closed = True


class SmtpSenderTests(WithPhoto):
    def setUp(self):
        super().setUp()
        FakeSMTP.instances = []

    def sender(self, **kw):
        return SmtpSender(settings(**kw), smtp_factory=FakeSMTP, ssl_factory=FakeSMTP)

    def test_starttls_puis_connexion_puis_envoi(self):
        self.sender(security="starttls", port=587, password="secret").send(self.job(), NOW)
        [smtp] = FakeSMTP.instances
        self.assertEqual(smtp.calls, ["ehlo", "starttls", "ehlo", "login", "send", "quit"])
        self.assertEqual(smtp.login_args, ("photo@fete.fr", "secret"))
        message, from_addr, to_addrs = smtp.sent[0]
        self.assertEqual((from_addr, to_addrs), ("photo@fete.fr", ["lea@gmail.com"]))
        self.assertEqual(smtp.args[:3], ("127.0.0.1", 587, 20.0))

    def test_securite_auto(self):
        self.assertEqual(settings(security="auto", port=465).resolved_security(), "ssl")
        self.assertEqual(settings(security="auto", port=587).resolved_security(), "starttls")
        self.assertEqual(settings(security="auto", port=25).resolved_security(), "starttls")
        self.assertEqual(settings(security="aucune").resolved_security(), "none")
        self.assertEqual(settings(security="ssl", port=587).resolved_security(), "ssl")

    def test_ssl_direct_sans_starttls(self):
        self.sender(security="ssl", port=465, password="x").send(self.job(), NOW)
        [smtp] = FakeSMTP.instances
        self.assertEqual(smtp.calls, ["ehlo", "login", "send", "quit"])
        self.assertIsNotNone(smtp.args[3])                                   # contexte TLS fourni

    def test_sans_mot_de_passe_pas_de_connexion(self):
        self.sender(security="aucune", password="").send(self.job(), NOW)
        self.assertEqual(FakeSMTP.instances[0].calls, ["ehlo", "send", "quit"])

    def test_identifiant_distinct_de_l_expediteur(self):
        self.sender(security="aucune", password="x", user="compte-technique").send(self.job(), NOW)
        self.assertEqual(FakeSMTP.instances[0].login_args, ("compte-technique", "x"))

    def test_la_connexion_est_toujours_fermee(self):
        sender = SmtpSender(settings(security="aucune", password="x"), smtp_factory=FakeSMTP, ssl_factory=FakeSMTP)
        for failing in ("login", "send"):
            FakeSMTP.instances.clear()
            original = FakeSMTP._do
            def boom(self, name, *a, _failing=failing, **k):
                self.calls.append(name)
                if name == _failing:
                    raise smtplib.SMTPServerDisconnected("coupé")
            with mock.patch.object(FakeSMTP, "_do", boom):
                with self.assertRaises(NetworkError):
                    sender.send(self.job(), NOW)
            self.assertTrue(FakeSMTP.instances[0].closed, failing)

    def test_erreurs_classees(self):
        sender = SmtpSender(settings(security="aucune", password="x"), smtp_factory=FakeSMTP, ssl_factory=FakeSMTP)
        for call, exc, expected in [("login", smtplib.SMTPAuthenticationError(535, b"x"), PermanentMailError),
                                    ("send", smtplib.SMTPRecipientsRefused({"lea@gmail.com": (550, b"x")}), PermanentMailError),
                                    ("ehlo", ConnectionRefusedError(), NetworkError),
                                    ("send", smtplib.SMTPDataError(451, b"later"), TemporaryMailError)]:
            def boom(self, name, *a, _call=call, _exc=exc, **k):
                self.calls.append(name)
                if name == _call:
                    raise _exc
            with mock.patch.object(FakeSMTP, "_do", boom):
                with self.assertRaises(expected):
                    sender.send(self.job(), NOW)

    def test_connexion_impossible(self):
        def factory(*a, **k):
            raise socket.gaierror(-2, "Name or service not known")
        with self.assertRaises(NetworkError):
            SmtpSender(settings(security="aucune"), smtp_factory=factory).send(self.job(), NOW)

    def test_photo_manquante_ne_se_connecte_meme_pas(self):
        with self.assertRaises(PermanentMailError):
            self.sender().send(self.job(photo=self.photo.with_name("absente.jpg")), NOW)
        self.assertEqual(FakeSMTP.instances, [])

    def test_configuration_incomplete(self):
        self.assertFalse(settings(host="").configured); self.assertFalse(settings(sender="").configured)
        self.assertTrue(settings().configured)


class RealSmtpServerTests(WithPhoto):
    """Vrai échange SMTP avec smtplib, contre un petit serveur local."""

    def send(self, server, job=None, **kw):
        s = settings(port=server.port, **kw)
        SmtpSender(s).send(job or self.job(), NOW)

    def test_mail_complet_recu(self):
        with FakeSmtpServer() as server:
            self.send(server)
            [received] = server.messages
        self.assertEqual((received.mail_from, received.rcpt_to), ("photo@fete.fr", ["lea@gmail.com"]))
        msg = email.message_from_bytes(received.data, policy=policy.default)
        self.assertEqual(msg["Subject"], SUBJECT)
        self.assertEqual(msg["To"], "Léa Martin <lea@gmail.com>")
        [attachment] = list(msg.iter_attachments())
        self.assertEqual(attachment.get_content(), b"\xff\xd8\xff\xe0FAKE-JPEG-DATA\xff\xd9")
        self.assertIn("Salut Léa !", msg.get_body(preferencelist=("plain",)).get_content())

    def test_authentification(self):
        with FakeSmtpServer(user="photo@fete.fr", password="secret") as server:
            self.send(server, password="secret")
            self.assertEqual(server.logins, [("photo@fete.fr", "secret")])
            self.assertEqual(len(server.messages), 1)

    def test_mauvais_mot_de_passe(self):
        with FakeSmtpServer(user="photo@fete.fr", password="secret") as server:
            with self.assertRaises(PermanentMailError) as ctx:
                self.send(server, password="faux")
            self.assertEqual(str(ctx.exception), MSG_AUTH)
            self.assertEqual(server.messages, [])

    def test_adresse_refusee(self):
        with FakeSmtpServer(reject_rcpt=["lea@gmail.com"]) as server:
            with self.assertRaises(PermanentMailError):
                self.send(server)

    def test_refus_provisoire(self):
        with FakeSmtpServer(temp_fail_rcpt=["lea@gmail.com"]) as server:
            with self.assertRaises(TemporaryMailError):
                self.send(server)

    def test_message_trop_gros(self):
        with FakeSmtpServer(reject_data_code=552) as server:
            with self.assertRaises(PermanentMailError):
                self.send(server)

    def test_serveur_arrete(self):
        with FakeSmtpServer() as server:
            port = server.port
        with self.assertRaises(NetworkError):
            SmtpSender(settings(port=port)).send(self.job(), NOW)


if __name__ == "__main__":
    unittest.main()
