# Roadmap Photobooth

L’étape 10 est terminée et constitue la base actuelle. Cette feuille de route commence donc à l’étape 11. Le travail avance **une étape à la fois** : je développe une étape, tu testes l’application avec son interface, puis on passe à la suivante après ton feu vert. Les tests automatisés et le lancement de l’application ne seront exécutés que selon ce que tu demandes pour l’étape.

Les fonctions optionnelles devront pouvoir être activées ou désactivées dans la configuration afin de garder un parcours simple pour les invités. Les médias (cadres, sons, masques, thèmes) resteront remplaçables sans modifier le code, lorsque c’est adapté.

## Étape 11 — Formats de fichier pour la liste d’invités *(validée)*

- Conserver le format `.xlsx` et ajouter `.xls` et `.ods` pour les listes d’invités.
- Lire les mêmes colonnes (nom, prénom, mail), reconnaître les variantes de titres déjà acceptées et conserver le comportement actuel de recherche/tri.
- Afficher une erreur compréhensible pour les formats invalides, protégés ou illisibles.
- Ajouter les dépendances nécessaires et les inclure dans les instructions et l’empaquetage de l’application.
- Ne pas convertir ni modifier le fichier source de l’utilisateur.

## Étape 12 — Cadre sur une photo unique sans décor ajouté *(validée)*

- Ajouter au parcours un choix explicite, par exemple un bouton « Photo avec cadre » à côté de la photo sans décor classique.
- Après ce choix, ouvrir la caméra sans décor ajouté et proposer les cadres disponibles dans un répertoire dédié que l’organisateur pourra alimenter.
- Afficher le cadre sélectionné en superposition dans l’aperçu caméra, afin que l’invité puisse voir le rendu avant de prendre la photo et changer de cadre.
- Prévoir un dossier `cadres/` alimentable avec des images PNG ou WebP transparentes, adaptées à la composition de la photo ; ignorer proprement les fichiers invalides.
- Appliquer exactement le rendu affiché à la photo finale enregistrée et envoyée.
- Laisser inchangés le parcours sans cadre, les photos avec décor et les bandes photomaton.

## Étape 13 — Fiabilité de la file d’envoi *(validée)*

- *(Déjà présent dans la base)* La file sur disque, l’indicateur discret, le renvoi immédiat depuis l’administration et l’export CSV avec les photos.
- Réessayer sans limite les erreurs temporaires, avec un délai croissant plafonné ; les erreurs définitives restent signalées pour intervention manuelle.
- Reprendre automatiquement les envois qui avaient été abandonnés à 60 essais par une ancienne version.
- Préserver la file sur disque et son fonctionnement après redémarrage.

## Étape 14 — Copie de sauvegarde des photos *(validée)*

- Pouvoir copier les photos vers un second dossier configurable, par exemple un disque externe ou une clé USB.
- Gérer proprement l’absence ou la déconnexion de la destination sans interrompre la séance.
- Signaler l’état de la sauvegarde dans les diagnostics et les journaux.

## Étape 15 — Thèmes configurables *(validée)*

- Introduire un dossier par thème regroupant les couleurs, textes, visuels d’accueil, cadres/logos, modèles de mail, décors et sons.
- Garder un thème par défaut équivalent à l’apparence actuelle.
- Habiller les écrans existants avec l’identité du thème (accueil visuel, textes utiles et cadre d’interface PNG/WebP au premier plan, masqué pendant la prise de vue).
- Sélectionner le thème dans la configuration, puis prévoir sa sélection dans l’administration si elle apporte une vraie simplicité.
- Vérifier l’inclusion des ressources dans l’exécutable.

## Étape 16 — GIF animé *(validée)*

- Ajouter deux modes de capture : poses espacées et rafale courte.
- Proposer boucle, boomerang, accéléré/ralenti et durée prolongée sur la dernière image.
- Réduire les dimensions et optimiser le poids du GIF ; conserver une limite de taille configurable.
- Afficher les GIF dans le diaporama et vérifier leur compatibilité avec l’envoi par mail.
- Réglages dans `[gif]` : activation, nombre d'images, intervalle de rafale, durée des images et limite maximale en Mo.
- Choix invité : poses espacées ou rafale courte ; boucle, boomerang, accéléré ou ralenti ; pause finale facultative.

## Étape 17 — Styles photo classiques *(validée)*

- Ajouter des rendus OpenCV : bande dessinée, croquis, aquarelle, pop-art et manga noir et blanc.
- Présenter l’original et les styles dans une galerie tactile de vignettes, avec aperçu agrandi au toucher et commandes toujours visibles.
- Renforcer les rendus : aplats et contours BD, papier ivoire pour le croquis, pigments aquarelle, tramage pop-art et trames manga.
- Autoriser le rendu sur toute l’image ou seulement sur la personne lorsque le détourage est disponible.
- Garder le rendu final haute qualité et mesurer le coût de l’aperçu avant d’activer un effet en direct.
- Les rendus ne sont pas appliqués pendant la capture : l'invité compare l'original et les aperçus réduits à l'écran de résultat ; le style choisi est recalculé à pleine résolution lors de la validation.

## Étape 18 — Masques virtuels *(validée)*

