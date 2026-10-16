# Photo Booth (développement)

## Installation (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Construire l'exécutable Windows

```
.\construire.bat
```

Installe PyInstaller, construit `dist\photobooth\` (avec `photobooth.exe`, `photobooth-outils.exe`, `lancer.bat`, `models\` et `MODE_EMPLOI.md`),
puis lance `photobooth-outils.exe --autotest` pour vérifier le résultat. Copie ensuite le dossier `dist\photobooth` sur le PC de la fête :
aucun Python n'y est nécessaire. Lis `MODE_EMPLOI.md` pour la préparation et le jour J. `python tools\creer_icone.py` régénère l'icône.

Commandes disponibles (avec `python main.py` en développement, ou `photobooth-outils.exe` sur le PC de la fête) :
`--autotest` (diagnostic complet), `--test-mail [adresse]`, `--telecharger-modeles [noms] [--tous] [--force]`, `--version`.

## Modèles de détourage IA (une seule fois, avec internet)

```
python tools\telecharger_modele.py                (paysage + carre, petits fichiers)
python tools\telecharger_modele.py multiclasse    (optionnel : plus précis sur les vêtements, plus lent)
```

Les fichiers sont placés dans `models/`. Le modèle utilisé se règle dans `config.ini` : `ia_modele = paysage` (défaut), `carre` ou `multiclasse`.
Sans modèle, les décors affichent un message d'erreur (sauf « Sans décor »).

## Comparer les méthodes de détourage

```
python tools\comparer_detourage.py
```

Prend une photo avec la webcam (ou `--image moi.jpg`) et écrit `debug\comparaison.jpg` : pour chaque méthode, le résultat,
le masque et le temps de calcul.

## Liste d'invités

Le fichier de la liste d'invités, configuré par `[chemins] fichier_invites`, peut être `.xlsx`, `.xls` ou `.ods` (par défaut `invites.xlsx`). La première ligne contient les titres `nom`, `prénom`, `mail`,
puis une ligne par invité (le mail peut rester vide : l'invité le saisira). Le fichier est relu à chaque passage sur l'écran « Qui es-tu ? »
s'il a changé ; ferme-le dans ton tableur avant de lancer le logiciel. L'invité peut chercher son nom au clavier tactile, ou choisir
« Je ne suis pas dans la liste ». Réglage `obligatoire` de `[mail]` : `true` supprime le bouton « Passer » de l'écran du mail.

## Thèmes

Le thème actif se choisit avec `theme = classique` dans `[general]` de `config.ini`. Chaque thème est un dossier sous `themes/` contenant
un `theme.ini` et, au besoin, les sous-dossiers `fonds/`, `cadres/`, `visuels/` et `sons/`. Le manifeste permet de régler les couleurs,
le titre et le texte d'accueil, le nom de l'application et le modèle de mail. Les images d'accueil, le logo et un cadre d'interface PNG/WebP
transparent (avec le centre évidé, idéalement au format 16:9) sont facultatifs et se déclarent dans `[ressources]` avec un chemin relatif au thème,
par exemple `cadre_interface = visuels/cadre-film.png`. Le cadre complet décore l'accueil ; son seul pourtour encadre les autres écrans sans passer sous leur contenu. Il est masqué pendant la prise de vue.
Le thème classique reprend les couleurs actuelles. Les anciennes ressources `fonds/`
et `cadres/` à la racine restent utilisées si les dossiers du thème ne contiennent aucune image.

Pour créer un thème, copie `themes/classique/`, renomme le dossier, modifie son `theme.ini`, puis sélectionne son nom dans `config.ini`.
Les modifications sont prises en compte au démarrage ou avec **Recharger la configuration** dans le mode administrateur.

## Cadres photo

Dépose des images PNG ou WebP avec transparence dans `cadres/`. Le bouton « Photo avec cadre » ouvre la caméra sans décor ; l'invité peut choisir un cadre et voir le rendu en direct avant la prise. Une image au même format que la photo (16:9 par défaut) remplit le mieux l'aperçu.

## config.ini se complète tout seul

Au lancement, les réglages apparus dans les nouvelles versions sont ajoutés à `config.ini` (à la fin de leur section, avec leur commentaire).
Tes valeurs et tes commentaires ne sont jamais modifiés ; l'ancienne version est gardée dans `config.ini.bak`.

## Diaporama sur le second écran

Branche un écran ou une télé (HDMI) et choisis « Étendre ces affichages » (Windows + P) : le diaporama s'y ouvre tout seul en plein écran, même si
tu branches l'écran après le lancement. Il montre en boucle les photos validées par les invités ; une nouvelle photo s'affiche presque tout de suite.
Sans second écran, rien ne s'affiche et il n'y a aucune erreur. Réglages dans `config.ini` : `second_ecran_active` (section `[general]`),
`duree` et `ordre` (chronologique ou aleatoire) dans `[diaporama]`. Le mode admin affiche l'état du diaporama et permet de le vider pour une nouvelle soirée
(les photos restent dans `photos/`). Pour le voir sans second écran : `python main.py --windowed --diaporama-fenetre`.

## Fiabilité hors-ligne et sauvegarde

- Le serveur mail est vérifié toutes les 30 s : la borne sait qu'elle est hors-ligne avant le premier invité. Une panne réseau n'use jamais les
  essais d'un envoi (ils attendent le retour du réseau, avec 2 minutes au plus entre deux essais).
- Voyant en haut à droite (`indicateur_organisateur` dans `[general]`), caché pendant la prise de vue et quand tout va bien.
- Mode admin : « Réessayer maintenant » et « Exporter les envois non partis » (dossier `exports/envois-AAAAMMJJ-HHMMSS/` : photos + `envois.csv` + `LISEZMOI.txt`).
- Section `[sauvegarde]` : `dossier = ...` recopie chaque photo validée (et ses poses) en gardant l'arborescence `AAAA-MM-JJ/`.
  Destination débranchée : les photos restent à copier, et partent dès qu'elle revient. Journal : `data/sauvegarde.jsonl`.

## Envoi des photos par mail

Section `[mail]` de `config.ini` : `smtp_hote`, `smtp_port`, `expediteur`, `mot_de_passe_application`, `adresse_organisateur` (qui reçoit une copie de chaque photo).
Avec Gmail : active la validation en 2 étapes sur le compte, puis crée un « mot de passe d'application » (Compte Google > Sécurité) et colle-le dans
`mot_de_passe_application` (serveur `smtp.gmail.com`, port `587`). Teste avec :

```
python tools\tester_mail.py
```

Chaque photo donne un envoi à l'invité et un envoi à l'organisateur, mis en file d'attente (`data/envois.sqlite3`) et partis en arrière-plan : l'invité n'attend jamais le réseau.
Sans connexion ou lors d'un refus temporaire du serveur, les envois restent en attente et repartent seuls dès que possible, même après un redémarrage du logiciel. Le délai entre essais est plafonné à deux minutes, sans limite du nombre d'essais. Les erreurs définitives restent signalées pour intervention dans le mode administrateur. Les photos sont toujours enregistrées dans `photos/`.
`objet` et `message` (avec `{prenom}`, `{nom}`, `{salutation}`, `{titre}`, `{date}` et `\n` pour un retour à la ligne) personnalisent le mail de l'invité.
Le mode administrateur affiche l'état des envois et permet de renvoyer ceux en échec. Gmail limite à environ 500 mails par jour.

## Mode photomaton

L'invité choisit « Une seule photo » ou « Photomaton » : `nb_poses` photos (4 par défaut) prises à la suite, avec un décompte avant chacune (`duree_decompte` pour la première, `decompte_entre_poses` ensuite), puis assemblées en une bande verticale avec un titre et la date (section `[photomaton]` de `config.ini` : titre, couleurs). La bande est enregistrée dans `photos/AAAA-MM-JJ/` et les poses individuelles dans `photos/AAAA-MM-JJ/poses/`.

## Styles photo

Sur l'écran de résultat, l'invité peut comparer l'original à cinq rendus OpenCV : bande dessinée, croquis, aquarelle, pop-art et manga noir et blanc. Il peut appliquer le style à toute l'image, ou au sujet seul si le détourage est disponible. Les aperçus réduits sont chronométrés dans le journal ; le rendu final est calculé à pleine résolution après validation.

## Fluidité de l'aperçu

Le temps de calcul s'affiche dans `logs/photobooth.log` (« ms par image »). Si l'aperçu est trop lent, réduis `apercu_largeur` dans `config.ini` (640 par exemple) : la photo finale reste en pleine résolution.

## Décors

Dépose tes images (jpg, png, webp) dans les sous-dossiers de `fonds/` : un sous-dossier = un thème (films, series, dessins animés, animes japonais). Format 16/9 conseillé. La galerie relit le dossier à chaque passage.

## Miroir

`miroir = true` (config.ini) inverse l'aperçu **et** la photo finale de la même façon : la photo est exactement ce que l'invité a vu, donc bien placée par rapport au décor. Le décor, lui, n'est jamais inversé. Les textes sur les vêtements apparaissent à l'envers en miroir ; `miroir = false` supprime l'inversion partout.

## Lancer

En développement sous Windows, lance `lancer-dev.bat` depuis la racine du dépôt. Il utilise `.venv` et ouvre l'application dans une fenêtre. Dans VS Code, tu peux aussi choisir **Run and Debug > Photo Booth (interface)** (F5).

```
python main.py --windowed     (développement, fenêtre normale)
python main.py                (plein écran, mode soirée)
```

Au premier lancement, `config.ini`, `photos/`, `fonds/` (avec les 4 thèmes) et `logs/` sont créés.

Les photos sont enregistrées dans `photos/AAAA-MM-JJ/HHMMSS.jpg`.

## Tests (sans PyQt6)

```
python -m unittest discover -s tests -t .
```

## Accès administrateur

- Dans l'appli : 3 appuis rapides dans le coin haut gauche de l'écran, puis le code (`code_admin`, 1234 par défaut).
- En développement : `Ctrl+Maj+Q`.
