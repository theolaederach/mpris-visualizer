# Fonctionnement de MPRIS Visualizer

Ce document explique, sans entrer dans le code, comment le programme fonctionne : ce qu'il regarde, ce qu'il affiche et comment ces éléments se coordonnent. Pour les détails techniques, voir [DOCUMENTATION.md](DOCUMENTATION.md).

## En une phrase

MPRIS Visualizer **observe** le lecteur de musique qui tourne déjà sur ton ordinateur, **écoute** le son qui sort des haut-parleurs, et **affiche** le tout dans une fenêtre. Il ne lit aucune musique lui-même.

## Les trois sources d'information

Le programme tire ses informations de trois endroits :

```
 ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
 │ Ton lecteur      │     │ Le son qui sort  │     │ La pochette      │
 │ (Spotify, VLC…)  │     │ de l'ordinateur  │     │ (image du média) │
 └────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
          │ MPRIS                  │ parec                  │ URL
          │ (playerctl)            │                        │
          ▼                        ▼                        ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │                         MPRIS Visualizer                           │
 │   titre · artiste · position · durée · spectre · couleurs          │
 └────────────────────────────────────────────────────────────────────┘
```

1. **Le lecteur** : grâce au protocole standard MPRIS, le programme demande au lecteur le titre, l'artiste, la pochette, la durée et la position actuelle. Il peut aussi lui envoyer des ordres : précédent, lecture / pause, suivant, ou aller à une position précise. C'est l'outil `playerctl` qui fait l'intermédiaire.
2. **Le son** : le programme écoute la sortie audio de l'ordinateur, sans enregistrer quoi que ce soit sur le disque. Il ne voit que l'intensité du son à chaque fréquence, à chaque instant.
3. **La pochette** : l'image est lue depuis un fichier sur ton ordinateur, ou téléchargée si le lecteur fournit une adresse web.

## Ce qui apparaît à l'écran

De haut en bas :

| Élément              | Ce qu'il montre                                            | D'où vient l'information       |
| -------------------- | ---------------------------------------------------------- | ------------------------------ |
| **Pochette**         | Image du média, au centre                                  | Le lecteur                     |
| **Titre et artiste** | Nom du morceau et de l'interprète                          | Le lecteur                     |
| **Jauge**            | Où tu en es dans le morceau, sous forme de ligne ondulante | Position et durée du lecteur   |
| **Temps**            | Temps écoulé à gauche, durée totale à droite               | Position et durée du lecteur   |
| **Boutons**          | Précédent, lecture / pause, suivant                        | Envoient des ordres au lecteur |
| **Barres**           | Les sons qui jouent, en bas de la fenêtre                  | Le son de l'ordinateur         |
| **Fond**             | Dégradé et halos colorés                                   | Les couleurs de la pochette    |

## Comment la pochette devient un fond coloré

Dès qu'une pochette arrive, le programme en extrait cinq couleurs représentatives :

1. Il réduit l'image à une petite taille, pour alléger le calcul.
2. Il regroupe les couleurs proches, puis garde celles qui apparaissent le plus souvent et qui sont les plus vives.
3. Il ne retient que des couleurs suffisamment différentes les unes des autres, pour éviter d'avoir cinq nuances presque identiques.

Ces cinq couleurs servent à trois choses :

- un **dégradé** diagonal qui passe par les cinq couleurs, assombri pour que le texte reste lisible ;
- cinq **halos** lumineux placés à différents endroits de la fenêtre ;
- les **barres** du visualiseur, éclaircies et réparties de gauche à droite.

Si le média n'a pas de pochette, un jeu de couleurs par défaut est utilisé.

## Comment les barres réagissent au son

Les barres ne sont pas une simple animation aléatoire. Elles reflètent ce qui sort réellement des haut-parleurs :

1. Le programme capte le son en continu, par petits morceaux.
2. Pour chaque morceau, il calcule la **répartition des fréquences** : quelle part de l'énergie est dans les basses, les médiums et les aigus. C'est ce qu'on appelle un spectre.
3. Les fréquences sont regroupées en bandes, de la plus grave à la plus aiguë. L'oreille perçoit mieux les différences de hauteur à basse fréquence, donc les bandes sont plus serrées dans les graves.
4. Chaque bande donne une barre. Quand le son est fort dans une bande, la barre monte. Quand le son baisse, elle redescend lentement.

