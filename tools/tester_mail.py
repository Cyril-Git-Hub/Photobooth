r"""Teste l'envoi de mails avec les réglages de config.ini (section [mail]).

    python tools\tester_mail.py                   # envoie une photo de test à adresse_organisateur
    python tools\tester_mail.py moi@exemple.fr    # ou à l'adresse de ton choix

Sans Python (PC de la fête) : photobooth-outils.exe --test-mail
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cli import test_mail as main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
