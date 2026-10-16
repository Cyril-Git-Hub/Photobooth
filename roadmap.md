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

## Étape 15 — Thèmes configurables *(développée, à tester)*

- Introduire un dossier par thème regroupant les couleurs, textes, visuels d’accueil, cadres/logos, modèles de mail, décors et sons.
- Garder un thème par défaut équivalent à l’apparence actuelle.
- Habiller les écrans existants avec l’identité du thème (accueil visuel, textes utiles et cadre d’interface PNG/WebP : illustration complète à l’accueil, pourtour dégagé sur les autres écrans, masqué pendant la prise de vue).
- Sélectionner le thème dans la configuration, puis prévoir sa sélection dans l’administration si elle apporte une vraie simplicité.
- Vérifier l’inclusion des ressources dans l’exécutable.

## Étape 16 — GIF animé

- Ajouter deux modes de capture : poses espacées et rafale courte.
- Proposer boucle, boomerang, accéléré/ralenti et durée prolongée sur la dernière image.
- Réduire les dimensions et optimiser le poids du GIF ; conserver une limite de taille configurable.
- Afficher les GIF dans le diaporama et vérifier leur compatibilité avec l’envoi par mail.

## Étape 17 — Styles photo classiques

- Ajouter des rendus OpenCV : bande dessinée, croquis, aquarelle, pop-art et manga noir et blanc.
- Comparer les styles sur l’écran de résultat à partir de l’original.
- Autoriser le rendu sur toute l’image ou seulement sur la personne lorsque le détourage est disponible.
- Garder le rendu final haute qualité et mesurer le coût de l’aperçu avant d’activer un effet en direct.

## Étape 18 — Masques virtuels

- Ajouter des masques PNG transparents dans un dossier de ressources : lunettes, couronne, oreilles, moustache, etc.
- Détecter et suivre les visages, avec calcul à résolution réduite et lissage.
- Désactiver les masques si la détection échoue ou ralentit trop l’aperçu.
- Mesurer les performances sur le portable cible et vérifier l’empaquetage.

## Étape 19 — Mode défi

- Charger les défis depuis un fichier modifiable.
- Afficher une consigne avec temps de préparation, puis lancer une photo, une bande ou un GIF.
- Permettre à un défi de proposer ou imposer un format, un décor, un masque et un style déjà disponibles.
- Ajouter une légende ou une carte de résultat facultative.

## Étape 20 — Effets sonores

- Ajouter les sons de compte à rebours, déclencheur, clap et réussite.
- Permettre de régler le volume et de couper les sons depuis l’administration.
- Continuer sans erreur si un son manque ou ne peut pas être joué.
- Valider les ressources audio dans l’exécutable Windows.

## Étape 21 — Options complémentaires

À prioriser après les étapes précédentes selon tes besoins : page locale et QR code de téléchargement, livre d’or vidéo, autocollants tactiles, écran d’attente animé, album ou planche-contact. Les options seront estimées séparément avant leur développement.

## Points de vigilance transverses

- Tester l’application graphique et l’exécutable sur le portable cible avant d’ajouter plusieurs traitements en direct.
- Surveiller le temps de traitement de la caméra et réduire automatiquement la résolution ou désactiver l’aperçu d’un effet trop coûteux.
- Vérifier la licence et la taille des modèles avant toute fonction reposant sur une IA additionnelle.
- Garder une configuration de soirée courte : seules les fonctions activées par l’organisateur sont proposées aux invités.
