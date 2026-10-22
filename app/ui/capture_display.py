"""Aperçu caméra plein écran sur le troisième écran, sans commandes tactiles."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QImageReader, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from ..core.screens import pick_third_screen


class CaptureDisplayWindow(QWidget):
    def __init__(self, background: QImage) -> None:
        super().__init__()
        self.setWindowTitle("Photo Booth : aperçu de prise de vue")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self._background = background
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

    def set_countdown(self, text: str) -> None:
        self._countdown = text
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0a1a"))
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
            painter.setPen(QColor("#ffd166"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._countdown)
        painter.end()


class CaptureDisplayController:
    def __init__(self, main_window) -> None:
        self._main = main_window
        self._window: CaptureDisplayWindow | None = None
        self._theme = main_window.theme
        self._live_preview = False
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
        if not self._live_preview and self._window is not None:
            self._window.set_background(self._background_image())

    def set_countdown(self, text: str) -> None:
        if self._live_preview and self._window is not None:
            self._window.set_countdown(text)

    def clear_countdown(self) -> None:
        if self._window is not None:
            self._window.set_countdown("")

    def reload_theme(self, theme) -> None:
        self._theme = theme
        if self._window is not None and not self._live_preview:
            self._window.set_background(self._background_image())

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
            self._window = CaptureDisplayWindow(self._background_image())
        elif not self._live_preview:
            self._window.set_background(self._background_image())
        self._window.show_on(screen)

    def close(self) -> None:
        if self._window is not None:
            self._window.close()
            self._window = None
