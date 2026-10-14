"""Construction du mail (texte, HTML, photo en pièce jointe) et envoi par SMTP.

Les erreurs sont classées pour la file d'attente :
- PermanentMailError : inutile de réessayer (adresse refusée, identifiants incorrects, photo introuvable) ;
- NetworkError : pas de connexion, on réessaiera dès que le réseau revient ;
- TemporaryMailError : refus provisoire du serveur (4xx), on réessaiera plus tard.
"""
from __future__ import annotations

import html
import logging
import re
import smtplib
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path
from typing import Callable

from ..config import Config
from .mail_queue import ORGANIZER, MailJob

log = logging.getLogger(__name__)

MSG_AUTH = ("Identifiants refusés par le serveur : vérifie « expediteur » et « mot_de_passe_application » "
            "(avec Gmail, il faut un mot de passe d'application).")


class MailError(Exception):
    """Envoi impossible ; le message est destiné au journal et au mode administrateur."""


class PermanentMailError(MailError):
    pass


class TemporaryMailError(MailError):
    pass


class NetworkError(TemporaryMailError):
    """Pas de connexion au serveur : tous les envois échoueraient de la même façon."""


# ---------------------------------------------------------------- réglages

@dataclass(frozen=True)
class MailSettings:
    host: str = ""
    port: int = 587
    security: str = "auto"
    user: str = ""
    sender: str = ""
    password: str = ""
    display_name: str = "Photo Booth"
    organizer: str = ""
    subject_template: str = ""
    body_template: str = ""
    event_title: str = ""
    timeout: float = 20.0

    @classmethod
    def from_config(cls, config: Config) -> "MailSettings":
        return cls(host=config.smtp_hote, port=config.smtp_port, security=config.mail_securite,
                   user=config.mail_utilisateur or config.expediteur, sender=config.expediteur,
                   password=config.mot_de_passe_application, display_name=config.mail_nom_expediteur,
                   organizer=config.adresse_organisateur, subject_template=config.mail_objet,
                   body_template=config.mail_message, event_title=config.pm_titre)

    @property
    def configured(self) -> bool:
        return bool(self.host and self.sender)

    def resolved_security(self) -> str:
        if self.security == "auto":
            return "ssl" if self.port == 465 else "starttls"
        return "none" if self.security == "aucune" else self.security


# ---------------------------------------------------------------- texte du mail

