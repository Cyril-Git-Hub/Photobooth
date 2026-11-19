"""Valeurs par défaut du mail envoyé à l'invité (modifiables dans config.ini)."""

DEFAULT_SENDER_NAME = "Photobooth"
DEFAULT_SUBJECT = "Ta photo du photobooth est prête !"
DEFAULT_BODY = ("{salutation}\n\n"
                "Ta photo du photobooth est en pièce jointe. Quelle équipe de choc, on dirait un générique d'anime !\n\n"
                "À très vite pour la suite de l'aventure !")


def escape_newlines(text: str) -> str:
    """config.ini tient chaque réglage sur une ligne : les retours à la ligne s'y écrivent \\n."""
    return text.replace("\n", "\\n")


def unescape_newlines(text: str) -> str:
    return text.replace("\\n", "\n")
