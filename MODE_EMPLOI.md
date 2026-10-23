# Photobooth : mode d'emploi

## Ce qu'il y a dans le dossier

| Fichier / dossier | Rôle |
|---|---|
| `lancer.bat` | **Lance la borne** (la relance toute seule si elle plante) |
| `photobooth-outils.exe` | Les mêmes outils avec une console : diagnostic, test des mails, téléchargement des modèles |
| `config.ini` | Tous les réglages (créé au premier lancement, se complète tout seul) |
| `invites.xlsx` | La liste des invités : `.xlsx`, `.xls` ou `.ods`, avec les colonnes `nom`, `prénom`, `pseudo` (facultatif), `mail` (facultatif) |
| `fonds\` | Les décors : une image 16/9 par fichier, un sous-dossier par thème |
| `cadres\` | Les cadres pour les photos uniques : PNG ou WebP avec transparence |
| `masques\` | Les masques PNG ajoutés par l'utilisateur (lunettes, moustache, etc.) |
| `themes\<nom>\defis.json` | Défis propres à ce thème ; sans défi valide, les défis intégrés dans `assets\defis.json` sont utilisés |
| `photos\` | Les photos de la soirée, un dossier par jour (les poses du photomaton sont dans `poses\`) |
| `models\` | Les modèles de détourage IA |
| `logs\` | Le journal de bord (`photobooth.log`) et le dernier diagnostic |
| `exports\` | Les exports de secours des mails non partis (créés à la demande) |

## Avant la fête (une seule fois)

1. **Modèles de détourage** (internet requis) : dans une console, `photobooth-outils.exe --telecharger-modeles`.
2. **Décors** : dépose tes images (jpg, png) dans `fonds\films`, `fonds\series`, etc.
3. **Invités** : remplis `invites.xlsx` (ou un fichier `.xls`/`.ods`) avec les colonnes `nom`, `prénom`, `pseudo` (facultatif), `mail`. Le pseudo est affiché à la place du prénom et du nom lorsqu'il est renseigné. Si le fichier a un autre nom ou emplacement, indique-le dans `[chemins]` avec `fichier_invites = ...`. Ferme-le dans ton tableur avant de lancer la borne.
4. **Cadres photo** (facultatif) : dépose des PNG ou WebP transparents dans `cadres\`. Ils seront proposés avec « Photo avec cadre ». Une image au format de la photo (par défaut 16:9) donnera le rendu le plus ajusté.
5. **Masques virtuels** (facultatif) : des lunettes, une couronne, une moustache et des oreilles de lapin sont inclus. Sur l'écran caméra, touche plusieurs icônes pour cumuler les masques ; retouche une icône pour la désactiver, ou « Aucun masque » pour tout retirer. Ajoute tes PNG transparents dans `masques\` et commence leur nom par `yeux_`, `bouche_`, `nez_`, `oreille_` ou `cheveux_` pour choisir leur placement. Pour `oreille_`, dessine une seule oreille : elle sera affichée deux fois, en miroir, de chaque côté du visage. Les anciens noms comme `lunettes`, `moustache`, `couronne` et `oreilles_lapin` restent reconnus. Les masques sont appliqués à chaque photo, pose photomaton ou image du GIF.
6. **Défis** (facultatif) : configure-les dans `themes/<nom-du-thème>/defis.json`. `themes/classique/defis.json` fournit un modèle vide ; sans défi valide pour le thème, les défis intégrés restent disponibles. Les chemins d'images sont relatifs au fichier `defis.json`. Dans `categories`, définis une fois les réglages communs puis liste les images : chaque image crée un défi, avec un identifiant généré depuis le préfixe de la catégorie (`imite-01`, `imite-02`, etc.). Dans `defis`, ajoute les défis individuels dont les options diffèrent. Chaque défi doit avoir un identifiant unique, un titre et une consigne. `format` accepte `single`, `strip` ou `gif` ; `decor` accepte `none`, `choose` ou `random`. Le champ `fond` impose un décor et remplace `decor`. `image` ou les chemins de `images` indiquent les images modèles. `masque` et `style` sont facultatifs ; les styles disponibles sont `original`, `cartoon`, `sketch`, `watercolor`, `pop_art` et `manga`. Les champs `_commentaire` sont ignorés par l’application. `actif = false` dans `[defis]` masque le bouton ; les défis GIF disparaissent si le GIF est désactivé.
   Exemple de catégorie (les images doivent exister dans le dossier du thème) :
   ```json
   {"id":"imite","titre":"Copie cette pose","consigne":"Imite la pose modele.","format":"single","decor":"none","fond":"","images":["defis/pose1.jpg","defis/pose2.jpg"]}
   ```
7. **Mails** : dans `config.ini`, section `[mail]`, renseigne `expediteur`, `mot_de_passe_application` et `adresse_organisateur` (tu reçois une copie de chaque photo).
   Avec Gmail : active la validation en 2 étapes, puis crée un « mot de passe d'application » (Compte Google > Sécurité). Gmail limite à environ 500 mails par jour.
   Ne partage jamais `config.ini` : le mot de passe y est en clair.
8. **Titre de la bande photomaton** : section `[photomaton]`, ligne `titre = ...` (et les couleurs si tu veux).
9. **Sauvegarde (conseillé)** : section `[sauvegarde]`, ligne `dossier = E:/sauvegarde-photos` (clé USB, disque externe...). Chaque photo validée y est recopiée toute seule.
10. **Thème** (facultatif) : choisis `theme = classique` dans `[general]`. Les thèmes sont dans `themes/<nom>/`; copie le dossier `classique` pour en créer un et modifier ses couleurs, textes, mail et ressources. Un cadre PNG/WebP transparent déclaré avec `cadre_interface` dans `[ressources]` s'affiche au premier plan sur les écrans du parcours, sauf pendant la prise de vue. Remplace les effets sonores en déposant des WAV portant les noms `compte_a_rebours.wav`, `declencheur.wav` ou `reussite.wav` dans `sons/`.
11. **GIF animé** (facultatif) : le bouton apparaît dans le choix du format. Réglages de disponibilité, nombre d'images, rythme et limite de poids dans la section `[gif]` de `config.ini`.
12. **Code administrateur** : change `code_admin` dans `config.ini` (1234 par défaut).
13. **Sons** : ouvre le mode administrateur (3 appuis rapides dans le coin supérieur gauche) pour couper les effets ou régler leur volume. Les réglages sont conservés dans `config.ini`.
14. **Vérifie tout** : `photobooth-outils.exe --autotest` (caméra, modèle, décors, invités, mails, écrans) puis `photobooth-outils.exe --test-mail` (envoie un vrai mail de test).

## Le jour J

1. Branche le PC **sur secteur** (la veille et l'écran éteint sont désactivés pendant la soirée).
2. **Écrans supplémentaires** : branche-les, puis Windows + P > **Étendre**. Le deuxième écran affiche le diaporama ; si un troisième écran est détecté, il affiche l'aperçu caméra pendant la prise de vue. La détection est automatique, y compris si tu branches les écrans après le lancement.
3. Lance **`lancer.bat`**.
4. Place la caméra à hauteur de visage, avec la lumière **devant** les invités et un mur uni derrière eux : c'est ce qui améliore le plus le détourage.
5. Vérifie internet (Wi-Fi) : sans réseau, les photos sont quand même prises, et les mails partent dès son retour.

## Si internet tombe (ou n'est jamais là)

- Les photos sont **toujours prises et enregistrées** ; seuls les mails attendent. Ils repartent **tout seuls** au retour du réseau (même après un redémarrage), et sans limite de temps.
- Les refus temporaires du serveur sont aussi réessayés sans limite, avec un délai plafonné à deux minutes. Les erreurs définitives (par exemple identifiants invalides) restent signalées en rouge : corrige la configuration, puis utilise **Réessayer maintenant**.
- Un **petit voyant orange ou rouge** apparaît en haut à droite de la borne, seulement quand il y a un souci : « Hors-ligne · 3 mails en attente » (orange), « mails en échec » ou « sauvegarde en panne » (rouge). Rien ne s'affiche quand tout va bien (réglage `indicateur_organisateur`).
- L'invité voit alors « Pas de connexion pour l'instant : ta photo partira dès que le réseau sera revenu ».
- **Secours** : mode admin > **Exporter les envois non partis** crée un dossier dans `exports\` avec les photos et un tableau `envois.csv` (adresse de chaque invité) pour tout envoyer à la main. Les envois partiront aussi tout seuls au retour du réseau : ne les fais pas deux fois.
- Mode admin > **Réessayer maintenant** relance tout de suite les mails (y compris ceux en échec) et la sauvegarde.

## Mode administrateur

Touche **5 fois rapidement le coin en haut à gauche** de l'écran, puis tape le code. Tu peux :
- voir l'état des mails (en attente, envoyés, en échec) et de la sauvegarde ;
- ouvrir **Gérer les activations** pour couper/rétablir les mails, la sauvegarde (si un dossier est configuré), le GIF, Casting/Audition, le QR code, le livre d'or, le diaporama secondaire et les effets sonores. Les messages mail déjà en attente sont suspendus pendant la désactivation et reprendront si tu réactives l'envoi ;
- **réessayer maintenant** les mails et la sauvegarde, ou **exporter** les envois non partis (voir ci-dessus) ;
- voir l'état du diaporama et le **vider** pour une nouvelle soirée (les photos restent dans `photos\`) ;
- **recharger la configuration** après avoir modifié `config.ini` ;
- régler le volume des effets sonores ;
- **quitter** la borne.

Avec un clavier : `Ctrl + Maj + Q`.

## Si des boutons sont coupés (petit écran)

L'interface est dessinée pour un écran **1920 × 1080** et s'adapte toute seule à l'écran du PC : sur un portable 1366 × 768 elle est réduite à environ 71 %, sur un 1280 × 720 à environ 67 %. Un écran Full HD affiché à 125 % ou 150 % dans Windows compte aussi comme un écran plus petit, et est adapté de la même façon. Au démarrage, `logs\photobooth.log` indique l'écran détecté et l'échelle choisie (ligne « Écran principal … : échelle de l'interface … »).

Si, malgré cela, des boutons du bas sont coupés ou, au contraire, si tout paraît trop petit, règle `echelle_interface` dans la section `[general]` de `config.ini` :

| Valeur | Effet |
|---|---|
| `auto` (par défaut) | Adaptée à l'écran |
| `0.7` | Interface plus petite (par exemple si des boutons sont encore coupés) |
| `1.0` | Taille « écran 1920 × 1080 » |
| `1.3` | Interface plus grande (par exemple sur un grand écran tactile) |

Le nombre doit être compris entre **0.4 et 2.0** (le point ou la virgule fonctionnent). Une valeur invalide ou hors de ces limites est ignorée : la borne repasse en `auto` (un avertissement est écrit dans `logs\photobooth.log`).

**Ce réglage ne prend effet qu'au prochain lancement** : ferme la borne (mode admin > Quitter), puis relance `lancer.bat`. « Recharger la configuration » ne suffit pas pour celui-là.

En dernier recours, un écran de la borne plus haut que l'écran du PC reste utilisable : **fais glisser le doigt** vers le haut ou le bas pour le faire défiler et atteindre les boutons. Si tu lances la borne en fenêtre (`plein_ecran = false`), la fenêtre est limitée à la taille de l'écran.

## Si quelque chose ne va pas

| Problème | Solution |
|---|---|
| « Caméra introuvable » | Ferme Teams, Zoom ou l'application Caméra de Windows. Vérifie Paramètres Windows > Confidentialité > Caméra. |
| « Modèle de détourage introuvable » | `photobooth-outils.exe --telecharger-modeles` |
| L'invité disparaît et le décor reste | `ia_inverser_masque = true` dans `config.ini` |
| L'aperçu est saccadé | `apercu_largeur = 640` dans `config.ini` |
| Contours mal découpés | Plus de lumière devant, mur uni derrière ; ou `ia_modele = multiclasse` (plus précis, plus lent) |
| Les mails n'arrivent pas | Mode admin pour voir l'état ; `photobooth-outils.exe --test-mail` donne la cause exacte ; regarde les courriers indésirables |
| Mails « en attente » | Pas d'internet : ils repartent seuls au retour du réseau (ou exporte-les à la main, mode admin) |
| Voyant rouge « sauvegarde en panne » | La clé USB ou le disque est débranché : rebranche-le, la copie reprend toute seule |
| Pas de diaporama | Windows + P > Étendre ; vérifie `second_ecran_active = true` |
| « Ouvert dans un tableur » | Ferme le fichier de la liste d'invités dans Excel ou LibreOffice |
| La borne a planté | `lancer.bat` la relance seule ; la cause est dans `logs\photobooth.log` |
| Un réglage n'a pas d'effet | Mode admin > Recharger la configuration (ou relance la borne ; `echelle_interface` demande toujours un relancement) |
| Boutons du bas coupés, interface trop grande ou trop petite | Voir « Si des boutons sont coupés (petit écran) » : réglage `echelle_interface` |

## Après la fête

- Les photos sont dans `photos\soiree_YYYY-MM-DD\` pendant une soir&eacute;e ou `photos\hors-soiree_YYYY-MM-DD\` hors soir&eacute;e ; les poses du photomaton sont rang&eacute;es dans `poses\`.
- Pour une nouvelle soirée, vide le diaporama (mode admin) ; garde ou supprime les anciennes photos comme tu veux.

## Soirées et planches-contact

Au début de chaque soirée, ouvre le mode administrateur (3 appuis rapides dans le coin supérieur gauche) et choisis **Démarrer une nouvelle soirée**. Cette soirée reste active après minuit et après un redémarrage, jusqu'au démarrage explicite de la suivante. Si une soirée est déjà active, l'application demande confirmation avant de la clôturer.

En fin de soirée ou plus tard, retourne dans le mode administrateur, sélectionne la soirée dans la liste puis choisis **Créer les planches-contact**. Une planche PNG est créée pour chaque invité identifié par son adresse mail, dans `exports\planches-contact\`. Elle inclut les photos uniques, les photos avec cadre, les bandes photomaton (une seule vignette de la bande, sans recompter les poses) et une vignette de la première image de chaque GIF. Le dossier créé s'ouvre automatiquement.

Seules les photos validées pendant une soirée active et associées à une adresse mail sont indexées. Les prises plus anciennes ne sont pas ajoutées rétroactivement. Les médias manquants ou illisibles sont ignorés et signalés après la génération. La base `data\soirees.sqlite3` conserve les associations entre soirée, invité et fichier photo.

## Écran de veille

Après le délai `inactivite_secondes` de `[general]`, l'écran de veille du thème s'affiche. Si l'invité était dans le parcours, la borne revient à l'accueil sous cet écran, sans attendre un second délai. Si elle était déjà à l'accueil, la veille s'affiche directement. Touche l'écran de veille pour révéler l'accueil, puis **Commencer** pour lancer le parcours. Le geste administrateur reste disponible dans le coin supérieur gauche. Mets le délai à `0` pour désactiver le retour automatique et l'écran de veille.

## Autocollants photo

Sur l'écran de résultat, touche une icône pour ajouter l'autocollant au centre de la photo, puis fais-le glisser au doigt pour le placer. Les commandes `−` et `+` changent sa taille, `↶` et `↻` le tournent, et `×` retire l'autocollant sélectionné. Tu peux en ajouter plusieurs. Ils sont intégrés à la photo enregistrée quand tu la valides ; **Recommencer** les abandonne avec la photo.

Les autocollants de départ sont fournis. Pour en ajouter, dépose des images PNG ou WebP transparentes, ou des SVG, dans `autocollants\` à côté de `config.ini`. Le nom du fichier sert d'infobulle.

## Livre d'or vidéo

L'option est désactivée par défaut. Pour la proposer, règle la section [livre_or] sur actif = true dans config.ini et démarre une soirée depuis le mode administrateur. Le bouton **Livre d'or vidéo**, d'une couleur distincte, apparaît dans le menu de choix du format uniquement pendant une soirée active.

Avant chaque enregistrement, l'écran explique que la vidéo et la voix seront gardées sur cet ordinateur, consultables et exportables par l'organisateur. L'invité doit accepter puis toucher **Enregistrer mon message** ; l'enregistrement s'arrête au bout de 15 secondes maximum ou au toucher de **Terminer l'enregistrement**. Un microphone par défaut doit être disponible dans Windows. Si la caméra, le micro ou l'espace disque manque (moins de 200 Mo libres), le message n'est pas enregistré et le parcours photo reste intact.

Les vidéos MP4 sont conservées dans le dossier livre-or\<identifiant-de-soirée>\, sans association à l'adresse mail. Depuis le mode administrateur, sélectionne la soirée et utilise **Ouvrir les vidéos du livre d'or** pour les consulter ou les copier vers un autre emplacement. **Supprimer les vidéos de la soirée** les efface définitivement après confirmation. Elles ne sont pas supprimées automatiquement.

## QR code de téléchargement

Cette option est **désactivée par défaut** (`[qr_drive] actif = false`). Dans cet état, aucun bouton QR n'apparaît, aucune connexion Google Drive ni aucun téléversement n'est lancé, et l'écran de remerciement garde son fonctionnement habituel.

Pour l'activer ultérieurement, règle `actif = true` dans la section `[qr_drive]` de `config.ini`, puis suis les étapes ci-dessous. Une fois le partage Drive configuré, le bouton **Afficher le QR code** ouvre un QR que l'invité peut scanner ; **Retour à la photo** revient à son résultat. Le QR donne accès au téléchargement de la photo, de la bande photomaton ou du GIF. Les poses individuelles conservées dans `photos\...\poses\` ne sont pas téléversées séparément.

Pour connecter Google Drive une seule fois :

1. Dans Google Cloud Console, crée un projet et active **Google Drive API**.
2. Configure l'écran de consentement OAuth et ajoute le champ d'application `https://www.googleapis.com/auth/drive.file`. Pour que le jeton reste renouvelable au-delà de 7 jours, mets l'application en statut **En production**. Pour un usage personnel limité à moins de 100 utilisateurs, Google n'exige pas la vérification de l'application ; un avertissement de consentement peut toutefois apparaître. Si tu la laisses en statut **Test**, le jeton de renouvellement expire après 7 jours et le nettoyage automatique mensuel ne pourra plus se connecter sans une nouvelle autorisation.
3. Crée un identifiant OAuth de type **Application de bureau**, télécharge le fichier JSON et place-le sous `data\google_drive_client.json` à côté de `main.py` (ou de l'exécutable). Ne le committe pas.
4. Avec la version de développement, ferme la borne puis exécute dans PowerShell : `.venv\Scripts\python.exe main.py --configurer-drive`. Avec la version distribuée, exécute `photobooth-outils.exe --configurer-drive` dans une console.
5. Dans le navigateur, connecte le compte Google propriétaire du Drive et autorise l'accès. Le jeton de renouvellement est conservé localement dans `data\google_drive_token.json`. Ce dossier est ignoré par Git.
6. Vérifie que la tâche est enregistrée avec `schtasks /Query /TN PhotoBoothDriveCleanup`.

La commande programme une tâche Windows qui vérifie les liens toutes les heures ; la borne fait aussi une vérification au démarrage. Google Drive ne sait pas appliquer une date d'expiration aux liens publics « toute personne disposant du lien », donc un lien peut rester accessible jusqu'au prochain passage de la tâche après son échéance. Si la tâche n'a pas pu être créée, le nettoyage se fera au prochain démarrage de la borne.

Les fichiers sont déposés dans le dossier Drive `Photobooth`. Après 30 jours, l'accès public est révoqué, mais le fichier reste dans Drive et continue d'occuper de l'espace. Si le réseau, le quota, Drive ou OAuth est indisponible, le QR est désactivé pour ce résultat ; l'enregistrement local et la mise en file du mail continuent normalement. Toute personne possédant le QR ou le lien peut télécharger le média pendant la période de partage.
