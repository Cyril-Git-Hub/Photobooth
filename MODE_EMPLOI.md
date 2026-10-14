# Photo Booth : mode d'emploi

## Ce qu'il y a dans le dossier

| Fichier / dossier | Rôle |
|---|---|
| `lancer.bat` | **Lance la borne** (la relance toute seule si elle plante) |
| `photobooth-outils.exe` | Les mêmes outils avec une console : diagnostic, test des mails, téléchargement des modèles |
| `config.ini` | Tous les réglages (créé au premier lancement, se complète tout seul) |
| `invites.xlsx` | La liste des invités : colonnes `nom`, `prénom`, `mail` (le mail peut rester vide) |
| `fonds\` | Les décors : une image 16/9 par fichier, un sous-dossier par thème |
| `photos\` | Les photos de la soirée, un dossier par jour (les poses du photomaton sont dans `poses\`) |
| `models\` | Les modèles de détourage IA |
| `logs\` | Le journal de bord (`photobooth.log`) et le dernier diagnostic |

## Avant la fête (une seule fois)

1. **Modèles de détourage** (internet requis) : dans une console, `photobooth-outils.exe --telecharger-modeles`.
2. **Décors** : dépose tes images (jpg, png) dans `fonds\films`, `fonds\series`, etc.
3. **Invités** : remplis `invites.xlsx` (ferme-le dans Excel avant de lancer la borne).
4. **Mails** : dans `config.ini`, section `[mail]`, renseigne `expediteur`, `mot_de_passe_application` et `adresse_organisateur` (tu reçois une copie de chaque photo).
   Avec Gmail : active la validation en 2 étapes, puis crée un « mot de passe d'application » (Compte Google > Sécurité). Gmail limite à environ 500 mails par jour.
   Ne partage jamais `config.ini` : le mot de passe y est en clair.
5. **Titre de la bande photomaton** : section `[photomaton]`, ligne `titre = ...` (et les couleurs si tu veux).
6. **Code administrateur** : change `code_admin` dans `config.ini` (1234 par défaut).
7. **Vérifie tout** : `photobooth-outils.exe --autotest` (caméra, modèle, décors, invités, mails, écrans) puis `photobooth-outils.exe --test-mail` (envoie un vrai mail de test).

## Le jour J

1. Branche le PC **sur secteur** (la veille et l'écran éteint sont désactivés pendant la soirée).
2. **Second écran** (diaporama) : branche-le, puis Windows + P > **Étendre**. Il se met en route tout seul, même branché après le lancement.
3. Lance **`lancer.bat`**.
4. Place la caméra à hauteur de visage, avec la lumière **devant** les invités et un mur uni derrière eux : c'est ce qui améliore le plus le détourage.
5. Vérifie internet (Wi-Fi) : sans réseau, les photos sont quand même prises, et les mails partent dès son retour.

## Mode administrateur

Touche **3 fois, vite, le coin en haut à gauche** de l'écran, puis tape le code. Tu peux :
- voir l'état des mails (en attente, envoyés, en échec) et **renvoyer ceux en échec** ;
- voir l'état du diaporama et le **vider** pour une nouvelle soirée (les photos restent dans `photos\`) ;
- **recharger la configuration** après avoir modifié `config.ini` ;
- **quitter** la borne.

Avec un clavier : `Ctrl + Maj + Q`.

## Si quelque chose ne va pas

| Problème | Solution |
|---|---|
| « Caméra introuvable » | Ferme Teams, Zoom ou l'application Caméra de Windows. Vérifie Paramètres Windows > Confidentialité > Caméra. |
| « Modèle de détourage introuvable » | `photobooth-outils.exe --telecharger-modeles` |
| L'invité disparaît et le décor reste | `ia_inverser_masque = true` dans `config.ini` |
| L'aperçu est saccadé | `apercu_largeur = 640` dans `config.ini` |
| Contours mal découpés | Plus de lumière devant, mur uni derrière ; ou `ia_modele = multiclasse` (plus précis, plus lent) |
| Les mails n'arrivent pas | Mode admin pour voir l'état ; `photobooth-outils.exe --test-mail` donne la cause exacte ; regarde les courriers indésirables |
| Mails « en attente » | Pas d'internet : ils repartent seuls au retour du réseau |
| Pas de diaporama | Windows + P > Étendre ; vérifie `second_ecran_active = true` |
| « Ouvert dans Excel » | Ferme `invites.xlsx` dans Excel |
| La borne a planté | `lancer.bat` la relance seule ; la cause est dans `logs\photobooth.log` |
| Un réglage n'a pas d'effet | Mode admin > Recharger la configuration (ou relance la borne) |

## Après la fête

- Les photos sont dans `photos\AAAA-MM-JJ\` (la bande, ou la photo unique) et `photos\AAAA-MM-JJ\poses\` (chaque pose du photomaton).
- Pour une nouvelle soirée, vide le diaporama (mode admin) ; garde ou supprime les anciennes photos comme tu veux.
