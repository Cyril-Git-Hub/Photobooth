r"""Compare les méthodes de détourage sur une même image et produit debug/comparaison.jpg.

    python tools\comparer_detourage.py                    # prend une photo avec la webcam dans 3 secondes
    python tools\comparer_detourage.py --image moi.jpg    # ou utilise une image existante
    python tools\comparer_detourage.py --decor fonds\films\mon_decor.jpg

Chaque ligne montre le résultat (à gauche) et le masque (à droite, blanc = personne), avec le temps de calcul.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.config import Config  # noqa: E402
from app.core import backgrounds, webcam  # noqa: E402
from app.core.compositor import blend, cover_resize  # noqa: E402
from app.core.models import MODELS  # noqa: E402
from app.core.segmentation import AiSegmenter, ChromaKeySegmenter, ChromaParams, SegmentationError  # noqa: E402

TILE_W, TILE_H = 480, 270
RUNS = 5


def capture(config: Config) -> np.ndarray:
    cap = webcam.open_capture(config.camera_index, config.resolution_largeur, config.resolution_hauteur)
    if cap is None:
        sys.exit("Caméra introuvable. Utilise --image pour travailler sur une photo existante.")
    for remaining in (3, 2, 1):
        print(f"Photo dans {remaining}…")
        start = time.time()
        while time.time() - start < 1:
            cap.read()                       # on continue à lire : l'exposition se stabilise
    frame = None
    for _ in range(5):
        ok, image = cap.read()
        frame = image if ok else frame
    cap.release()
    if frame is None:
        sys.exit("La caméra n'a pas fourni d'image.")
    return frame


def label(image: np.ndarray, text: str) -> np.ndarray:
    # cv2.putText ne gère pas les accents : les libellés sont en ASCII
    cv2.putText(image, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(image, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return image


def tile(image: np.ndarray, text: str) -> np.ndarray:
    return label(cover_resize(image, TILE_W, TILE_H), text)


def default_decor(width: int, height: int) -> np.ndarray:
    ramp = np.linspace(0, 255, width, dtype=np.uint8)
    decor = np.zeros((height, width, 3), np.uint8)
    decor[:, :, 0], decor[:, :, 2] = ramp[None, :], 255 - ramp[None, :]
    decor[:, :, 1] = 120
    return decor


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare les méthodes de détourage")
    parser.add_argument("--image", type=Path, help="image à utiliser au lieu de la webcam")
    parser.add_argument("--decor", type=Path, help="décor à incruster")
    args = parser.parse_args()

    config = Config.load()
    if args.image:
        frame = backgrounds.load_image(args.image)
        if frame is None:
            sys.exit(f"Image illisible : {args.image}")
    else:
        frame = capture(config)
        if config.miroir:
            frame = cv2.flip(frame, 1)
    frame = webcam.shrink(frame, 1280)            # taille proche de celle de l'aperçu, pour des temps comparables
    height, width = frame.shape[:2]

    decor_path = args.decor
    if decor_path is None:
        themes = backgrounds.scan_backgrounds(config.dossier_fonds)
        decor_path = themes[0].images[0] if themes else None
    decor_source = backgrounds.load_image(decor_path) if decor_path else None
    decor = cover_resize(decor_source if decor_source is not None else default_decor(width, height), width, height)

    variants: list[tuple[str, object]] = []
    for name, spec in MODELS.items():
        path = config.dossier_modeles / spec.filename
        if path.is_file():
            variants.append((f"IA {name} + filtre guide", lambda p=path, s=spec: AiSegmenter(p, s.input_size, config.ia_inverser_masque)))
    carre = config.dossier_modeles / MODELS["carre"].filename
    if carre.is_file():
        variants.append(("IA carre, ANCIENNE methode", lambda: AiSegmenter(carre, MODELS["carre"].input_size, config.ia_inverser_masque, guided=False)))
    variants.append(("fond vert (reglages config.ini)", lambda: ChromaKeySegmenter(ChromaParams.from_config(config))))

    rows = [np.hstack([tile(frame, "image d'origine"), tile(decor, "decor")])]
    print(f"{'méthode':36s} temps")
    for title, factory in variants:
        try:
            segmenter = factory()
        except SegmentationError as exc:
            print(f"{title:36s} ignorée : {exc.args[0].splitlines()[0]}")
            continue
        segmenter.segment(frame)                                  # échauffement
        start = time.perf_counter()
        for _ in range(RUNS):
            mask = segmenter.segment(frame)
        ms = 1000 * (time.perf_counter() - start) / RUNS
        segmenter.close()
        result = blend(segmenter.clean_frame(frame, mask), mask, decor)
        mask_view = cv2.cvtColor((mask * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        print(f"{title:36s} {ms:5.0f} ms")
        rows.append(np.hstack([tile(result, f"{title} - {ms:.0f} ms"), tile(mask_view, "masque")]))

    out_dir = ROOT / "debug"
    out_dir.mkdir(exist_ok=True)
    ok, buffer = cv2.imencode(".jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 92])
    (out_dir / "comparaison.jpg").write_bytes(buffer.tobytes())   # write_bytes : chemins accentués
    print(f"\nRésultat : {out_dir / 'comparaison.jpg'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
