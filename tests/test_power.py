import ctypes
import logging
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from app import logger, power


class FakeKernel:
    def __init__(self, result=1, error=None):
        self.calls, self.result, self.error = [], result, error
        self.kernel32 = self

    def SetThreadExecutionState(self, flags):
        if self.error:
            raise self.error
        self.calls.append(flags.value)
        return self.result


class PowerTests(unittest.TestCase):
    def test_sans_effet_hors_windows(self):
        with mock.patch.object(power.sys, "platform", "linux"):
            self.assertFalse(power.prevent_sleep(True))

    def test_empeche_la_veille_et_l_extinction_de_l_ecran(self):
        fake = FakeKernel()
        with mock.patch.object(power.sys, "platform", "win32"), mock.patch.object(ctypes, "windll", fake, create=True):
            self.assertTrue(power.prevent_sleep(True))
            self.assertTrue(power.prevent_sleep(False))
        self.assertEqual(fake.calls, [power.ES_CONTINUOUS | power.ES_SYSTEM_REQUIRED | power.ES_DISPLAY_REQUIRED,
                                      power.ES_CONTINUOUS])

    def test_refus_de_windows(self):
        with mock.patch.object(power.sys, "platform", "win32"), \
             mock.patch.object(ctypes, "windll", FakeKernel(result=0), create=True):
            with self.assertLogs("app.power", level="WARNING"):
                self.assertFalse(power.prevent_sleep(True))

    def test_erreur_imprevue_ne_plante_pas(self):
        with mock.patch.object(power.sys, "platform", "win32"), \
             mock.patch.object(ctypes, "windll", FakeKernel(error=OSError("boom")), create=True):
            with self.assertLogs("app.power", level="ERROR"):
                self.assertFalse(power.prevent_sleep(True))


class ThreadHookTests(unittest.TestCase):
    def args(self, exc):
        return SimpleNamespace(exc_type=type(exc), exc_value=exc, exc_traceback=exc.__traceback__,
                               thread=threading.Thread(name="envoi-mails"))

    def test_exception_de_thread_journalisee(self):
        with self.assertLogs("photobooth", level="CRITICAL") as logs:
            logger._log_thread_exception(self.args(RuntimeError("boom")))
        self.assertIn("envoi-mails", logs.output[0]); self.assertIn("boom", logs.output[0])

    def test_arret_normal_du_thread_ignore(self):
        with self.assertNoLogs("photobooth", level="CRITICAL"):
            logger._log_thread_exception(self.args(SystemExit()))

    def test_thread_inconnu(self):
        args = self.args(ValueError("x")); args.thread = None
        with self.assertLogs("photobooth", level="CRITICAL"):
            logger._log_thread_exception(args)


if __name__ == "__main__":
    unittest.main()
