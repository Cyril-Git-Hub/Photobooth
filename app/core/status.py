"""Voyant discret pour l'organisateur, affiché en haut à droite de la borne seulement quand quelque chose cloche."""
from __future__ import annotations

from dataclasses import dataclass

WARN, ERROR = "warn", "error"


@dataclass(frozen=True)
class Badge:
    text: str
    level: str   # WARN (orange) ou ERROR (rouge)


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def build_badge(mail, backup) -> Badge | None:
    """`mail` : MailStats, `backup` : BackupStats (ou None). Renvoie None quand tout va bien."""
    parts: list[str] = []
    level = WARN
    if mail is not None:
        if not mail.configured:
            if mail.pending:
                parts.append(f"mails non configurés ({mail.pending} en attente)")
        else:
            if mail.online is False:
                parts.append("hors-ligne")
            if mail.pending:
                parts.append(_plural(mail.pending, "mail en attente", "mails en attente"))
            if mail.failed:
                parts.append(_plural(mail.failed, "mail en échec", "mails en échec"))
                level = ERROR
    if backup is not None and backup.enabled and backup.pending and backup.last_error:
        parts.append(f"sauvegarde en panne ({_plural(backup.pending, 'photo', 'photos')})")
        level = ERROR
    return Badge(" · ".join(parts).capitalize(), level) if parts else None
