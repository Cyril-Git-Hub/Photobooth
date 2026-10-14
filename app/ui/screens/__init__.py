"""Registre des écrans. L'ordre du dictionnaire est l'ordre du parcours."""
from .background_select import BackgroundSelectScreen
from .base import BaseScreen
from .capture import CaptureScreen
from .email_entry import EmailEntryScreen
from .format_select import FormatSelectScreen
from .guest_select import GuestSelectScreen
from .placeholders import HomeScreen
from .review import ReviewScreen
from .sending import SendingScreen

SCREENS: dict[str, type[BaseScreen]] = {
    "home": HomeScreen,
    "guest_select": GuestSelectScreen,
    "email_entry": EmailEntryScreen,
    "format_select": FormatSelectScreen,
    "background_select": BackgroundSelectScreen,
    "capture": CaptureScreen,
    "review": ReviewScreen,
    "sending": SendingScreen,
}
