"""Choix du rythme de capture et du rendu du GIF animé."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from ..scale import px
from ..widgets.big_button import BigButton
from .base import BaseScreen


class GifOptionsScreen(BaseScreen):
    def __init__(self, nav) -> None:
        super().__init__(nav)
        title = QLabel("Ton GIF animé")
        title.setObjectName("heading")
        self._mode_buttons = {
            "spaced": BigButton("Poses espacées", "primary"),
            "burst": BigButton("Rafale courte", "secondary"),
        }
        self._effect_buttons = {
            "loop": BigButton("Boucle", "primary"),
            "boomerang": BigButton("Boomerang", "secondary"),
            "fast": BigButton("Accéléré", "secondary"),
            "slow": BigButton("Ralenti", "secondary"),
        }
        for mode, button in self._mode_buttons.items():
            button.setMinimumSize(px(280), px(100))
            button.clicked.connect(lambda _checked=False, selected=mode: self._select_mode(selected))
        for effect, button in self._effect_buttons.items():
            button.setMinimumSize(px(250), px(88))
            button.clicked.connect(lambda _checked=False, selected=effect: self._select_effect(selected))

        mode_label = QLabel("Comment prendre les images ?")
        mode_label.setObjectName("note")
        mode_row = QHBoxLayout()
        mode_row.addStretch(1)
        for button in self._mode_buttons.values():
            mode_row.addWidget(button)
        mode_row.addStretch(1)

        effect_label = QLabel("Quel rendu ?")
        effect_label.setObjectName("note")
        effects = QGridLayout()
        effects.setSpacing(px(12))
        for index, button in enumerate(self._effect_buttons.values()):
            effects.addWidget(button, index // 2, index % 2)
        effects_host = QHBoxLayout()
        effects_host.addStretch(1)
        effects_host.addLayout(effects)
        effects_host.addStretch(1)

        self._hold = QCheckBox("Marquer une pause sur la dernière image")
        back = BigButton("Retour", "secondary")
        back.clicked.connect(lambda: self.nav.go_to("format_select"))
        start = BigButton("Continuer")
        start.clicked.connect(lambda: self.nav.go_to("capture"))
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(back)
        footer.addWidget(start)
        footer.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(40), px(20), px(40), px(20))
        layout.setSpacing(px(12))
        layout.addWidget(title)
        layout.addWidget(mode_label)
        layout.addLayout(mode_row)
        layout.addWidget(effect_label)
        layout.addLayout(effects_host)
        layout.addWidget(self._hold, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        layout.addLayout(footer)

    def on_enter(self) -> None:
        self._set_selected(self._mode_buttons, self.session.gif_capture_mode)
        self._set_selected(self._effect_buttons, self.session.gif_effect)
        self._hold.setChecked(self.session.gif_hold_last)

    @staticmethod
    def _set_selected(buttons: dict[str, BigButton], selected: str) -> None:
        for key, button in buttons.items():
            button.setProperty("variant", "primary" if key == selected else "secondary")
            button.style().unpolish(button)
            button.style().polish(button)

    def _select_mode(self, mode: str) -> None:
        self.session.gif_capture_mode = mode
        self._set_selected(self._mode_buttons, mode)

    def _select_effect(self, effect: str) -> None:
        self.session.gif_effect = effect
        self._set_selected(self._effect_buttons, effect)

    def on_leave(self) -> None:
        self.session.gif_hold_last = self._hold.isChecked()
