"""Texte en cours de saisie sur le clavier virtuel (logique pure, testable sans interface)."""
from __future__ import annotations


class TextBuffer:
    def __init__(self, max_length: int = 80, allow_space: bool = False, text: str = "") -> None:
        self.max_length = max_length
        self.allow_space = allow_space
        self._text = ""
        self.set(text)

    @property
    def value(self) -> str:
        return self._text

    def set(self, text: str) -> None:
        self._text = ""
        self.insert(text)

    def clear(self) -> None:
        self._text = ""

    def backspace(self) -> None:
        self._text = self._text[:-1]

    def insert(self, chunk: str) -> None:
        """Ajoute du texte (une touche, un suffixe comme « .com » ou un domaine comme « @gmail.com »)."""
        chunk = "".join(c for c in chunk.lower() if c.isprintable() and (self.allow_space or not c.isspace()))
        if not chunk:
            return
        if chunk.startswith("@"):
            if "@" in self._text:
                if chunk == "@":
                    return                                            # une seule arobase
                self._text = self._text[:self._text.index("@")]       # un domaine remplace celui déjà saisi
        elif chunk.startswith("."):
            if not self._text:
                return                                                # pas de point en tête
            if self._text.endswith("."):
                chunk = chunk[1:]                                     # pas de double point
                if not chunk:
                    return
        if len(self._text) + len(chunk) > self.max_length:
            return
        self._text += chunk
