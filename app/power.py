"""Empêche Windows de s'endormir ou d'éteindre l'écran pendant la soirée."""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def prevent_sleep(enable: bool = True) -> bool:
    """Active ou lève l'interdiction de veille. Renvoie True si Windows a accepté (sans effet ailleurs).

    SetThreadExecutionState s'applique au thread appelant : à appeler depuis le thread principal,
    qui vit aussi longtemps que le logiciel.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        flags = ES_CONTINUOUS | ((ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED) if enable else 0)
        previous = ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
        if previous == 0:
            log.warning("Windows a refusé la demande de maintien en éveil")
            return False
        log.info("Veille Windows %s", "empêchée" if enable else "de nouveau autorisée")
        return True
    except Exception:
        log.exception("Maintien en éveil impossible")
        return False
