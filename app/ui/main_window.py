"""Fenêtre principale : navigation entre écrans, retour automatique, accès admin caché."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QMouseEvent, QPixmap, QShortcut, QTouchEvent
from PyQt6.QtWidgets import (
    QApplication, QFrame, QLabel, QMainWindow, QScrollArea, QScroller, QStackedLayout, QStackedWidget, QWidget,
)

from ..config import Config
from ..core.backup import BackupService
from ..core.drive_sharing import DriveShareService
from ..core.camera import CameraWorker
from ..core.events import EventStore
from ..core.mail_service import MailService
from ..core.status import build_badge
from ..core.segmentation import Segmenter, SegmentationError, create_segmenter, segmenter_key
from ..core.sounds import SoundManager
from ..session import Session
from . import scale
from .admin_dialog import open_admin_dialog
from .slideshow import SlideshowController
from .capture_display import CaptureDisplayController
from .screensaver import ScreensaverOverlay
from .screens import SCREENS
from .screens.base import BaseScreen

log = logging.getLogger(__name__)

FLOW = [name for name in SCREENS if name not in {"gif_options", "challenge", "guestbook"}]  # écrans hors parcours linéaire
ADMIN_TAPS = 5                             # 5 appuis distincts dans le coin...
ADMIN_WINDOW_S = 5.0                       # ...en moins de 5 secondes
ADMIN_TAP_DEBOUNCE_S = 0.15                # ignore l'événement souris synthétisé après un toucher
_ACTIVITY_EVENTS = {
    QEvent.Type.MouseButtonPress,
    QEvent.Type.TouchBegin,
    QEvent.Type.KeyPress,
}


class MainWindow(QMainWindow):
    def __init__(self, config: Config, fullscreen: bool = True, slideshow_windowed: bool = False) -> None:
        super().__init__()
        self.config = config
        self.theme = getattr(config, "active_theme", None)
        self.sounds = SoundManager(config, self)
        self.events = EventStore(config)
        self.session = Session()
        self.current_name = ""
        self._admin_taps: list[float] = []
        self._last_admin_tap = 0.0
        # La caméra vit aussi longtemps qu'un invité est dans le parcours : elle démarre à l'écran
        # de prise de vue et s'arrête au retour à l'accueil (voir go_to). Créée avant les écrans
        # car ils s'abonnent à ses signaux.
        self.camera = CameraWorker(config, self)
        self.mail = MailService(config)     # envoi des photos par mail, en arrière-plan
        self.backup = BackupService(config)  # copie des photos validées vers un second dossier (facultatif)
        self.drive_share = None
        self.drive_executor = None
        self.ensure_drive_service()
        self.slideshow = SlideshowController(config, self, windowed_preview=slideshow_windowed)
        self.capture_display = CaptureDisplayController(self)
        self.camera.preview_ready.connect(self.capture_display.set_image)
        self._segmenter: Segmenter | None = None
        self._segmenter_key: tuple | None = None

        self.setWindowTitle(self.theme.app_title if self.theme else "Photobooth")
        self._stack = QStackedWidget()
        self._booth_frame = QFrame()
        self._booth_frame.setObjectName("boothFrame")
        frame_layout = QStackedLayout(self._booth_frame)
        frame_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        self._frame_layout = frame_layout
        frame_layout.addWidget(self._stack)
        self.setCentralWidget(self._booth_frame)

        self._screens: dict[str, BaseScreen] = {}
        self._wrappers: dict[str, QScrollArea] = {}
        for name, screen_cls in SCREENS.items():
            screen = screen_cls(self)
            self._screens[name] = screen
            self._wrappers[name] = self._scrollable(screen)
            self._stack.addWidget(self._wrappers[name])

        # voyant discret de l'organisateur (en haut à droite, seulement en cas de souci)
        self._badge = QLabel(self)
        self._badge.setObjectName("badge")
        self._badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._badge.hide()
        self._frame_overlay = QLabel(self._booth_frame)
        self._frame_overlay.setObjectName("screenFrameOverlay")
        self._frame_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._frame_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._frame_overlay.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop)
        self._frame_overlay.setStyleSheet("background: transparent; border: none;")
        self._frame_layout.addWidget(self._frame_overlay)
        self._frame_overlay.raise_()
        self._frame_pixmap: QPixmap | None = None
        self._load_screen_frame()
        self._screensaver = ScreensaverOverlay(self.theme, self._start_from_screensaver)
        self._screensaver.setGeometry(self._booth_frame.rect())
        self._screensaver.hide()
        self._badge_timer = QTimer(self)
        self._badge_timer.setInterval(3000)
        self._badge_timer.timeout.connect(self._refresh_badge)
        self._badge_timer.start()

        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.timeout.connect(self._on_inactivity)
        self._screensaver_timer = QTimer(self)
        self._screensaver_timer.setSingleShot(True)
        self._screensaver_timer.timeout.connect(self._show_screensaver)

        QApplication.instance().installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self.camera.stop_camera)
        QApplication.instance().aboutToQuit.connect(self.close_segmenter)
        QApplication.instance().aboutToQuit.connect(self.mail.stop)
        QApplication.instance().aboutToQuit.connect(self.backup.stop)
        QApplication.instance().aboutToQuit.connect(self.slideshow.close)
        QApplication.instance().aboutToQuit.connect(self.capture_display.close)
        # Raccourci de développement (les invités n'ont pas de clavier)
        QShortcut(QKeySequence("Ctrl+Shift+Q"), self).activated.connect(self.open_admin)

        self.go_to("home")
        if fullscreen:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.showFullScreen()
        else:
            self.resize(*scale.windowed_size(1280, 720, QApplication.primaryScreen()))   # sans dépasser l'écran
            self.show()
        # Charger le modèle IA prend 1 à 2 secondes : on le fait au démarrage, pas devant le premier invité
        QTimer.singleShot(500, self._warm_up)
        self.mail.start()
        self.backup.start()
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

    def reload_theme(self) -> None:
        from ..core.themes import load_theme
        from .theme import build_stylesheet
        self.theme = load_theme(self.config)
        self.config.active_theme = self.theme
        self.capture_display.reload_theme(self.theme)
        self.sounds.reload()
        self.setWindowTitle(self.theme.app_title)
        QApplication.instance().setApplicationName(self.theme.app_title)
        QApplication.instance().setStyleSheet(build_stylesheet(theme=self.theme))
        self._screensaver.deleteLater()
        self._screensaver = ScreensaverOverlay(self.theme, self._start_from_screensaver)
        self._screensaver.setGeometry(self._booth_frame.rect())
        self._screensaver.hide()
        self._load_screen_frame()
        home = self._screens.get("home")
        if home is not None and hasattr(home, "apply_theme"):
            home.apply_theme(self.theme)
        guestbook = self._screens.get("guestbook")
        if guestbook is not None and hasattr(guestbook, "apply_theme"):
            guestbook.apply_theme(self.theme)

    def ensure_drive_service(self) -> bool:
        """Prépare le service QR lorsqu'il vient d'être activé dans l'administration."""
        if not self.config.qr_drive_actif or self.drive_share is not None:
            return self.drive_share is not None
        if self.drive_executor is None:
            self.drive_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="drive-share")
        try:
            self.drive_share = DriveShareService(self.config.base_dir)
            if self.drive_share.is_configured():
                cleanup = self.drive_executor.submit(self.drive_share.revoke_expired)
                cleanup.add_done_callback(self._log_drive_cleanup_error)
            return True
        except Exception:
            log.exception("Service QR Google Drive indisponible ; le photobooth continue sans partage QR")
            self.drive_share = None
            return False

    def apply_activation_settings(self) -> bool:
        """Applique immédiatement les options modifiées depuis le menu admin."""
        self.mail.reload_settings()
        self.sounds.reload()
        self.backup.retry_now()
        self.slideshow.reload()
        drive_ready = self.ensure_drive_service() if self.config.qr_drive_actif else True
        if self.current_name == "format_select":
            self._screens[self.current_name].on_enter()
        self._refresh_badge()
        return drive_ready

    def _warm_up(self) -> None:
        try:
            self.get_segmenter()
        except SegmentationError as exc:
            log.warning("Détourage non prêt au démarrage : %s", exc.args[0].replace("\n", " "))
        except Exception:
            log.exception("Erreur au chargement du détourage")

    @staticmethod
    def _scrollable(screen: QWidget) -> QScrollArea:
        """Si un écran dépasse la hauteur disponible (petit écran, affichage agrandi), on peut faire défiler au doigt :
        aucun bouton n'est jamais inaccessible. Quand tout tient, rien ne change."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(screen)
        QScroller.grabGesture(area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        return area

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
        self.capture_display.refresh()
        screen = self._screens[name]
        self._stack.setCurrentWidget(self._wrappers[name])
        screen.on_enter()
        # Changing the current page may raise the stack above sibling overlays.
        # Reapply the frame after the page switch so its transparent PNG stays in front.
        self._apply_screen_frame_mode()
        self._restart_inactivity()
        log.info("Écran : %s", name)
        self._refresh_badge()

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
        if delay <= 0 or screen is None:
            self._inactivity_timer.stop()
            self._screensaver_timer.stop()
            return
        if self.current_name == "home":
            self._inactivity_timer.stop()
            if self._screensaver.isVisible():
                self._screensaver_timer.stop()
            else:
                self._screensaver_timer.start(delay * 1000)
            return
        self._screensaver_timer.stop()
        if not screen.allow_inactivity_reset:
            self._inactivity_timer.stop()
            return
        self._inactivity_timer.start(delay * 1000)

    def _show_screensaver(self) -> None:
        if self.current_name != "home" or self.config.inactivite_secondes <= 0:
            return
        self._screensaver_timer.stop()
        log.info("Inactivité sur l'accueil : affichage de l'écran de veille")
        self._frame_overlay.hide()
        self._screensaver.setGeometry(self._booth_frame.rect())
        self._screensaver.show()
        self._screensaver.raise_()

    def _start_from_screensaver(self, position: QPoint) -> None:
        if not self._screensaver.isVisible():
            return
        if self._admin_corner_rect().contains(position):
            return  # garde le geste d'ouverture du mode administrateur disponible
        self._screensaver.hide()
        self._apply_screen_frame_mode()
        self._restart_inactivity()
        log.info("Écran de veille masqué : retour à l'accueil")

    def _on_inactivity(self) -> None:
        screen = self._screens.get(self.current_name)
        if screen is None or not screen.allow_inactivity_reset:
            return
        log.info("Inactivité : retour à l'accueil et affichage de l'écran de veille")
        self.go_to("home")
        self._show_screensaver()

    # ---------- accès admin ----------

    def open_admin(self) -> None:
        if self._screensaver.isVisible():
            self._screensaver.hide()
            self._apply_screen_frame_mode()
        open_admin_dialog(self)
        self._restart_inactivity()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        etype = event.type()
        if etype in _ACTIVITY_EVENTS:
            self._restart_inactivity()
        if isinstance(obj, QWidget) and obj.window() is self:
            if (etype == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
                    and event.button() == Qt.MouseButton.LeftButton):
                self._check_admin_gesture(event.globalPosition().toPoint())
            elif etype == QEvent.Type.TouchBegin and isinstance(event, QTouchEvent) and event.points():
                self._check_admin_gesture(event.points()[0].globalPosition().toPoint())
        return False  # on n'intercepte jamais les événements

    def _admin_corner_rect(self) -> QRect:
        """Zone confortable au toucher, proportionnelle à l'écran sans couvrir tout le parcours."""
        width = min(320, max(240, round(self.width() * 0.20)))
        height = min(220, max(160, round(self.height() * 0.22)))
        return QRect(0, 0, min(width, self.width()), min(height, self.height()))

    def _check_admin_gesture(self, global_position: QPoint) -> None:
        pos = self.mapFromGlobal(global_position)
        if not self._admin_corner_rect().contains(pos):
            self._admin_taps.clear()
            return
        now = time.monotonic()
        if now - self._last_admin_tap < ADMIN_TAP_DEBOUNCE_S:
            return
        self._last_admin_tap = now
        self._admin_taps = [t for t in self._admin_taps if now - t <= ADMIN_WINDOW_S] + [now]
        if len(self._admin_taps) >= ADMIN_TAPS:
            self._admin_taps.clear()
            QTimer.singleShot(0, self.open_admin)  # hors du filtre d'événements

    # ---------- voyant de l'organisateur ----------

    def _refresh_badge(self) -> None:
        """Affiche « Hors-ligne · 3 mails en attente »... seulement quand il y a un souci, et jamais pendant la prise de vue."""
        badge = None
        if self.config.indicateur_organisateur and self.current_name != "capture":
            try:
                badge = build_badge(self.mail.stats(), self.backup.stats())
            except Exception:
                log.exception("Voyant de l'organisateur : état illisible")
        if badge is None:
            self._badge.hide()
            return
        self._badge.setText(badge.text)
        self._badge.setProperty("level", badge.level)
        style = self._badge.style()
        style.unpolish(self._badge)       # le style dépend de la propriété « level » : on le réapplique
        style.polish(self._badge)
        self._badge.adjustSize()
        self._place_badge()
        self._badge.show()
        self._badge.raise_()

    def _place_badge(self) -> None:
        self._badge.move(int(self.width()) - int(self._badge.width()) - 16, 12)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_screensaver"):
            self._screensaver.setGeometry(self._booth_frame.rect())
        self._place_badge()
        self._apply_screen_frame_mode()

    def _load_screen_frame(self) -> None:
        path = self.theme.screen_frame if self.theme else None
        self._frame_pixmap = QPixmap(str(path)) if path is not None else None
        if self._frame_pixmap is None or self._frame_pixmap.isNull():
            self._frame_overlay.clear()
            self._frame_overlay.hide()
            self._stack.setContentsMargins(scale.px(14), scale.px(14), scale.px(14), scale.px(14))
            if path is not None:
                log.warning("Cadre d'interface illisible : %s", path)
            return
        self._update_screen_frame()
        self._apply_screen_frame_mode()

    def _update_screen_frame(self) -> None:
        if self._frame_pixmap is None or self._frame_pixmap.isNull():
            return
        available = QSize(self._booth_frame.width(), self._booth_frame.height())
        frame_size = self._frame_pixmap.size().scaled(available, Qt.AspectRatioMode.KeepAspectRatio)
        left = (self._booth_frame.width() - frame_size.width()) // 2
        top = (self._booth_frame.height() - frame_size.height()) // 2
        self._frame_overlay.setGeometry(left, top, frame_size.width(), frame_size.height())
        self._frame_overlay.setPixmap(self._frame_pixmap.scaled(
            frame_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _apply_screen_frame_mode(self) -> None:
        """Le cadre est au premier plan, son centre transparent laisse voir l'écran ; il disparaît à la capture."""
        if self._frame_pixmap is None or self._frame_pixmap.isNull():
            self._stack.setContentsMargins(scale.px(14), scale.px(14), scale.px(14), scale.px(14))
            return
        if self.current_name == "capture":
            self._stack.setContentsMargins(scale.px(14), scale.px(14), scale.px(14), scale.px(14))
            self._frame_overlay.hide()
            return
        width, height = self._booth_frame.width(), self._booth_frame.height()
        self._stack.setContentsMargins(
            round(width * 0.065), round(height * 0.08),
            round(width * 0.065), round(height * 0.16),
        )
        self._update_screen_frame()
        self._frame_overlay.show()
        self._frame_overlay.raise_()
        if self._badge.isVisible():
            self._badge.raise_()

    def closeEvent(self, event) -> None:
        log.info("Fermeture du logiciel")
        guestbook = self._screens.get("guestbook")
        if guestbook is not None:
            guestbook.stop_and_wait()
        self.camera.stop_camera()
        self.close_segmenter()
        self.mail.stop()
        self.backup.stop()
        self.slideshow.close()
        self.sounds.stop_all()
        if self.drive_executor is not None:
            self.drive_executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

    @staticmethod
    def _log_drive_cleanup_error(future) -> None:
        try:
            future.result()
        except Exception:
            log.exception("Nettoyage automatique des liens Google Drive impossible")
