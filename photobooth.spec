# -*- mode: python ; coding: utf-8 -*-
"""Construction de l'exécutable Windows (dossier dist/photobooth/), via construire.bat.

Deux programmes partagent les mêmes bibliothèques :
- photobooth.exe        : la borne, sans fenêtre de console ;
- photobooth-outils.exe : le même programme avec une console, pour --autotest, --test-mail et --telecharger-modeles
                          (aucun Python n'est nécessaire sur le PC de la fête).
Les fichiers de l'utilisateur (config.ini, liste d'invités, fonds/, models/, photos/...) restent À CÔTÉ de l'exécutable.
"""
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(SPECPATH)
ICON = os.path.join(ROOT, "assets", "photobooth.ico")
FACE_CASCADE = os.path.join(ROOT, "assets", "haarcascade_frontalface_default.xml")

# MediaPipe embarque des bibliothèques et des fichiers de données que l'analyse automatique ne voit pas toujours
datas, binaries, hiddenimports = collect_all("mediapipe")
for package in ("googleapiclient", "google_auth_oauthlib", "google_auth_httplib2", "qrcode"):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports
hiddenimports += collect_submodules("xlrd")
hiddenimports += collect_submodules("odf")
hiddenimports += collect_submodules("PIL")
hiddenimports += collect_submodules("PyQt6.QtMultimedia")
datas.append((ICON, "assets"))                       # icône de la fenêtre (paths.resource_path)
datas.append((os.path.join(ROOT, "assets", "masques"), "assets/masques"))
datas.append((os.path.join(ROOT, "assets", "defis.json"), "assets"))
datas.append((os.path.join(ROOT, "assets", "defis"), "assets/defis"))
datas.append((os.path.join(ROOT, "assets", "autocollants"), "assets/autocollants"))
datas.append((FACE_CASCADE, "assets"))                # classificateur OpenCV pour les masques virtuels

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

borne = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="photobooth",
    icon=ICON,
    console=False,
    upx=False,
)
outils = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="photobooth-outils",
    icon=ICON,
    console=True,
    upx=False,
)
coll = COLLECT(
    borne, outils,
    a.binaries, a.datas,
    strip=False,
    upx=False,
    name="photobooth",
)