class _SafeValues(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"        # variable inconnue : laissée telle quelle plutôt que de planter


def render(template: str, values: dict[str, str]) -> str:
    try:
        return template.format_map(_SafeValues(values))
    except (ValueError, IndexError, KeyError, AttributeError):
        return template               # accolades mal formées : le texte part tel quel


def text_to_html(text: str) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    body = "".join(f'<p style="margin:0 0 14px 0">{html.escape(p).replace(chr(10), "<br>")}</p>' for p in paragraphs)
    return ('<html><body style="font-family:Segoe UI,Arial,sans-serif;font-size:16px;color:#222">'
            f"{body}</body></html>")


def _guest_values(settings: MailSettings, job: MailJob, now: datetime) -> dict[str, str]:
    first = job.guest_first_name
    return {"prenom": first, "nom": job.guest_last_name, "nom_complet": job.guest_name,
            "salutation": f"Salut {first} !" if first else "Salut !",
            "titre": settings.event_title, "date": now.strftime("%d/%m/%Y")}


def _organizer_texts(job: MailJob) -> tuple[str, str]:
    name = job.guest_name or "invité sans nom"
    if job.guest_email:
        detail = f"Cette photo a aussi été envoyée à {job.guest_email}."
    else:
        detail = "Cet invité n'a pas donné d'adresse mail : tu es seul(e) à recevoir cette photo."
    return f"[Photo booth] {name}", f"Copie de la photo de {name}.\n\n{detail}"


def build_message(settings: MailSettings, job: MailJob, now: datetime | None = None) -> EmailMessage:
    now = now or datetime.now()
    try:
        photo = job.photo_path.read_bytes()
    except OSError as exc:
        raise PermanentMailError(f"Photo introuvable : {job.photo_path.name}") from exc

    if job.kind == ORGANIZER:
        subject, body = _organizer_texts(job)
    else:
        values = _guest_values(settings, job, now)
        subject, body = render(settings.subject_template, values), render(settings.body_template, values)

    message = EmailMessage()
    try:
        message["From"] = Address(display_name=settings.display_name, addr_spec=settings.sender)
        message["To"] = Address(display_name=job.guest_name if job.kind != ORGANIZER else "", addr_spec=job.recipient)
    except (ValueError, IndexError) as exc:
        raise PermanentMailError(f"Adresse invalide : {job.recipient}") from exc
    message["Subject"] = subject.replace("\n", " ")
    message["Date"] = format_datetime(now.astimezone())
    message["Message-ID"] = make_msgid(domain=settings.sender.rpartition("@")[2] or None)
    message.set_content(body)
    message.add_alternative(text_to_html(body), subtype="html")
    message.add_attachment(photo, maintype="image", subtype="jpeg", filename=f"photobooth_{job.photo_path.stem}.jpg")
    return message


# ---------------------------------------------------------------- erreurs

def classify(exc: BaseException, recipient: str = "") -> MailError:
    """Transforme une exception de smtplib / réseau en erreur permanente, temporaire ou réseau."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return PermanentMailError(MSG_AUTH)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [code for code, _ in exc.recipients.values()]
        if codes and all(400 <= code < 500 for code in codes):
            return TemporaryMailError(f"Destinataire refusé provisoirement : {recipient}")
        return PermanentMailError(f"Adresse refusée par le serveur : {recipient}")
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return PermanentMailError(f"Le serveur ne gère pas cette connexion ou cette authentification : {exc}")
    if isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError)):
        return NetworkError(f"Connexion au serveur mail impossible ou interrompue : {exc}")
    if isinstance(exc, smtplib.SMTPResponseException):
        detail = exc.smtp_error.decode("utf-8", "replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
        text = f"Refusé par le serveur ({exc.smtp_code}) : {detail}"
        return TemporaryMailError(text) if 400 <= exc.smtp_code < 500 else PermanentMailError(text)
    if isinstance(exc, ssl.SSLCertVerificationError):
        return PermanentMailError(f"Certificat du serveur refusé : {exc}")
    if isinstance(exc, smtplib.SMTPException):         # avant OSError : SMTPException en hérite
        return TemporaryMailError(f"Erreur du serveur mail : {exc}")
    if isinstance(exc, (ConnectionError, TimeoutError, socket.timeout, socket.gaierror, ssl.SSLError, OSError)):
        return NetworkError(f"Pas de connexion au serveur mail : {exc}")
    return TemporaryMailError(f"Erreur inattendue : {exc!r}")


# ---------------------------------------------------------------- envoi

class SmtpSender:
    def __init__(self, settings: MailSettings, smtp_factory: Callable | None = None,
                 ssl_factory: Callable | None = None) -> None:
        self.settings = settings
        self._smtp_factory = smtp_factory or smtplib.SMTP
        self._ssl_factory = ssl_factory or smtplib.SMTP_SSL

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def _open(self):
        s = self.settings
        mode = s.resolved_security()
        if mode == "ssl":
            smtp = self._ssl_factory(s.host, s.port, timeout=s.timeout, context=ssl.create_default_context())
        else:
            smtp = self._smtp_factory(s.host, s.port, timeout=s.timeout)
        try:
            smtp.ehlo()
            if mode == "starttls":
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if s.password:
                smtp.login(s.user or s.sender, s.password)
            return smtp
        except BaseException:
            _close_quietly(smtp)
            raise

    def send(self, job: MailJob, now: datetime | None = None) -> None:
        """Envoie le mail du `job`. Lève PermanentMailError, TemporaryMailError ou NetworkError."""
        message = build_message(self.settings, job, now)
        smtp = None
        try:
            smtp = self._open()
            smtp.send_message(message, from_addr=self.settings.sender, to_addrs=[job.recipient])
        except MailError:
            raise
        except Exception as exc:
            raise classify(exc, job.recipient) from exc
        finally:
            if smtp is not None:
                _close_quietly(smtp)


def _close_quietly(smtp) -> None:
    try:
        smtp.quit()
    except Exception:
        try:
            smtp.close()
        except Exception:
            pass
