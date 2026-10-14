"""Fenêtre principale : navigation entre écrans, retour automatique, accès admin caché."""
from __future__ import annotations

import logging
import time

from PyQt6.QtCore import QEvent, QObject, QRect, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QMouseEvent, QShortcut
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget

from ..config import Config
from ..core.camera import CameraWorker
from ..core.mail_service import MailService
from ..core.segmentation import Segmenter, SegmentationError, create_segmenter, segmenter_key
from ..session import Session
from .admin_dialog import open_admin_dialog
from .slideshow import SlideshowController
from .screens import SCREENS
from .screens.base import BaseScreen

log = logging.getLogger(__name__)

FLOW = list(SCREENS)                       # ordre du parcours = ordre du registre
ADMIN_CORNER = QRect(0, 0, 120, 120)       # coin haut gauche
ADMIN_TAPS = 3                             # 3 appuis dans le coin...
ADMIN_WINDOW_S = 3.0                       # ...en moins de 3 secondes
_ACTIVITY_EVENTS = {
    QEvent.Type.MouseButtonPress,
    QEvent.Type.TouchBegin,
    QEvent.Type.KeyPress,
}


class MainWindow(QMainWindow):
    def __init__(self, config: Config, fullscreen: bool = True, slideshow_windowed: bool = False) -> None:
        super().__init__()
        self.config = config
        self.session = Session()
        self.current_name = ""
        self._admin_taps: list[float] = []
        # La caméra vit aussi longtemps qu'un invité est dans le parcours : elle démarre à l'écran
        # de prise de vue et s'arrête au retour à l'accueil (voir go_to). Créée avant les écrans
        # car ils s'abonnent à ses signaux.
        self.camera = CameraWorker(config, self)
        self.mail = MailService(config)     # envoi des photos par mail, en arrière-plan
        self.slideshow = SlideshowController(config, self, windowed_preview=slideshow_windowed)
        self._segmenter: Segmenter | None = None
        self._segmenter_key: tuple | None = None

        self.setWindowTitle("Photo Booth")
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._screens: dict[str, BaseScreen] = {}
        for name, screen_cls in SCREENS.items():
            screen = screen_cls(self)
            self._screens[name] = screen
            self._stack.addWidget(screen)

        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.timeout.connect(self._on_inactivity)

        QApplication.instance().installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self.camera.stop_camera)
        QApplication.instance().aboutToQuit.connect(self.close_segmenter)
        QApplication.instance().aboutToQuit.connect(self.mail.stop)
        QApplication.instance().aboutToQuit.connect(self.slideshow.close)
        # Raccourci de développement (les invités n'ont pas de clavier)
        QShortcut(QKeySequence("Ctrl+Shift+Q"), self).activated.connect(self.open_admin)

        self.go_to("home")
        if fullscreen:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.showFullScreen()
        else:
            self.resize(1280, 720)
            self.show()
        # Charger le modèle IA prend 1 à 2 secondes : on le fait au démarrage, pas devant le premier invité
        QTimer.singleShot(500, self._warm_up)
        self.mail.start()
        self.slideshow.start()      # après l'affichage de la borne : le second écran se choisit par rapport à elle

    # ---------- détourage (partagé par tous les écrans) ----------

    def get_segmenter(self) -> Segmenter:
        """Segmenteur du mode courant ; recréé si les réglages ont changé. Peut lever SegmentationError."""
        key = segmenter_key(self.config)
        if self._segmenter is None or key != self._segmenter_key:
            self.close_segmenter()
            self._segmenter = create_segmenter(self.config)
            self._segmenter_key = key
        return self._segmenter

    def close_segmenter(self) -> None:
        if self._segmenter is not None:
            self._segmenter.close()
            self._segmenter = None
            self._segmenter_key = None

    def _warm_up(self) -> None:
        try:
            self.get_segmenter()
        except SegmentationError as exc:
            log.warning("Détourage non prêt au démarrage : %s", exc.args[0].replace("\n", " "))
        except Exception:
            log.exception("Erreur au chargement du détourage")

    # ---------- navigation ----------

    def go_to(self, name: str) -> None:
        if name not in self._screens:
            raise KeyError(f"Écran inconnu : {name}")
        previous = self._screens.get(self.current_name)
        if previous is not None:
            previous.on_leave()
        if name == "home":
            self.session.reset()  # un nouvel invité repart toujours de zéro
            self.camera.stop_camera()
        self.current_name = name
        screen = self._screens[name]
        self._stack.setCurrentWidget(screen)
        screen.on_enter()
        self._restart_inactivity()
        log.info("Écran : %s", name)

    def go_next(self) -> None:
        index = FLOW.index(self.current_name)
        self.go_to(FLOW[index + 1] if index + 1 < len(FLOW) else "home")

    def go_back(self) -> None:
        index = FLOW.index(self.current_name)
        self.go_to(FLOW[index - 1] if index > 0 else "home")

    def go_home(self) -> None:
        self.go_to("home")

    # ---------- retour automatique à l'accueil ----------

    def _restart_inactivity(self) -> None:
        screen = self._screens.get(self.current_name)
        delay = self.config.inactivite_secondes
        if delay <= 0 or screen is None or self.current_name == "home" or not screen.allow_inactivity_reset:
            self._inactivity_timer.stop()
            return
        self._inactivity_timer.start(delay * 1000)

    def _on_inactivity(self) -> None:
        screen = self._screens.get(self.current_name)
        if screen is None or not screen.allow_inactivity_reset:
            return
        log.info("Inactivité : retour à l'accueil")
        self.go_to("home")

    # ---------- accès admin ----------

    def open_admin(self) -> None:
        open_admin_dialog(self)
        self._restart_inactivity()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        etype = event.type()
        if etype in _ACTIVITY_EVENTS:
            self._restart_inactivity()
        if (etype == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
                and isinstance(obj, QWidget) and obj.window() is self):
            self._check_admin_gesture(event)
        return False  # on n'intercepte jamais les événements

    def _check_admin_gesture(self, event: QMouseEvent) -> None:
        pos = self.mapFromGlobal(event.globalPosition().toPoint())
        if not ADMIN_CORNER.contains(pos):
            self._admin_taps.clear()
            return
        now = time.monotonic()
        self._admin_taps = [t for t in self._admin_taps if now - t <= ADMIN_WINDOW_S] + [now]
        if len(self._admin_taps) >= ADMIN_TAPS:
            self._admin_taps.clear()
            QTimer.singleShot(0, self.open_admin)  # hors du filtre d'événements

    def closeEvent(self, event) -> None:
        log.info("Fermeture du logiciel")
        self.camera.stop_camera()
        self.close_segmenter()
        self.mail.stop()
        self.slideshow.close()
        super().closeEvent(event)
