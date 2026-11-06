import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class ModelDownloadScriptTests(unittest.TestCase):
    def test_script_ne_demande_aucune_dependance_de_la_borne(self):
        result = subprocess.run(
            [sys.executable, "-S", str(ROOT / "tools" / "telecharger_modele.py"), "modele-inconnu"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Modèle inconnu", result.stdout)
        self.assertNotIn("ModuleNotFoundError", result.stderr)


if __name__ == "__main__":
    unittest.main()
