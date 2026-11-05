"""Aperçu caméra plein écran sur le troisième écran, sans commandes tactiles."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QImageReader, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from ..core.playlist import Playlist
from ..core.screens import pick_third_screen

log = logging.getLogger(__name__)


class CaptureDisplayWindow(QWidget):
    def __init__(self, background: QImage, colors: dict[str, str] | None = None,
                 app_title: str = "Photobooth") -> None:
        super().__init__()
        self.setWindowTitle(f"{app_title} : aperçu de prise de vue")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self._background = background
        self._colors = colors or {}
        self._image: QImage | None = None
        self._countdown = ""

    def show_on(self, screen) -> None:
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.showFullScreen()

    def set_image(self, image: QImage) -> None:
        self._image = image
        self.update()

    def set_background(self, image: QImage) -> None:
        self._background = image
        self._image = None
        self._countdown = ""
        self.update()

    def set_gallery_photo(self, image: QImage) -> None:
        self._image = image
        self._countdown = ""
        self.update()

    def set_colors(self, colors: dict[str, str] | None) -> None:
        self._colors = colors or {}
        self.update()

    def set_countdown(self, text: str) -> None:
        self._countdown = text
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._colors.get("mail_background", "#0b0a1a")))
        is_preview = self._image is not None and not self._image.isNull()
        image = self._image if is_preview else self._background
        if image is not None and not image.isNull():
            mode = Qt.AspectRatioMode.KeepAspectRatio
            target = image.size().scaled(self.size(), mode)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            scaled = image.scaled(target, mode,
                                  Qt.TransformationMode.SmoothTransformation)
            painter.drawImage((self.width() - scaled.width()) // 2,
                              (self.height() - scaled.height()) // 2, scaled)
        if self._countdown:
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(max(48, int(self.height() * 0.42)))
            painter.setFont(font)
            painter.setPen(QColor(20, 18, 43, 180))
            painter.drawText(self.rect().translated(6, 6), Qt.AlignmentFlag.AlignCenter,
                             self._countdown)
            painter.setPen(QColor(self._colors.get("accent", "#ffd166")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._countdown)
        painter.end()


class CaptureDisplayController:
    def __init__(self, main_window) -> None:
        self._main = main_window
        self._window: CaptureDisplayWindow | None = None
        self._theme = main_window.theme
        self._live_preview = False
        self._gallery_active = False
        self._gallery = Playlist("aleatoire")
        self._gallery_paths: tuple[Path, ...] = ()
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance_gallery)
        qapp = QApplication.instance()
        qapp.screenAdded.connect(self._screens_changed)
        qapp.screenRemoved.connect(self._screens_changed)

    def _screens_changed(self, *_args) -> None:
        QTimer.singleShot(500, self.refresh)

    def set_image(self, image: QImage) -> None:
        if self._live_preview and self._window is not None and self._window.isVisible():
            self._window.set_image(image)

    def set_live_preview(self, active: bool) -> None:
        self._live_preview = bool(active)
        self.refresh()

    def set_countdown(self, text: str) -> None:
        if self._live_preview and self._window is not None:
            self._window.set_countdown(text)

    def clear_countdown(self) -> None:
        if self._window is not None:
            self._window.set_countdown("")

    def reload_theme(self, theme) -> None:
        self._theme = theme
        if self._window is not None:
            self._window.setWindowTitle(f"{theme.app_title} : aperçu de prise de vue")
            self._window.set_colors(getattr(theme, "colors", None))
            self.refresh()

    def _background_image(self) -> QImage:
        if self._theme is not None:
            path = self._theme.folder / "visuels" / "fond_ecran3.png"
            image = QImageReader(str(path)).read()
            if not image.isNull():
                return image
        return QImage()

    def refresh(self, *_args) -> None:
        screens = QApplication.screens()
        screen = pick_third_screen(screens, self._main.screen())
        in_guestbook = self._main.current_name == "guestbook"
        self._live_preview = self._main.current_name == "capture" or (in_guestbook and self._live_preview)
        if screen is None:
            self.close()
            return
        if self._window is None:
            self._window = CaptureDisplayWindow(self._background_image(),
                                                getattr(self._theme, "colors", None),
                                                getattr(self._theme, "app_title", "Photobooth"))
        self._window.show_on(screen)
        if self._live_preview:
            self._timer.stop()
            self._gallery_active = False
            return

        paths = tuple(self._main.slideshow.photos())
        changed = paths != self._gallery_paths
        if changed:
            self._gallery_paths = paths
            self._gallery.load(paths)
        if changed or not self._gallery_active:
            self._gallery_active = True
            self._advance_gallery()
        elif not self._timer.isActive():
            self._advance_gallery()

    def _advance_gallery(self) -> None:
        if not self._gallery_active or self._window is None:
            return
        shown = False
        for _ in range(len(self._gallery)):
            path = self._gallery.next()
            if path is None:
                break
            image = self._load_gallery_photo(path)
            if not image.isNull():
                self._window.set_gallery_photo(image)
                shown = True
                break
            self._gallery.remove(path)
        if not shown:
            self._window.set_background(self._background_image())
        self._timer.start(max(5, self._main.config.dp_duree) * 1000)

    def _load_gallery_photo(self, path: Path) -> QImage:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and self._window is not None:
            reader.setScaledSize(size.scaled(
                QSize(self._window.width(), self._window.height()),
                Qt.AspectRatioMode.KeepAspectRatio,
            ))
        image = reader.read()
        if image.isNull():
            log.warning("Photo illisible sur l'écran annexe de prise de vue : %s", path)
        return image

    def close(self) -> None:
        self._timer.stop()
        self._gallery_active = False
        if self._window is not None:
            self._window.close()
            self._window = None
