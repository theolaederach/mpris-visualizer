# MPRIS Visualizer

Un lecteur d'affichage pour Linux : il montre la pochette du média en cours, un dégradé de couleurs extrait de cette pochette, un visualiseur audio en arrière-plan, une jauge de progression ondulante et les boutons précédent / lecture / suivant.

Il fonctionne avec n'importe quel lecteur compatible **MPRIS** (Spotify, Firefox, Chromium, VLC, mpv, Rhythmbox, etc.) et se redimensionne librement, donc il s'intègre bien aux gestionnaires de fenêtres en tuiles comme Hyprland, Sway ou i3.

![Aperçu](docs/screenshot.png)

## Fonctionnalités

- **Pochette** centrée, avec coins arrondis et ombre, récupérée depuis le lecteur (fichier local ou URL).
- **Dégradé de fond** construit à partir de 5 couleurs extraites de la pochette, avec des halos colorés.
- **Visualiseur audio** : barres de largeur fixe en arrière-plan, dont le nombre s'adapte à la largeur de la fenêtre.
- **Jauge de progression** : une ligne qui ondule pendant la lecture et s'aplatit en pause. Cliquer dessus change la position de lecture.
- **Temps** écoulé et durée totale, au format `m:ss` ou `h:mm:ss`.
- **Contrôles** : précédent, lecture / pause, suivant.

## Prérequis

Le programme s'appuie sur des outils système, à installer sur la machine :

| Outil       | Rôle                                              | Paquet (exemples)                                     |
| ----------- | ------------------------------------------------- | ----------------------------------------------------- |
| `playerctl` | Lit les métadonnées MPRIS et envoie les commandes | `playerctl`                                           |
| `parec`     | Capture la sortie audio pour le visualiseur       | `pulseaudio-utils` (ou `pipewire-pulse` sur PipeWire) |

Sur **Arch / Manjaro** : `sudo pacman -S playerctl libpulse`
Sur **Debian / Ubuntu** : `sudo apt install playerctl pulseaudio-utils`
Sur **Fedora** : `sudo dnf install playerctl pulseaudio-utils`

Python et les bibliothèques graphiques sont inclus dans l'AppImage. Pour lancer le code source directement, il faut Python 3.9 ou plus, avec PySide6 et numpy.

## Installation

### Option 1 : AppImage (recommandée)

1. Télécharge `MPRIS-Visualizer-x86_64.AppImage` depuis la page des [releases](../../releases), ou construis-la (voir ci-dessous).
2. Rends-la exécutable :
   ```bash
   chmod +x MPRIS-Visualizer-x86_64.AppImage
   ```
3. Lance-la :
   ```bash
   ./MPRIS-Visualizer-x86_64.AppImage
   ```

### Option 2 : depuis le code source

