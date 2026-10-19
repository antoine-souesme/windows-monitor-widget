# Mode personnalisé et fenêtre d'options

## Pourquoi

Aujourd'hui le widget a deux modes, Normal et Compact, qui empilent les
métriques choisies en une seule colonne. Chacun veut pouvoir composer son
widget librement : plusieurs colonnes, plusieurs rangs, la même métrique à
plusieurs endroits s'il le souhaite. Il n'y a pas de disposition type, la
grille est entièrement libre.

En parallèle, le menu clic droit est devenu trop chargé. Les réglages
partent dans une vraie fenêtre d'options, ce qui laisse aussi la place de
régler la grille.

## Ce qui est demandé

### Menu clic droit

Il ne contient plus que deux entrées : « Options… » et « Quitter »
(séparées par un trait). Tout le reste déménage dans la fenêtre d'options.

### Fenêtre d'options

Une fenêtre classique de Windows (avec barre de titre, déplaçable),
intitulée « Monitor Widget — Options ». Chaque changement s'applique
immédiatement au widget, il n'y a pas de bouton « Enregistrer ». Elle
contient, de haut en bas (voir la maquette validée,
`.superpowers/brainstorm/*/content/options-window.html`) :

1. **Affichage** : trois boutons radio, « Normal », « Compact »,
   « Personnalisé ».
2. Selon le mode :
   - Normal ou Compact : les cases à cocher « Métriques affichées »,
     comme dans le menu actuel.
   - Personnalisé : un bloc intitulé **« Grille mode personnalisé »**, avec
     deux listes « Colonnes » et « Rangs », puis un tableau de listes
     déroulantes, une par case, disposées comme la grille elle‑même.
3. **Options des métriques** : les options déclarées par les métriques
   (`probes.Option`), une liste déroulante par option.
4. **Général** : « Animations fluides (consomme plus de CPU) »,
   « Lancer au démarrage » (absent dans le paquet du Store, comme
   aujourd'hui), « Toujours au premier plan ».
5. Le numéro de version en petit, en bas (il était en tête du menu).

### Mode personnalisé

Chaque case de la grille affiche une seule valeur, dessinée exactement
comme une ligne du mode compact (légende et graphique en haut, nombre et
jauge en bas). Les cases sont rangées en colonnes et en rangs selon les
dimensions choisies.

La liste déroulante d'une case propose « (vide) » puis chaque valeur
mesurable **séparément** : une métrique à une valeur apparaît une fois
(« CPU », « RAM », « GPU »), une métrique à plusieurs valeurs apparaît une
fois par valeur (« Réseau réception », « Réseau envoi »). La même valeur
peut être choisie dans plusieurs cases.

Une case vide reste un emplacement vide de la grille.

### Nouveau dessin des lignes compactes

En mode Compact comme en mode Personnalisé, une valeur est redessinée
d'après la maquette de l'utilisateur
(`docs/superpowers/specs/2026-10-19-ligne-compacte.png`) :

- le graphique des 60 dernières secondes occupe tout le fond de la ligne,
  sur toute sa largeur ;
- sa courbe est un trait plein de la couleur de la valeur, et la surface
  sous la courbe est remplie de la même couleur, atténuée comme par
  transparence ;
- le nom de la valeur (« CPU ») est écrit à gauche et le nombre (« 70% »)
  à droite, par‑dessus le graphique, en blanc cerné d'un contour sombre pour
  rester lisible quelle que soit la courbe derrière ;
- la jauge reste en dessous, sur toute la largeur, comme aujourd'hui.

Le mode Normal ne change pas.

Choix faits par moi : tkinter ne gère pas la transparence d'une forme, la
surface est donc remplie d'une couleur calculée en mélangeant la couleur de
la valeur avec le fond (environ un tiers de la couleur), ce qui donne le
même effet sans hachures ; le contour des textes est obtenu en dessinant le
texte en sombre légèrement décalé tout autour, puis en blanc par‑dessus. Le
nom et le nombre ne partageant plus de colonne de gauche, la largeur de
légende commune disparaît.

## Hors du périmètre

Pas de glisser‑déposer des cases sur le widget lui‑même, pas de cases de
tailles différentes (fusion de cases), pas de modèles de disposition
proposés. Le mode Normal ne change pas d'aspect.

## Contraintes

Celles du projet (`CLAUDE.md`) s'appliquent : rien de bloquant dans la
boucle d'affichage, une configuration abîmée retombe sur les valeurs par
défaut, l'écriture du fichier se fait sur les événements significatifs,
les textes affichés sont en français et le code en anglais, aucun code
propre à une métrique dans `ui.py`. Une nouvelle métrique ajoutée avec
`@register` doit apparaître d'elle‑même dans les listes de la grille.

## Choix faits par moi (à vérifier)

- **Configuration.** Le booléen `compact` est remplacé par une clé `mode`
  (`"normal"`, `"compact"`, `"custom"`). Un fichier existant avec
  `compact: true` donne `mode: "compact"`. La grille est rangée sous
  `grid_columns`, `grid_rows` et `grid_cells` (liste de cases lues rang par
  rang ; chaque case nomme une métrique et l'indice de sa valeur, ou est
  vide). Une case qui désigne une métrique ou une valeur inconnue devient
  vide.
- **Limites.** De 1 à 6 colonnes et de 1 à 6 rangs.
- **Premier passage en mode personnalisé.** La grille démarre avec une
  colonne et autant de rangs que de valeurs affichées jusque‑là, remplies
  dans le même ordre. Depuis le mode Compact, l'écran ne change donc pas ;
  depuis le mode Normal, on retrouve les mêmes valeurs, dessinées en lignes
  compactes. Ce remplissage n'a lieu que si aucune grille n'est encore
  enregistrée.
- **Changement de dimensions.** Les cases qui restent dans la grille gardent
  leur choix, les nouvelles sont vides.
- **Largeur (choisie par l'utilisateur).** En mode personnalisé, chaque
  colonne a une largeur à elle, rangée à part sous `grid_column_width`
  (200 pixels au départ), indépendante de `width` qui reste celle des modes
  Normal et Compact. Le widget fait cette largeur multipliée par le nombre de
  colonnes (plus les marges), et tirer un bord élargit toutes les colonnes
  ensemble. Les bornes actuelles (`MIN_WIDTH`, `MAX_WIDTH`) s'appliquent à
  une colonne, et la largeur totale ne dépasse jamais celle de l'écran :
  la largeur de colonne est réduite en conséquence.
- **Option réseau.** En mode personnalisé, l'option « Réception / Envoi »
  du réseau n'a plus de sens (chaque case choisit sa valeur) et n'est pas
  montrée ; le réseau mesure alors toujours les deux. Les autres options
  (par exemple l'affichage de la RAM) s'appliquent à toutes les cases de
  cette métrique.
- **Mesures.** Une métrique est lue une seule fois par seconde même si
  plusieurs cases l'affichent ; elles partagent le même historique.
- **Fenêtre unique.** « Options… » ramène la fenêtre au premier plan si
  elle est déjà ouverte au lieu d'en ouvrir une seconde.

## Laissé au constructeur

La façon dont une métrique expose la liste de ses valeurs et leurs noms,
indépendamment de ses options ; le découpage du code de la fenêtre
d'options (un nouveau module à côté de `ui.py` est bienvenu) ; l'aspect
exact des widgets tkinter/ttk ; les tests à ajouter dans `tests/` pour la
configuration et la disposition de la grille, sans affichage.
