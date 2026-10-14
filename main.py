"""Point d'entrée du Photo Booth.

Codes de sortie : 0 = arrêt normal (ou déjà lancé) ; 1 = erreur. lancer.bat ne relance la borne qu'après une erreur.
"""
from __future__ import annotations

import logging
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from app import __version__, cli, diagnostics, paths, power, single_instance
from app.config import Config, complete_missing
from app.core import guests
from app.logger import setup_logging
from app.ui.main_window import MainWindow
from app.ui.theme import STYLESHEET

log = logging.getLogger("photobooth")
EXIT_OK, EXIT_ERROR = 0, 1


def _message(kind: str, text: str) -> None:
    """Message à l'écran : un exécutable sans console ne peut rien afficher autrement."""
    try:
        app = QApplication.instance() or QApplication(sys.argv[:1])
        getattr(QMessageBox, kind)(None, "Photo Booth", text)
    except Exception:
        log.exception("Impossible d'afficher le message : %s", text)


def _run_app(args) -> int:
    config_path = args.config or paths.app_dir() / "config.ini"
    complete_missing(config_path)      # ajoute les réglages apparus dans les nouvelles versions
    config = Config.load(args.config)
    config.ensure_directories()
    guests.ensure_template(config.fichier_invites)

    app = QApplication.instance() or QApplication(sys.argv)
    icon = paths.resource_path("assets/photobooth.ico")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))

    if args.autotest:
        report, code = diagnostics.run(config, len(app.screens()))
        if sys.stdout is not None:
            print(report)
        else:                           # exécutable sans console : le rapport s'affiche dans une fenêtre
            _message("information", report)
        return code

    lock = single_instance.acquire(config.dossier_donnees / "photobooth.lock")
    if lock is None:
        log.warning("Photo Booth est déjà lancé : cette copie se ferme")
        _message("warning", "Photo Booth est déjà lancé sur cet ordinateur.")
        return EXIT_OK                 # pas une erreur : lancer.bat ne doit pas relancer

    log.info("Démarrage de Photo Booth %s (détourage=%s, poses=%d)", __version__, config.mode_detourage, config.nb_poses)
    power.prevent_sleep(True)          # ni veille ni écran éteint pendant la soirée
    try:
        app.setStyleSheet(STYLESHEET)
        window = MainWindow(config, fullscreen=config.plein_ecran and not args.windowed,
                            slideshow_windowed=args.diaporama_fenetre)
        window.show()
        return app.exec()
    finally:
        power.prevent_sleep(False)
        lock.unlock()


def main(argv: list[str] | None = None) -> int:
    args = cli.build_parser().parse_args(argv)
    code = cli.run_tools(args)         # --version, --test-mail, --telecharger-modeles : sans interface
    if code is not None:
        return code
    setup_logging(paths.app_dir() / "logs")
    try:
        return _run_app(args)
    except Exception as exc:
        log.critical("Photo Booth n'a pas pu démarrer", exc_info=True)
        _message("critical", f"Photo Booth n'a pas pu démarrer.\n\n{exc}\n\n"
                             f"Détails dans : {paths.app_dir() / 'logs' / 'photobooth.log'}")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
