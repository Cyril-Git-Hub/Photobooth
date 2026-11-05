"""Dialogs tactiles d'authentification administrateur."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from .scale import px


def _set_button_variant(button: QPushButton, variant: str) -> None:
    button.setProperty("variant", variant)
    button.style().unpolish(button)
    button.style().polish(button)


class PatternPad(QWidget):
    """Grille tactile 3x3 : le schéma se dessine en glissant le doigt."""

    pattern_finished = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(px(320), px(320))
        self.setMaximumSize(px(480), px(480))
        self._selected: list[int] = []
        self._drawing = False
        self._cursor: QPointF | None = None
        self._color = QColor("#39b96b")

    def clear(self) -> None:
        self._selected.clear()
        self._drawing = False
        self._cursor = None
        self.update()

    @property
    def pattern(self) -> str:
        return "-".join(str(index + 1) for index in self._selected)

    def _geometry(self):
        side = min(self.width(), self.height())
        margin = side * 0.18
        radius = max(px(12), side * 0.035)
        spacing = (side - 2 * margin) / 2
        centers = [QPointF((self.width() - side) / 2 + margin + col * spacing,
                           (self.height() - side) / 2 + margin + row * spacing)
                   for row in range(3) for col in range(3)]
        return centers, radius, max(px(28), spacing * 0.28)

    def _nearest_node(self, point: QPointF) -> int | None:
        centers, _radius, hit_radius = self._geometry()
        candidates = [(center.x() - point.x()) ** 2 + (center.y() - point.y()) ** 2
                      for center in centers]
        index = min(range(9), key=candidates.__getitem__)
        return index if candidates[index] <= hit_radius ** 2 else None

    @staticmethod
    def _segment_projection(point: QPointF, start: QPointF, end: QPointF) -> tuple[float, float]:
        dx, dy = end.x() - start.x(), end.y() - start.y()
        length2 = dx * dx + dy * dy
        if not length2:
            return 0.0, float("inf")
        t = max(0.0, min(1.0, ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / length2))
        nearest_x, nearest_y = start.x() + t * dx, start.y() + t * dy
        distance = ((point.x() - nearest_x) ** 2 + (point.y() - nearest_y) ** 2) ** 0.5
        return t, distance

    def _append_node(self, index: int) -> None:
        if index in self._selected:
            return
        centers, _radius, hit_radius = self._geometry()
        if self._selected:
            start = centers[self._selected[-1]]
            end = centers[index]
            crossed = []
            for candidate, center in enumerate(centers):
                if candidate in self._selected or candidate == index:
                    continue
                t, distance = self._segment_projection(center, start, end)
                if 0 < t < 1 and distance <= hit_radius * 0.45:
                    crossed.append((t, candidate))
            self._selected.extend(candidate for _t, candidate in sorted(crossed))
        self._selected.append(index)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._selected.clear()
        self._drawing = True
        self._cursor = event.position()
        node = self._nearest_node(self._cursor)
        if node is not None:
            self._append_node(node)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if not self._drawing:
            return super().mouseMoveEvent(event)
        self._cursor = event.position()
        node = self._nearest_node(self._cursor)
        if node is not None:
            self._append_node(node)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drawing and event.button() == Qt.MouseButton.LeftButton:
            self._drawing = False
            self._cursor = None
            self.update()
            self.pattern_finished.emit(self.pattern)

    def paintEvent(self, _event) -> None:
        centers, radius, _hit_radius = self._geometry()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line_color = QColor(self._color)
        line_color.setAlpha(190)
        pen = QPen(line_color, max(px(5), radius * 0.6), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for first, second in zip(self._selected, self._selected[1:]):
            painter.drawLine(centers[first], centers[second])
        if self._drawing and self._selected and self._cursor is not None:
            painter.drawLine(centers[self._selected[-1]], self._cursor)
        for index, center in enumerate(centers):
            selected = index in self._selected
            painter.setPen(QPen(self._color if selected else QColor("#c5c3d4"), max(px(2), radius * 0.18)))
            painter.setBrush(self._color if selected else QColor(25, 23, 43, 210))
            painter.drawEllipse(center, radius, radius)
        painter.end()


class PatternDialog(QDialog):
    """Saisie d'un schéma, avec confirmation facultative lors de sa création."""

    def __init__(self, parent=None, *, confirm: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Définir le schéma" if confirm else "Accès administrateur")
        self._confirm = confirm
        self._first_pattern: str | None = None
        self.value: str | None = None
        self.switch_to: str | None = None
        screen = parent.screen() if parent else None
        available = screen.availableGeometry() if screen else None
        width = available.width() if available else px(700)
        height = available.height() if available else px(800)
        self.setMinimumSize(min(px(360), max(280, width - px(24))),
                            min(px(420), max(320, height - px(24))))
        self.resize(min(px(500), int(width * 0.9)), min(px(650), int(height * 0.9)))

        layout = QVBoxLayout(self)
        self._instruction = QLabel()
        self._instruction.setWordWrap(True)
        self._instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._instruction)
        self._pad = PatternPad(self)
        layout.addWidget(self._pad, 1, alignment=Qt.AlignmentFlag.AlignCenter)
        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)
        self._pad.pattern_finished.connect(self._on_pattern_finished)

        actions = QHBoxLayout()
        clear = QPushButton("Effacer")
        clear.setObjectName("adminAuthButton")
        _set_button_variant(clear, "secondary")
        clear.setMinimumSize(px(130), px(56))
        clear.clicked.connect(self._clear)
        actions.addWidget(clear)
        actions.addStretch(1)
        cancel = QPushButton("Annuler")
        cancel.setObjectName("adminAuthButton")
        _set_button_variant(cancel, "secondary")
        cancel.setMinimumSize(px(130), px(56))
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self._switch_button = None
        if not confirm:
            self._switch_button = QPushButton("Utiliser le code")
            self._switch_button.setObjectName("adminAuthButton")
            _set_button_variant(self._switch_button, "secondary")
            self._switch_button.setMinimumSize(px(180), px(56))
            self._switch_button.clicked.connect(self._switch_to_code)
        self._validate = QPushButton("Valider")
        self._validate.setObjectName("adminAuthButton")
        _set_button_variant(self._validate, "primary")
        self._validate.setMinimumSize(px(150), px(56))
        self._validate.setEnabled(False)
        self._validate.clicked.connect(self._accept_pattern)
        actions.addWidget(self._validate)
        layout.addLayout(actions)
        if self._switch_button is not None:
            layout.addWidget(self._switch_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._instruction.setText(
            "Relie au moins 4 points en faisant glisser ton doigt." if confirm
            else "Dessine ton schéma en reliant au moins 4 points."
        )
        if not confirm:
            self._validate.setText("Déverrouiller")

    def _clear(self) -> None:
        self._pad.clear()
        self._validate.setEnabled(False)
        self._status.clear()

    def _on_pattern_finished(self, pattern: str) -> None:
        if len(pattern.split("-")) < 4:
            self._validate.setEnabled(False)
            self._status.setText("Le schéma doit relier au moins 4 points différents.")
            return
        if self._confirm:
            if self._first_pattern is None:
                self._first_pattern = pattern
                self._pad.clear()
                self._instruction.setText("Répète le même schéma pour le confirmer.")
                self._status.setText("Schéma enregistré une première fois.")
                return
            if pattern != self._first_pattern:
                self._first_pattern = None
                self._pad.clear()
                self._instruction.setText("Les schémas sont différents. Dessine-le à nouveau.")
                self._status.clear()
                return
            self.value = pattern
            self._status.setText("Schéma confirmé.")
            self._validate.setEnabled(True)
            self._validate.setText("Enregistrer")
            return
        self.value = pattern
        self._status.setText(f"{len(pattern.split('-'))} points reliés.")
        self._validate.setEnabled(True)

    def _accept_pattern(self) -> None:
        if self.value:
            self.accept()

    def _switch_to_code(self) -> None:
        self.switch_to = "code"
        self.reject()


class PinDialog(QDialog):
    """Pavé numérique entièrement tactile pour le code administrateur."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Accès administrateur")
        self.value = ""
        self.switch_to: str | None = None
        screen = parent.screen() if parent else None
        available = screen.availableGeometry() if screen else None
        width = available.width() if available else px(700)
        height = available.height() if available else px(800)
        self.setMinimumSize(min(px(320), max(280, width - px(24))),
                            min(px(420), max(320, height - px(24))))
        self.resize(min(px(420), int(width * 0.9)), min(px(620), int(height * 0.9)))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Saisis le code administrateur."), alignment=Qt.AlignmentFlag.AlignCenter)
        self._display = QLineEdit()
        self._display.setEchoMode(QLineEdit.EchoMode.Password)
        self._display.setReadOnly(True)
        self._display.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setMinimumHeight(px(58))
        layout.addWidget(self._display)

        grid = QGridLayout()
        grid.setSpacing(px(8))
        for digit in range(1, 10):
            button = self._key(str(digit), lambda _checked=False, d=str(digit): self._append(d))
            grid.addWidget(button, (digit - 1) // 3, (digit - 1) % 3)
        grid.addWidget(self._key("Effacer", lambda: self._set_value("")), 3, 0, 1, 1)
        grid.addWidget(self._key("0", lambda: self._append("0")), 3, 1)
        grid.addWidget(self._key("⌫", self._backspace), 3, 2)
        layout.addLayout(grid)

        actions = QHBoxLayout()
        cancel = self._key("Annuler", self.reject)
        actions.addWidget(cancel)
        self._validate = self._key("Valider", self.accept)
        _set_button_variant(self._validate, "primary")
        self._validate.setEnabled(False)
        actions.addWidget(self._validate)
        layout.addLayout(actions)
        switch = self._key("Utiliser un schéma", self._switch_to_pattern)
        _set_button_variant(switch, "secondary")
        layout.addWidget(switch)

    @staticmethod
    def _key(label: str, callback) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName("adminAuthKey" if label.isdigit() or label == "⌫" else "adminAuthButton")
        _set_button_variant(button, "key")
        button.setMinimumSize(px(72), px(60))
        button.clicked.connect(callback)
        return button

    def _append(self, digit: str) -> None:
        if len(self.value) < 16:
            self._set_value(self.value + digit)

    def _backspace(self) -> None:
        self._set_value(self.value[:-1])

    def _set_value(self, value: str) -> None:
        self.value = value
        self._display.setText(value)
        self._validate.setEnabled(bool(value))

    def _switch_to_pattern(self) -> None:
        self.switch_to = "pattern"
        self.reject()
