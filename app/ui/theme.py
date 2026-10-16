"""Thème sombre et fun, adapté au tactile (gros boutons, grandes polices)."""
from .scale import scale_stylesheet

STYLESHEET = """
QWidget {
    background-color: #14122b;
    color: #f4f1ff;
    font-family: "Segoe UI", sans-serif;
    font-size: 22px;
}
QLabel#title   { font-size: 56px; font-weight: 700; color: #ffd166; }
QLabel#heading { font-size: 40px; font-weight: 700; color: #ffd166; }
QLabel#note    { font-size: 24px; color: #b8b2d9; }
QLabel#summary { font-size: 18px; color: #8f89b5; }

QPushButton {
    border: none;
    border-radius: 22px;
    padding: 18px 36px;
    font-size: 30px;
    font-weight: 600;
}
QPushButton[variant="primary"]           { background-color: #ff4d8d; color: white; }
QPushButton[variant="primary"]:pressed   { background-color: #d93a75; }
QPushButton[variant="secondary"]         { background-color: #2b2757; color: #f4f1ff; }
QPushButton[variant="secondary"]:pressed { background-color: #3b3680; }
QPushButton[variant="danger"]            { background-color: #b3261e; color: white; }
QPushButton[variant="danger"]:pressed    { background-color: #8c1d18; }

QPushButton[variant="key"]         { background-color: #2b2757; color: #f4f1ff; border-radius: 14px; padding: 6px 4px; font-size: 30px; font-weight: 600; }
QPushButton[variant="key"]:pressed { background-color: #ff4d8d; }
QLabel#mailfield { font-size: 44px; font-weight: 600; color: #ffd166; background-color: #0b0a1a; border-radius: 16px; padding: 14px 24px; }
QLabel#search    { font-size: 34px; color: #ffd166; }
QLabel#error     { font-size: 26px; color: #ff6b6b; }
QLabel#badge     { font-size: 18px; font-weight: 600; padding: 6px 16px; border-radius: 14px; color: #14122b; background-color: #ffb347; }
QLabel#badge[level="error"] { color: white; background-color: #e5484d; }

QToolButton { background-color: #2b2757; border: none; border-radius: 16px; padding: 10px; font-size: 18px; }
QToolButton:pressed { background-color: #3b3680; }
QScrollArea, QScrollArea > QWidget > QWidget { background-color: transparent; }
"""


def build_stylesheet(scale: float | None = None) -> str:
    """STYLESHEET dont toutes les tailles (polices, marges, arrondis) sont à l'échelle de l'écran."""
    return scale_stylesheet(STYLESHEET, scale)
