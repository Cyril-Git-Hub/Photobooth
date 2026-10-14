import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

from app.config import Config
from app.core import segmentation
from app.core.segmentation import (
    AiSegmenter, ChromaKeySegmenter, ChromaParams, SegmentationError,
    clean_coarse, refine_coarse_mask, refine_mask, segmenter_key,
)

GREEN = (0, 255, 0)  # BGR


def green_scene(width=120, height=80):
    """Fond vert avec un « invité » gris au centre."""
    frame = np.zeros((height, width, 3), np.uint8)
    frame[:] = GREEN
    frame[20:60, 40:80] = (120, 120, 120)
    return frame


class RefineMaskTests(unittest.TestCase):
    def test_extremes_et_monotonie(self):
        values = refine_mask(np.linspace(0, 1, 101, dtype=np.float32))
        self.assertEqual(float(values[0]), 0.0)
        self.assertEqual(float(values[-1]), 1.0)
        self.assertTrue(np.all(np.diff(values) >= -1e-6))
        self.assertAlmostEqual(float(refine_mask(np.float32(0.5))), 0.5, places=5)
        self.assertEqual(float(refine_mask(np.float32(0.2))), 0.0)
        self.assertEqual(float(refine_mask(np.float32(0.8))), 1.0)


# ---------------------------------------------------------------- nettoyage du masque du modèle

def blob(shape, y0, y1, x0, x1, value=1.0):
    mask = np.zeros(shape, np.float32)
    mask[y0:y1, x0:x1] = value
    return mask


class CleanCoarseTests(unittest.TestCase):
    SHAPE = (144, 256)

    def test_ilot_parasite_supprime(self):
        coarse = blob(self.SHAPE, 20, 130, 80, 180) + blob(self.SHAPE, 5, 12, 5, 14, 0.9)
        out = clean_coarse(coarse)
        self.assertEqual(float(out[8, 9]), 0.0)
        self.assertEqual(float(out[70, 130]), 1.0)

    def test_la_plus_grande_zone_est_toujours_gardee(self):
        coarse = blob(self.SHAPE, 60, 66, 100, 120)       # ~0,3 % de l'image : une personne très éloignée
        self.assertEqual(float(clean_coarse(coarse)[63, 110]), 1.0)

    def test_plusieurs_personnes_conservees(self):
        coarse = blob(self.SHAPE, 20, 130, 20, 100) + blob(self.SHAPE, 30, 130, 150, 230)
        out = clean_coarse(coarse)
        self.assertEqual(float(out[70, 60]), 1.0); self.assertEqual(float(out[70, 190]), 1.0)

    def test_trou_incertain_entoure_par_la_personne_comble(self):
        coarse = blob(self.SHAPE, 20, 130, 60, 200)
        coarse[60:90, 100:150] = 0.4                       # le modèle hésite sur un vêtement
        out = clean_coarse(coarse)
        self.assertEqual(float(out[75, 125]), 1.0)

    def test_jour_franc_conserve(self):
        coarse = blob(self.SHAPE, 20, 130, 60, 200)
        coarse[60:90, 100:150] = 0.02                      # le modèle est sûr : c'est le fond (bras sur la hanche)
        out = clean_coarse(coarse)
        self.assertLess(float(out[75, 125]), 0.05)

    def test_trou_qui_touche_le_bord_non_comble(self):
        coarse = blob(self.SHAPE, 0, 144, 60, 200)
        coarse[0:50, 100:150] = 0.4                        # encoche ouverte vers le haut de l'image
        out = clean_coarse(coarse)
        self.assertLess(float(out[20, 125]), 0.5)          # pas comblé : reste du fond

    def test_trou_trop_grand_non_comble(self):
        coarse = blob(self.SHAPE, 5, 139, 20, 236)
        coarse[30:110, 60:200] = 0.4                       # ~30 % de l'image : ce n'est plus un détail
        self.assertLess(float(clean_coarse(coarse)[70, 130]), 0.5)   # pas comblé : reste du fond

    def test_aucune_personne(self):
        out = clean_coarse(np.zeros(self.SHAPE, np.float32))
        self.assertEqual(float(out.max()), 0.0)

    def test_entree_non_modifiee(self):
        coarse = blob(self.SHAPE, 20, 130, 60, 200); coarse[60:90, 100:150] = 0.4
        before = coarse.copy()
        clean_coarse(coarse)
        self.assertTrue(np.array_equal(coarse, before))