- Ajouter des masques PNG transparents et permettre d'en ajouter dans `masques/` avec des préfixes de placement (`yeux_`, `bouche_`, `nez_`, `oreille_`, `cheveux_`) ; un masque `oreille_` représente une oreille, dupliquée en miroir.
- Détecter les visages à résolution réduite, lisser leur position et appliquer le masque à chaque personne détectée.
- Afficher le masque sur l'aperçu puis sur les photos, poses photomaton et images GIF.
- Permettre de sélectionner plusieurs masques simultanément et de les retirer individuellement.
- Désactiver le masque si la détection échoue ou ralentit trop l'aperçu, sans bloquer la prise de vue.
- Vérifier les performances et l'empaquetage PyInstaller.

## Étape 19 — Mode défi *(validée)*

- Charger les défis depuis un fichier JSON modifiable et laisser désactiver leur bouton dans la configuration.
- Fournir dix défis de départ : imitation illustrée, statue de la Liberté, star du rock, couverture de magazine, émotions en bande, statue de cire, danse GIF, explosion de joie, décor choisi et décor surprise.
- Afficher la consigne et l'image de référence avant le parcours photo ; garder la consigne visible sur l'écran de capture.
- Laisser chaque défi proposer le format photo, photomaton ou GIF, un décor, un masque et un style ; réutiliser les réglages existants du GIF et du photobooth.
- Inscrire le nom du défi en haut de la photo finale, de chaque image du GIF et de la bande photomaton.

## Étape 20 — Effets sonores *(validée)*

- Ajouter les sons de compte à rebours, de déclencheur et de réussite.
- Permettre de régler le volume et de couper les sons depuis l’administration.
- Continuer sans erreur si un son manque ou ne peut pas être joué.
- Valider les ressources audio dans l’exécutable Windows.

## Étape 21 — Planches-contact par invité et par soirée *(validée)*

- Depuis l'administration, démarrer une nouvelle soirée ; son identifiant reste actif après minuit et après un redémarrage, jusqu'au démarrage explicite de la suivante.
- Associer durablement chaque résultat photo validé à l'adresse mail de l'invité, à la soirée et au fichier enregistré ; ne pas dépendre du dossier daté ni de la file d'envoi des mails.
- Depuis l'administration, choisir une soirée et générer à la demande, en fin de soirée ou plus tard, une planche-contact pour chaque invité identifié par son adresse mail.
- Inclure les photos uniques, celles avec cadre, les bandes photomaton et les GIF. Sur une planche fixe, montrer une vignette du GIF ; représenter la bande photomaton comme une bande afin d'éviter de compter ses poses deux fois.
- Enregistrer les planches dans un dossier d'export associé à la soirée ; les fichiers restent disponibles après la génération.

## Étape 22 — Écran de veille *(validée)*

- Afficher un écran d'attente attractif lorsque la borne n'est pas utilisée, avec le thème actif et une invitation claire à commencer.
- Réagir au toucher pour revenir au parcours d'accueil ; conserver l'accès administrateur.
- Afficher l'écran de veille à l'expiration du délai `inactivite_secondes` déjà configurable ; si l'invité est dans le parcours, revenir à l'accueil sous l'écran de veille sans attendre un second délai.
- Utiliser les visuels et couleurs du thème actif ; afficher une invitation tactile pour commencer.
- Garder le geste d'accès administrateur disponible depuis l'écran de veille.
- Vérifier que l'écran d'attente ne perturbe ni la caméra, ni le diaporama du second écran, ni le retour automatique déjà en place.

## Étapes suivantes — ordre de priorité proposé

### Étape 23 — Autocollants tactiles *(à cadrer)*

- Depuis l'aperçu du résultat, choisir des autocollants et les placer au doigt sur la photo.
- Déplacer, redimensionner, tourner ou retirer chaque autocollant avant de valider ; appliquer le même montage au fichier final.
- Fournir une petite sélection de départ et permettre à l'organisateur d'en ajouter dans un dossier dédié.
- Garder cette étape facultative et distincte des masques de visage et des cadres plein format.

### Étape 24 — QR code de partage *(à cadrer)*

- Afficher après validation un QR code propre à la photo, qui ouvre son téléchargement sur le téléphone de l'invité.
- Choisir un hébergement accessible aux invités et définir la durée de disponibilité des liens ainsi que les règles d'accès avant le développement.
- Prévoir un message clair si le réseau ou le service d'hébergement est indisponible ; le téléchargement QR ne doit pas empêcher l'enregistrement ni l'envoi par mail.
- La page locale et le serveur local ne font pas partie du projet retenu.

### Étape 25 — Livre d'or vidéo *(à cadrer)*

- Proposer aux invités volontaires d'enregistrer un court message vidéo après leur parcours photo.
- Permettre de passer cette étape, limiter la durée et vérifier clairement l'espace disque disponible.
- Ranger les vidéos par soirée et prévoir leur consultation/export depuis l'administration.
- Définir avant développement le consentement à l'enregistrement, l'information affichée et la suppression des vidéos.

## Points de vigilance transverses

- Tester l’application graphique et l’exécutable sur le portable cible avant d’ajouter plusieurs traitements en direct.
- Surveiller le temps de traitement de la caméra et réduire automatiquement la résolution ou désactiver l’aperçu d’un effet trop coûteux.
- Vérifier la licence et la taille des modèles avant toute fonction reposant sur une IA additionnelle.
- Garder une configuration de soirée courte : seules les fonctions activées par l’organisateur sont proposées aux invités.