Deux réglages rendent le mouvement agréable à regarder :

- **Montée rapide, retombée douce** : une barre réagit tout de suite à un son fort, mais redescend progressivement, comme un égaliseur d'autoradio.
- **Lissage entre voisines** : une barre tient compte un peu de ses voisines, ce qui évite les pics isolés et désordonnés.

Le **nombre de barres s'adapte à la largeur de la fenêtre**. Chaque barre garde la même épaisseur : une fenêtre plus large en affiche simplement davantage.

## Comment la jauge fonctionne

La jauge indique où tu en es dans le morceau.

- **Position** : le programme demande au lecteur sa position environ deux fois par seconde. Entre deux demandes, il calcule lui-même la position pour que le curseur avance sans à-coups.
- **Clic** : cliquer sur la ligne déplace la lecture à l'endroit cliqué, proportionnellement à la durée du morceau.
- **Ondulation** : la ligne ondule seulement quand la musique joue. Elle s'arrête doucement en pause. L'ondulation a une vitesse et une amplitude fixes : elle ne suit pas le rythme de la musique.
- **Sans durée** : certains flux, comme les radios en ligne, ne donnent pas leur durée. Dans ce cas, la jauge et la durée restent vides.

## Ce qui se passe quand tu appuies sur un bouton

Les boutons envoient simplement l'ordre correspondant au lecteur, par exemple « morceau suivant ». Le programme ne gère pas la file d'attente : c'est le lecteur qui décide de la suite. L'affichage (titre, pochette, temps) se met à jour à la prochaine vérification, au plus une demi-seconde plus tard.

## Ce qui se passe quand le morceau change

Toutes les demi-secondes environ, le programme vérifie l'état du lecteur. Quand le titre, l'artiste ou la pochette changent :

1. Le titre et l'artiste sont mis à jour tout de suite.
2. Si la pochette a changé, elle est chargée en arrière-plan, sans bloquer la fenêtre.
3. Une fois chargée, elle remplace l'ancienne, et les couleurs du fond sont recalculées.
4. Si tu changes de morceau pendant le chargement, la pochette précédente est ignorée, pour ne jamais afficher une image qui ne correspond plus à la musique.

## Ce qui se passe quand le lecteur s'arrête ou disparaît

- **Lecteur en pause** : la jauge s'aplatit, les barres retombent à zéro, et le bouton affiche le symbole de lecture.
- **Aucun lecteur ouvert** : la fenêtre affiche « Aucun média en lecture » et les boutons ne font rien.
- **Pas de son** : les barres restent à zéro.

Le programme ne plante pas dans ces cas. Il continue d'interroger le lecteur et reprend l'affichage dès qu'un média apparaît.

## Ce qui tourne en parallèle

Le programme fait plusieurs tâches en même temps, pour que la fenêtre reste fluide :

| Tâche                     | Rôle                      | Fréquence                      |
| ------------------------- | ------------------------- | ------------------------------ |
| Affichage                 | Dessine la fenêtre        | environ 60 fois par seconde    |
| Analyse du son            | Calcule le spectre        | environ 43 fois par seconde    |
| Lecture des infos         | Interroge le lecteur      | deux fois par seconde          |
| Chargement de la pochette | Lit ou télécharge l'image | une fois par nouvelle pochette |

Ces tâches ne bloquent pas l'une l'autre : si le téléchargement d'une pochette est lent, la musique et l'affichage continuent.

## Ce que le programme ne fait pas

- Il ne lit pas de musique et ne modifie pas le son.
- Il n'enregistre ni le son, ni l'historique d'écoute.
- Il n'envoie rien sur Internet, sauf le téléchargement de la pochette si le lecteur en fournit une adresse web.
- Il ne demande aucun compte ni aucune connexion.

## Pour aller plus loin

- [README](../README.md) : installation, utilisation et dépannage.
- [DOCUMENTATION.md](DOCUMENTATION.md) : architecture, classes, réglages et construction de l'AppImage.