# ---------------------------------------------------------------- agrandissement guidé

def synthetic_scene(width=480, height=270, seed=1):
    """Pièce texturée + personne (tête, torse, bras) ; renvoie l'image BGR et le masque exact."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width]
    room = np.stack([120 + 30 * np.sin(xx / 45.0), 130 + 25 * np.cos(yy / 35.0), 125 + 0 * xx], -1).astype(np.float32)
    room += rng.normal(0, 4, room.shape)
    s = 3
    gt = np.zeros((height * s, width * s), np.uint8)
    sx, sy = width / 960, height / 540
    def P(x, y): return (int(x * sx * s), int(y * sy * s))
    def A(a, b): return (int(a * sx * s), int(b * sy * s))
    cv2.ellipse(gt, P(480, 170), A(70, 90), 0, 0, 360, 255, -1)
    cv2.rectangle(gt, P(330, 250), P(630, 540), 255, -1)
    cv2.ellipse(gt, P(310, 380), A(45, 150), 15, 0, 360, 255, -1)
    cv2.ellipse(gt, P(650, 380), A(45, 150), -15, 0, 360, 255, -1)
    gt = cv2.resize(gt, (width, height), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    person = np.zeros((height, width, 3), np.float32)
    person[:] = (60, 70, 170)
    person[: int(140 * sy)] = (120, 150, 200)
    person[int(380 * sy):int(470 * sy), int(400 * sx):int(560 * sx)] = (122, 130, 126)   # vêtement de la couleur du mur
    person += rng.normal(0, 3, person.shape)
    image = np.clip(room * (1 - gt[..., None]) + person * gt[..., None], 0, 255).astype(np.uint8)
    return image, gt


@unittest.skipUnless(segmentation._HAS_GUIDED_FILTER, "opencv-contrib (filtre guidé) non disponible")
class GuidedRefinementTests(unittest.TestCase):
    def setUp(self):
        self.image, self.truth = synthetic_scene()
        height, width = self.truth.shape
        coarse = cv2.GaussianBlur(cv2.resize(self.truth, (256, 144), interpolation=cv2.INTER_AREA), (0, 0), 1.2)
        coarse[100:124, 107:150] = 0.42      # hésitation du modèle sur le vêtement clair
        coarse[5:12, 5:14] = 0.8             # îlot parasite dans le fond
        self.coarse = coarse
        solid = (self.truth > 0.5).astype(np.uint8)
        self.edge = (cv2.dilate(solid, np.ones((7, 7))) - cv2.erode(solid, np.ones((7, 7)))) > 0
        self.cloth = np.zeros_like(self.edge); self.cloth[int(380 / 2):int(470 / 2), int(400 / 2):int(560 / 2)] = True
        self.corner = np.zeros_like(self.edge); self.corner[5:25, 5:30] = True

    def error(self, mask, region=None):
        diff = np.abs(mask - self.truth)
        return float(diff.mean() if region is None else diff[region].mean())

    def test_contours_bien_meilleurs_que_l_ancienne_methode(self):
        old = refine_coarse_mask(self.image, self.coarse, guided=False)
        new = refine_coarse_mask(self.image, self.coarse, guided=True)
        self.assertLess(self.error(new, self.edge), 0.5 * self.error(old, self.edge))
        self.assertLess(self.error(new), self.error(old))

    def test_vetement_clair_et_ilot(self):
        old = refine_coarse_mask(self.image, self.coarse, guided=False)
        new = refine_coarse_mask(self.image, self.coarse, guided=True)
        self.assertGreater(self.error(old, self.cloth), 0.3)      # l'ancienne méthode laisse un trou
        self.assertLess(self.error(new, self.cloth), 0.05)
        self.assertGreater(self.error(old, self.corner), 0.1)
        self.assertLess(self.error(new, self.corner), 0.02)

    def test_sortie_float32_entre_0_et_1(self):
        for guided in (True, False):
            mask = refine_coarse_mask(self.image, self.coarse, guided=guided)
            self.assertEqual(mask.dtype, np.float32); self.assertEqual(mask.shape, self.truth.shape)
            self.assertGreaterEqual(float(mask.min()), 0.0); self.assertLessEqual(float(mask.max()), 1.0)


class FallbackTests(unittest.TestCase):
    def test_repli_sans_filtre_guide(self):
        image, truth = synthetic_scene(240, 135)
        coarse = cv2.resize(truth, (256, 144), interpolation=cv2.INTER_AREA)
        with mock.patch.object(segmentation, "_HAS_GUIDED_FILTER", False):
            mask = refine_coarse_mask(image, coarse, guided=True)
        self.assertEqual(mask.shape, truth.shape); self.assertEqual(mask.dtype, np.float32)
        self.assertLess(float(np.abs(mask - truth).mean()), 0.05)


# ---------------------------------------------------------------- fond vert

class ChromaKeyTests(unittest.TestCase):
    def test_masque_personne_sur_fond_vert(self):
        mask = ChromaKeySegmenter(ChromaParams()).segment(green_scene())
        self.assertEqual(mask.dtype, np.float32)
        self.assertEqual(mask.shape, (80, 120))
        self.assertGreater(float(mask[40, 60]), 0.99)      # centre de l'invité
        self.assertLess(float(mask[5, 5]), 0.01)            # fond
        self.assertLess(float(mask[75, 115]), 0.01)

    def test_grains_isoles_et_trous_nettoyes(self):
        frame = green_scene()
        frame[5, 5] = (120, 120, 120)     # un pixel parasite dans le fond
        frame[40, 60] = GREEN             # un trou dans l'invité
        mask = ChromaKeySegmenter(ChromaParams(adoucissement=0)).segment(frame)
        self.assertLess(float(mask[5, 5]), 0.01)
        self.assertGreater(float(mask[40, 60]), 0.99)

    def test_adoucissement_cree_un_degrade_sur_les_bords(self):
        hard = ChromaKeySegmenter(ChromaParams(adoucissement=0)).segment(green_scene())
        soft = ChromaKeySegmenter(ChromaParams(adoucissement=4)).segment(green_scene())
        self.assertEqual(set(np.unique(hard).round(3)), {0.0, 1.0})
        self.assertGreater(len(np.unique(soft.round(3))), 2)

    def test_les_seuils_sont_pris_en_compte(self):
        frame = np.zeros((40, 40, 3), np.uint8)
        frame[:] = (40, 120, 40)    # vert sombre : saturation 170, valeur 120
        strict = ChromaKeySegmenter(ChromaParams(valeur_min=200, adoucissement=0)).segment(frame)
        loose = ChromaKeySegmenter(ChromaParams(valeur_min=40, adoucissement=0)).segment(frame)
        self.assertGreater(float(strict.mean()), 0.99)   # trop sombre pour être du fond : « personne »
        self.assertLess(float(loose.mean()), 0.01)

    def test_despill_uniquement_sur_le_contour(self):
        seg = ChromaKeySegmenter(ChromaParams(adoucissement=2, despill=True))
        frame = green_scene()
        frame[40, 41] = (100, 160, 100)    # reflet vert près du bord de l'invité
        frame[40, 60] = (100, 160, 100)    # même couleur au milieu de l'invité : ne doit pas bouger
        mask = seg.segment(frame)
        cleaned = seg.clean_frame(frame, mask)
        self.assertEqual(int(cleaned[40, 41, 1]), 100)          # vert ramené à max(bleu, rouge)
        self.assertEqual(int(cleaned[40, 60, 1]), 160)          # intact
        self.assertEqual(int(cleaned[40, 41, 0]), 100)          # bleu et rouge inchangés
        off = ChromaKeySegmenter(ChromaParams(despill=False))
        self.assertIs(off.clean_frame(frame, mask), frame)


# ---------------------------------------------------------------- IA (MediaPipe simulé)

class FakeMask:
    def __init__(self, array):
        self._array = array

    def numpy_view(self):
        return self._array


def fake_mediapipe(masks_for):
    """Faux module mediapipe : `masks_for(rgb)` renvoie la liste des masques du résultat."""
    recorded = types.SimpleNamespace(options=None, closed=False)
    mp = types.ModuleType("mediapipe")
    mp.Image = lambda image_format, data: types.SimpleNamespace(data=data, format=image_format)
    mp.ImageFormat = types.SimpleNamespace(SRGB="SRGB")
    tasks = types.ModuleType("mediapipe.tasks")
    python = types.ModuleType("mediapipe.tasks.python")
    vision = types.ModuleType("mediapipe.tasks.python.vision")
    python.BaseOptions = lambda **kw: types.SimpleNamespace(**kw)
    vision.RunningMode = types.SimpleNamespace(IMAGE="IMAGE")
    vision.ImageSegmenterOptions = lambda **kw: types.SimpleNamespace(**kw)

    class Segmenter:
        def segment(self, image):
            return types.SimpleNamespace(confidence_masks=[FakeMask(m) for m in masks_for(image.data)])

        def close(self):
            recorded.closed = True

    def create_from_options(options):
        recorded.options = options
        return Segmenter()

    vision.ImageSegmenter = types.SimpleNamespace(create_from_options=create_from_options)
    mp.tasks, tasks.python, python.vision = tasks, python, vision
    modules = {"mediapipe": mp, "mediapipe.tasks": tasks,
               "mediapipe.tasks.python": python, "mediapipe.tasks.python.vision": vision}
    return modules, recorded


def person_in(rgb):
    """Masque « personne au centre » à la résolution de l'image envoyée au modèle."""
    h, w = rgb.shape[:2]
    mask = np.zeros((h, w), np.float32)
    mask[h // 8: 7 * h // 8, w // 4: 3 * w // 4] = 1.0
    return mask


class AiSegmenterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="modèle é ")
        self.addCleanup(self._tmp.cleanup)
        self.model = Path(self._tmp.name) / "modele.tflite"
        self.model.write_bytes(b"MODELE-BIDON")
        self.frame = np.zeros((72, 128, 3), np.uint8)

    def make(self, masks_for, invert=False, input_size=(256, 144), guided=True):
        modules, recorded = fake_mediapipe(masks_for)
        with mock.patch.dict(sys.modules, modules):
            seg = AiSegmenter(self.model, input_size, invert, guided)
        return seg, recorded

    def test_modele_absent(self):
        with self.assertRaises(SegmentationError) as ctx:
            AiSegmenter(self.model.with_name("absent.tflite"))
        self.assertIn("telecharger_modele", ctx.exception.args[0])

    def test_mediapipe_non_installe(self):
        with mock.patch.dict(sys.modules, {"mediapipe": None}):
            with self.assertRaises(SegmentationError) as ctx:
                AiSegmenter(self.model)
        self.assertIn("pip install", ctx.exception.args[0])

    def test_modele_charge_depuis_un_buffer(self):
        _, recorded = self.make(lambda rgb: [person_in(rgb)])
        self.assertEqual(recorded.options.base_options.model_asset_buffer, b"MODELE-BIDON")
        self.assertTrue(recorded.options.output_confidence_masks)
        self.assertFalse(recorded.options.output_category_mask)

    def test_le_modele_recoit_exactement_la_taille_qu_il_attend(self):
        seen = []
        for size in [(256, 144), (256, 256)]:
            seg, _ = self.make(lambda rgb: seen.append(rgb.shape) or [person_in(rgb)], input_size=size)
            seg.segment(self.frame)
        self.assertEqual(seen, [(144, 256, 3), (256, 256, 3)])

    def test_deux_masques_la_personne_est_l_indice_1(self):
        seg, _ = self.make(lambda rgb: [1 - person_in(rgb), person_in(rgb)])
        mask = seg.segment(self.frame)
        self.assertEqual(mask.shape, (72, 128)); self.assertEqual(mask.dtype, np.float32)
        self.assertGreater(float(mask[36, 64]), 0.99)
        self.assertLess(float(mask[2, 2]), 0.01)

    def test_un_seul_masque_est_la_personne(self):
        seg, _ = self.make(lambda rgb: [person_in(rgb)])
        self.assertGreater(float(seg.segment(self.frame)[36, 64]), 0.99)

    def test_multiclasse_la_personne_est_tout_sauf_le_fond(self):
        def six_masks(rgb):
            person = person_in(rgb)
            return [1 - person] + [person / 5] * 5          # 0 = fond, 1..5 = parties de la personne
        seg, _ = self.make(six_masks, input_size=(256, 256))
        mask = seg.segment(self.frame)
        self.assertGreater(float(mask[36, 64]), 0.99); self.assertLess(float(mask[2, 2]), 0.01)

    def test_masque_inverse_sur_demande(self):
        seg, _ = self.make(lambda rgb: [person_in(rgb)], invert=True)
        mask = seg.segment(self.frame)
        self.assertLess(float(mask[36, 64]), 0.01)
        self.assertGreater(float(mask[2, 2]), 0.99)

    def test_le_masque_a_toujours_la_taille_de_l_image(self):
        for shape in [(72, 128, 3), (270, 480, 3), (540, 960, 3)]:
            seg, _ = self.make(lambda rgb: [person_in(rgb)])
            self.assertEqual(seg.segment(np.zeros(shape, np.uint8)).shape, shape[:2])

    def test_masque_a_trois_dimensions(self):
        seg, _ = self.make(lambda rgb: [person_in(rgb)[:, :, None]])
        self.assertEqual(seg.segment(self.frame).shape, (72, 128))

    def test_aucun_masque(self):
        seg, _ = self.make(lambda rgb: [])
        with self.assertRaises(SegmentationError):
            seg.segment(self.frame)

    def test_image_envoyee_en_rgb(self):
        seen = {}
        def masks_for(rgb):
            seen["pixel"] = tuple(rgb[0, 0])
            return [person_in(rgb)]
        seg, _ = self.make(masks_for)
        frame = np.zeros((72, 128, 3), np.uint8); frame[:] = (10, 20, 30)   # BGR uniforme
        seg.segment(frame)
        self.assertEqual(seen["pixel"], (30, 20, 10))                        # RGB

    def test_la_copie_du_masque_est_independante(self):
        base = person_in(np.zeros((144, 256, 3)))
        seg, _ = self.make(lambda rgb: [base])
        seg.segment(self.frame)
        self.assertEqual(float(base[72, 128]), 1.0)                           # le masque de MediaPipe n'est pas modifié

    def test_ancienne_methode_encore_disponible_pour_comparer(self):
        seg, _ = self.make(lambda rgb: [person_in(rgb)], guided=False)
        self.assertGreater(float(seg.segment(self.frame)[36, 64]), 0.99)

    def test_fermeture(self):
        seg, recorded = self.make(lambda rgb: [person_in(rgb)])
        seg.close()
        self.assertTrue(recorded.closed)

    def test_modele_illisible(self):
        modules, _ = fake_mediapipe(lambda rgb: [])
        modules["mediapipe.tasks.python.vision"].ImageSegmenter = types.SimpleNamespace(
            create_from_options=mock.Mock(side_effect=RuntimeError("fichier corrompu")))
        with mock.patch.dict(sys.modules, modules):
            with self.assertRaises(SegmentationError) as ctx:
                AiSegmenter(self.model)
        self.assertIn("fichier corrompu", ctx.exception.args[0])


