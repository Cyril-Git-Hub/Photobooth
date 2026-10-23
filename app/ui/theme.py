"""Styles de base adaptés au tactile, avec palette fournie par le thème actif."""
import re

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
    border: 2px solid rgba(255, 255, 255, 0.12);
    border-radius: 22px;
    padding: 18px 36px;
    font-size: 30px;
    font-weight: 600;
}
QPushButton:hover { border-color: rgba(255, 255, 255, 0.42); }
QPushButton#formatOptionButton { border-radius: 16px; padding: 10px 18px; font-size: 23px; }
QPushButton:disabled { color: rgba(244, 241, 255, 0.48); background: #2b2757; border-color: transparent; }
QPushButton[variant="primary"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff4d8d, stop:1 #d93a75);
    color: #ffffff; border-color: rgba(255, 255, 255, 0.24);
}
QPushButton[variant="primary"]:pressed { background: #d93a75; }
QPushButton[variant="secondary"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b3680, stop:1 #2b2757);
    color: #f4f1ff;
}
QPushButton[variant="secondary"]:pressed { background: #3b3680; }
QPushButton[variant="man"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3988e8, stop:1 #2465b8);
    color: #ffffff; border-color: rgba(255, 255, 255, 0.24);
}
QPushButton[variant="man"]:pressed { background: #2465b8; }
QPushButton[variant="woman"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f36da8, stop:1 #cf477f);
    color: #ffffff; border-color: rgba(255, 255, 255, 0.24);
}
QPushButton[variant="woman"]:pressed { background: #cf477f; }
QPushButton[variant="notListed"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #39a96b, stop:1 #247a4b);
    color: #ffffff; border-color: rgba(255, 255, 255, 0.24);
}
QPushButton[variant="notListed"]:pressed { background: #247a4b; }
QPushButton[variant="surprise"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8b5cf6, stop:1 #6336c9);
    color: #ffffff; border-color: rgba(255, 255, 255, 0.24);
}
QPushButton[variant="surprise"]:pressed { background: #6336c9; }
QPushButton[variant="danger"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #b3261e, stop:1 #8c1d18);
    color: #ffffff; border-color: rgba(255, 255, 255, 0.2);
}
QPushButton[variant="danger"]:pressed { background: #8c1d18; }
QPushButton[variant="guestbook"] {
    background: @guestbook_color@;
    color: #0b0a1a;
    border-color: rgba(255, 209, 102, 0.7);
}
QPushButton[variant="guestbook"]:pressed { background: @guestbook_pressed_color@; }

QPushButton[variant="key"]         { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b3680, stop:1 #2b2757); color: #f4f1ff; border-radius: 14px; padding: 6px 4px; font-size: 30px; font-weight: 600; }
QPushButton[variant="key"]:pressed { background: #ff4d8d; }
QPushButton#compactKeyButton { border-radius: 10px; padding: 2px 2px; font-size: 25px; }
QPushButton#emailNavButton { border-radius: 16px; padding: 7px 18px; font-size: 24px; }
QLabel#mailfield { font-size: 44px; font-weight: 600; color: #ffd166; background-color: #0b0a1a; border-radius: 16px; padding: 14px 24px; }
QLabel#search    { font-size: 34px; color: #ffd166; }
QLabel#error     { font-size: 26px; color: #ff6b6b; }
QLabel#badge     { font-size: 18px; font-weight: 600; padding: 6px 16px; border-radius: 14px; color: #14122b; background-color: #ffb347; }
QLabel#badge[level="error"] { color: #ffffff; background-color: #e5484d; }
QLabel#challengeReference { background-color: #201d40; border: 2px solid rgba(255, 255, 255, 0.16); border-radius: 24px; color: #b8b2d9; font-size: 24px; padding: 12px; }

QToolButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b3680, stop:1 #2b2757); border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 16px; padding: 10px; font-size: 18px; }
QToolButton:hover { border-color: rgba(255, 255, 255, 0.42); }
QToolButton:pressed { background: #3b3680; }
QToolButton#virtualMaskButton { border-radius: 10px; padding: 2px; }
QToolButton#virtualMaskButton:checked { border: 3px solid #ffd166; background: #3b3680; }
QToolButton#captureChoiceButton { border-radius: 10px; padding: 2px; }
QToolButton#captureChoiceButton:checked { border: 3px solid #ffd166; background: #3b3680; }
QToolButton#photoStickerButton { border-radius: 12px; padding: 2px; }
QToolButton#photoStickerControl { min-width: 54px; min-height: 46px; padding: 2px; font-size: 27px; font-weight: 700; }
QPushButton#styleCard {
    background: #201d40;
    border: 2px solid rgba(255, 255, 255, 0.18);
    border-radius: 16px;
    padding: 6px;
    font-size: 20px;
}
QPushButton#styleCard:hover { border-color: rgba(255, 255, 255, 0.55); background: #29264f; }
QPushButton#styleCard:checked { border: 3px solid #ffd166; background: #302b5d; }
QLabel#styleThumbnail { background-color: #0b0a1a; border-radius: 8px; color: #b8b2d9; font-size: 14px; }
QLabel#styleCardLabel { background: transparent; color: #f4f1ff; font-size: 17px; font-weight: 600; }
QLabel#styleGalleryTitle { background: transparent; color: #ffd166; font-size: 18px; font-weight: 700; }
QWidget#reviewScreen QCheckBox { spacing: 12px; font-size: 20px; }
QWidget#reviewScreen QCheckBox::indicator { width: 28px; height: 28px; }
QWidget#reviewScreen QCheckBox::indicator:unchecked { border: 2px solid #b8b2d9; border-radius: 6px; background: #201d40; }
QWidget#reviewScreen QCheckBox::indicator:checked { border: 2px solid #ffd166; border-radius: 6px; background: #3b3680; }
QFrame#boothFrame, QStackedWidget { background-color: transparent; }
QScrollArea, QScrollArea > QWidget > QWidget { background-color: transparent; }
"""


def build_stylesheet(scale: float | None = None, theme=None) -> str:
    """STYLESHEET dont les tailles sont à l'échelle de l'écran et les couleurs viennent du thème."""
    stylesheet = STYLESHEET
    if theme is not None:
        colors = theme.colors
        replacements = {
            "#14122b": colors["background"], "#f4f1ff": colors["text"], "#ffd166": colors["accent"],
            "#b8b2d9": colors["muted"], "#8f89b5": colors["summary"], "#ff4d8d": colors["primary"],
            "#d93a75": colors["primary_pressed"], "#2b2757": colors["secondary"],
            "#3b3680": colors["secondary_pressed"], "#0b0a1a": colors["mail_background"],
            "#ff6b6b": colors["error"], "#ffb347": colors["warning"], "#b3261e": colors["danger"],
            "#8c1d18": colors["danger_pressed"], "#e5484d": colors["badge_error"],
            "#3988e8": colors["man"], "#2465b8": colors["man_pressed"],
            "#f36da8": colors["woman"], "#cf477f": colors["woman_pressed"],
            "#39a96b": colors["green"], "#247a4b": colors["green_pressed"],
            "#8b5cf6": colors["surprise"], "#6336c9": colors["surprise_pressed"],
            "#201d40": colors["panel"], "#29264f": colors["panel_hover"],
            "#302b5d": colors["panel_selected"],
            "#ffc44d": colors["reference_border"], "#ffcd5f": colors["challenge_title"],
            "#12102a": colors["challenge_panel"], "#ffffff": colors["white"],
        }
        pattern = re.compile("|".join(re.escape(color) for color in replacements))
        stylesheet = pattern.sub(lambda match: replacements[match.group(0)], stylesheet)
    palette = theme.colors if theme is not None else {
        "guestbook": "#ffd166", "guestbook_pressed": "#ffb347",
    }
    stylesheet = stylesheet.replace("@guestbook_color@", palette["guestbook"])
    stylesheet = stylesheet.replace("@guestbook_pressed_color@", palette["guestbook_pressed"])
    return scale_stylesheet(stylesheet, scale)