```bash
git clone https://github.com/theolaederach2/mpris-visualizer.git
cd mpris-visualizer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Construire l'AppImage

Le script `build_appimage.sh` crée un environnement virtuel, y installe les dépendances, assemble l'AppDir puis produit l'AppImage.

Il faut [`appimagetool`](https://github.com/AppImage/appimagetool/releases) dans le `PATH` :

```bash
./build_appimage.sh
```

Le fichier `MPRIS-Visualizer-x86_64.AppImage` est créé à la racine du projet.

## Utilisation

Lance un média dans un lecteur compatible MPRIS, puis ouvre la fenêtre. Elle se met à jour automatiquement quand le morceau change.

- **Boutons** : précédent, lecture / pause, suivant.
- **Jauge** : clique sur la ligne pour aller à un endroit précis du morceau.
- **Redimensionnement** : la pochette et la jauge gardent les mêmes proportions. Le nombre de barres s'adapte à la largeur.

Sous Hyprland, la fenêtre peut être laissée en tuile ou basculée en flottant selon ta configuration. Comme elle est redimensionnable, la pochette, la jauge et les barres s'adaptent à la taille choisie.

## Personnalisation

Les réglages se font directement dans `main.py`, en haut du fichier et dans les classes concernées :

| Réglage                                | Emplacement             | Effet                                          |
| -------------------------------------- | ----------------------- | ---------------------------------------------- |
| `BAR_WIDTH`, `BAR_GAP`                 | en haut du fichier      | Largeur et espacement des barres (px)          |
| `COVER_RATIO`                          | en haut du fichier      | Taille de la pochette par rapport à la fenêtre |
| `PALETTE_SIZE`                         | en haut du fichier      | Nombre de couleurs extraites de la pochette    |
| `DEFAULT_PALETTE`                      | en haut du fichier      | Couleurs utilisées sans pochette               |
| `Analyzer.BANDS`                       | classe `Analyzer`       | Nombre de bandes de fréquence calculées        |
| `WAVE_AMP`, `WAVE_SPEED`, `WAVELENGTH` | classe `ProgressWidget` | Amplitude, vitesse et longueur de l'ondulation |

Pour une description détaillée, voir [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md).

## Dépannage

**La fenêtre s'ouvre mais aucune musique n'apparaît**
Vérifie que `playerctl` voit ton lecteur :

```bash
playerctl -l
playerctl metadata
```

**Les barres du visualiseur ne bougent pas**
Vérifie que `parec` est installé et que ton serveur audio est actif :

```bash
parec --version
pactl info
```

**Le message `qt.qpa.wayland.textinput ... Trying to disable ... but 0x0 is focused`**
C'est un avertissement de Qt sous Wayland, sans conséquence. Pour le masquer :

```bash
QT_LOGGING_RULES="qt.qpa.wayland.textinput=false" ./MPRIS-Visualizer-x86_64.AppImage
```

**La jauge ne montre pas la durée**
Certains lecteurs, notamment les flux web, ne fournissent pas la durée du morceau. La jauge reste alors vide.

**L'AppImage ne se lance pas**
Vérifie qu'elle est exécutable (`chmod +x`). Si elle affiche `main.py introuvable`, reconstruis-la avec `build_appimage.sh`.

## Documentation

- [Fonctionnement](docs/FONCTIONNEMENT.md) : explication du programme en langage simple.
- [Documentation technique](docs/DOCUMENTATION.md) : architecture, classes, réglages et construction de l'AppImage.

## Structure du projet

```
mpris-visualizer/
├── main.py              # Application complète
├── requirements.txt     # Dépendances Python
├── build_appimage.sh    # Script de construction de l'AppImage
├── LICENSE              # Licence GPL-3.0
├── docs/
│   ├── FONCTIONNEMENT.md   # Explication du fonctionnement
│   └── DOCUMENTATION.md    # Documentation technique
├── README.md
└── .gitignore
```

## Contribuer

Les contributions sont bienvenues. Ouvre une _issue_ pour signaler un bug ou proposer une fonctionnalité, ou une _pull request_ pour une modification.

## Licence

Ce logiciel est un logiciel libre, distribué sous la **GNU General Public License version 3** ou toute version ultérieure (`GPL-3.0-or-later`). Tu peux l'utiliser, l'étudier, le modifier et le redistribuer, à condition de conserver la même liberté pour les versions que tu diffuses. Le texte complet est dans le fichier [LICENSE](LICENSE).

Les bibliothèques utilisées restent sous leurs propres licences libres : PySide6 (LGPL-3.0), numpy (BSD-3-Clause). Les outils système `playerctl` (GPL-3.0) et `parec` (LGPL-2.1) sont appelés comme programmes séparés, et non liés au code.

## Crédits

Ce projet a été entièrement créé avec **Claude Code**, de zéro : conception, code, documentation et script de construction, avec l'assistant d'Anthropic. Il a été testé par son auteur sur sa propre machine.

PS : Je n'ai pas touché une seule ligne de code, je l'ai juste créer parce que j'avais besoin d'un visualiseur et non pour apprendre à créer une application pour interagir avec les lecteurs multimédias.