class FactoryTests(unittest.TestCase):
    def test_cle_et_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config.load(base_dir=Path(tmp))
            key_ai = segmenter_key(config)
            self.assertEqual(key_ai[0], "ia")
            config.ia_modele = "carre"
            self.assertNotEqual(segmenter_key(config), key_ai)       # changer de modèle recrée le segmenteur
            config.mode_detourage = "fond_vert"
            key_green = segmenter_key(config)
            self.assertEqual(key_green[0], "fond_vert")
            self.assertIsInstance(segmentation.create_segmenter(config), ChromaKeySegmenter)
            config.fv_teinte_max = 90
            self.assertNotEqual(segmenter_key(config), key_green)    # un réglage change la clé
            config.mode_detourage = "ia"
            with self.assertRaises(SegmentationError):               # pas de modèle dans le dossier de test
                segmentation.create_segmenter(config)

    def test_le_modele_choisi_donne_sa_taille_d_entree(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config.load(base_dir=Path(tmp))
            config.ensure_directories()
            modules, _ = fake_mediapipe(lambda rgb: [person_in(rgb)])
            for name, size, filename in [("paysage", (256, 144), "selfie_segmenter_landscape.tflite"),
                                         ("carre", (256, 256), "selfie_segmenter.tflite")]:
                config.ia_modele = name
                self.assertEqual(config.fichier_modele_ia.name, filename)
                config.fichier_modele_ia.write_bytes(b"x")
                with mock.patch.dict(sys.modules, modules):
                    seg = segmentation.create_segmenter(config)
                self.assertEqual(seg._input_size, size)


if __name__ == "__main__":
    unittest.main()
