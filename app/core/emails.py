"""Validation basique d'une adresse mail saisie au clavier tactile."""
from __future__ import annotations

import re

_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
_EMAIL_RE = re.compile(rf"^[a-z0-9_%+-]+(?:\.[a-z0-9_%+-]+)*@{_LABEL}(?:\.{_LABEL})*\.[a-z]{{2,}}$")

MSG_INVALID = "Adresse mail invalide : elle doit ressembler à prenom@gmail.com"


def normalize_email(text: str) -> str:
    """Les adresses sont enregistrées en minuscules, sans espaces autour."""
    return text.strip().lower()


def is_valid_email(text: str) -> bool:
    """Contrôle de forme uniquement (une seule arobase, un domaine avec un point) : on ne vérifie pas que la boîte existe."""
    email = normalize_email(text)
    return len(email) <= 254 and bool(_EMAIL_RE.match(email))


def mask_email(text: str) -> str:
    """lea.martin@gmail.com -> l***@gmail.com : l'écran de fin ne montre pas l'adresse en entier."""
    email = normalize_email(text)
    local, _, domain = email.partition("@")
    if not local or not domain:
        return ""
    return f"{local[0]}***@{domain}"
