r"""Génère assets/photobooth.ico (icône de l'exécutable et de la fenêtre).

    python tools\creer_icone.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw_icon(size: int = 512) -> Image.Image:
    """Appareil photo blanc sur un dégradé rose-violet, aux coins arrondis."""
    gradient = Image.new("RGB", (size, size))
    pixels = gradient.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size - 2)
            pixels[x, y] = (int(255 - 124 * t), int(77 - 30 * t), int(141 + 106 * t))      # #ff4d8d -> #7b2ff7
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=255)
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    icon.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(icon)
    s = size / 512
    def box(x0, y0, x1, y1): return tuple(round(v * s) for v in (x0, y0, x1, y1))
    draw.rounded_rectangle(box(150, 158, 250, 215), radius=round(14 * s), fill="white")           # bosse du viseur
    draw.rounded_rectangle(box(70, 190, 442, 394), radius=round(36 * s), fill="white")            # boîtier
    draw.ellipse(box(176, 212, 336, 372), fill=(123, 47, 247, 255))                                # objectif
    draw.ellipse(box(204, 240, 308, 344), fill=(255, 255, 255, 255))
    draw.ellipse(box(228, 264, 284, 320), fill=(255, 77, 141, 255))
    draw.ellipse(box(364, 214, 412, 262), fill=(255, 209, 102, 255))                               # flash
    return icon


def main() -> int:
    target = ROOT / "assets" / "photobooth.ico"
    target.parent.mkdir(exist_ok=True)
    draw_icon().save(target, format="ICO", sizes=[(n, n) for n in SIZES])
    print(f"Icône créée : {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
