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

# MediaPipe embarque des bibliothèques et des fichiers de données que l'analyse automatique ne voit pas toujours
datas, binaries, hiddenimports = collect_all("mediapipe")
hiddenimports += collect_submodules("xlrd")
hiddenimports += collect_submodules("odf")
hiddenimports += collect_submodules("PIL")
datas.append((ICON, "assets"))                       # icône de la fenêtre (paths.resource_path)

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
