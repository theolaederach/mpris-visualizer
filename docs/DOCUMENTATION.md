# Documentation technique — MPRIS Visualizer

Ce document décrit l'architecture du programme, son fonctionnement interne, ses réglages et ses limites. Pour une explication sans jargon, voir [FONCTIONNEMENT.md](FONCTIONNEMENT.md). Pour l'installation et l'utilisation, voir le [README](../README.md).

Licence : GPL-3.0-or-later. Le projet a été créé entièrement avec Claude Code, de zéro.

## Sommaire

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture](#2-architecture)
3. [Flux de données](#3-flux-de-données)
4. [Modules et classes](#4-modules-et-classes)
5. [Réglages](#5-réglages)
6. [Construction de l'AppImage](#6-construction-de-lappimage)
7. [Performances](#7-performances)
8. [Limites connues](#8-limites-connues)

---

## 1. Vue d'ensemble

MPRIS Visualizer est une application de bureau écrite en Python, avec une interface Qt (PySide6). Elle combine trois sources de données :

| Source                 | Outil                                     | Usage                                                           |
| ---------------------- | ----------------------------------------- | --------------------------------------------------------------- |
| Métadonnées du lecteur | `playerctl` (MPRIS)                       | Titre, artiste, pochette, durée, position, état lecture / pause |
| Audio système          | `parec` (monitor de la sortie par défaut) | Spectre pour le visualiseur et les barres                       |
| Pochette               | Fichier local (`file://`) ou HTTP(S)      | Image affichée et source des couleurs                           |

L'application ne lit aucun son. Elle observe le lecteur déjà en cours et lui envoie des commandes.

## 2. Architecture

Le programme utilise trois types de threads :

```
┌─────────────────────────┐        ┌──────────────────────────┐
│ Thread principal (Qt)   │◄───────│ _poll_loop (thread)      │
│ - VisualizerWindow      │ signal │ playerctl metadata/pos   │
│ - rendu (paintEvent)    │        │ toutes les 0,5 s         │
│ - QTimer 16 ms          │        └──────────────────────────┘
└────────▲────────────────┘
         │ lecture de données partagées
┌────────┴────────────────┐        ┌──────────────────────────┐
│ Analyzer (thread)       │        │ Chargement pochette      │
│ parec → FFT → bandes    │        │ (thread ponctuel)        │
└─────────────────────────┘        └──────────────────────────┘
```

- **Thread principal** : toute l'interface. Qt n'autorise pas à modifier les widgets depuis un autre thread, donc les résultats des threads de fond passent par des signaux (`Bridge`).
- **`_poll_loop`** : interroge `playerctl` toutes les 0,5 s et publie l'état dans `PlaybackState`. Il n'émet un signal que si les métadonnées changent.
- **`Analyzer`** : lit en continu le flux PCM de `parec`, calcule le spectre et le stocke dans `bands`.
- **Chargement de la pochette** : un thread ponctuel par nouvelle pochette. Le résultat n'est appliqué que si la pochette correspond toujours à la piste en cours, ce qui évite d'afficher une image périmée.

## 3. Flux de données

### 3.1 Métadonnées

```
playerctl metadata --format "{{status}} ||| {{title}} ||| {{artist}} ||| {{mpris:artUrl}} ||| {{mpris:length}}"
```

La sortie est découpée sur le séparateur `|||`. La durée est fournie en microsecondes par MPRIS et convertie en secondes.

### 3.2 Position

`playerctl position` renvoie la position en secondes. Elle est lue toutes les 0,5 s, puis interpolée à l'affichage (`PlaybackState.snapshot`) pour que le temps et la jauge avancent fluidement entre deux lectures.

### 3.3 Audio

`parec` diffuse des échantillons `s16le`, mono, à 44 100 Hz, depuis `@DEFAULT_MONITOR@` (la sortie audio par défaut en lecture de monitor). Pour chaque trame :

1. Les 1 024 nouveaux échantillons sont ajoutés à une fenêtre glissante de 2 048 échantillons.
2. Une FFT à fenêtre de Hann est calculée.
3. Le spectre est regroupé en `BANDS` bandes logarithmiques, de 40 Hz à 16 kHz.
4. Les valeurs sont passées en racine carrée, amplifiées légèrement vers les aigus, puis lissées avec leurs voisines.

Le résultat est stocké dans `Analyzer.bands`.

### 3.4 Affichage des barres

À chaque image (`paintEvent`) :

1. Le nombre de barres `n` est calculé à partir de la largeur de la fenêtre : `n = (largeur + gap) / (largeur_barre + gap)`.
2. Les `BANDS` valeurs sont rééchantillonnées vers `n` barres par interpolation linéaire.
3. Chaque hauteur est lissée dans le temps : montée rapide (`k = 28 /s`) et retombée douce (`k = 9 /s`), avec un coefficient calculé selon le temps écoulé.

## 4. Modules et classes

Tout le programme est dans `main.py`.

### Fonctions utilitaires

| Fonction                        | Rôle                                                                                                    |
| ------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `playerctl(*args)`              | Exécute `playerctl` et renvoie sa sortie, ou une chaîne vide en cas d'erreur ou de délai dépassé (2 s). |
| `load_image_bytes(url)`         | Lit une pochette en local ou la télécharge (délai de 5 s).                                              |
| `fmt_time(seconds)`             | Formate une durée en `m:ss` ou `h:mm:ss`.                                                               |
| `extract_palette(image, count)` | Extrait les couleurs de la pochette (voir 4.1).                                                         |
| `white_icon(icon, size)`        | Recolore une icône standard Qt en blanc.                                                                |

### 4.1 Extraction de la palette

1. La pochette est réduite à 48 × 48 pixels.
2. Chaque pixel est rangé dans un seau (32 niveaux par canal) ; le seau garde le nombre de pixels et la somme des couleurs.
3. Chaque seau reçoit un score : `nombre_de_pixels × (0,2 + saturation)`. Les couleurs vives et fréquentes sont favorisées.
4. Les couleurs sont choisies par score décroissant, en gardant seulement celles qui sont à plus de 60 unités de distance euclidienne des précédentes.
5. Si moins de `PALETTE_SIZE` couleurs sont trouvées, `DEFAULT_PALETTE` complète la liste.

### 4.2 Classes

| Classe                       | Rôle                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------ |
| `PlaybackState`              | Position, durée et état de lecture, avec interpolation à l'affichage. Protégé par un verrou.           |
| `Analyzer(threading.Thread)` | Capture audio, FFT, bandes de fréquence. Démon, arrêté proprement à la fermeture.                      |
| `Bridge(QObject)`            | Signaux `meta_changed` et `cover_loaded` pour transmettre les données aux threads Qt.                  |
| `CoverWidget(QWidget)`       | Dessine la pochette centrée, avec ombre et coins arrondis. Garde en cache la version mise à l'échelle. |
| `ProgressWidget(QWidget)`    | Dessine la jauge ondulante. Émet `seek_requested` lors d'un clic.                                      |
| `VisualizerWindow(QWidget)`  | Fenêtre principale : mise en page, boutons, mise à jour, rendu de l'arrière-plan et des barres.        |

### 4.3 Cycle de rendu

| Élément                   | Fréquence                              | Mise en cache                      |
| ------------------------- | -------------------------------------- | ---------------------------------- |
| Dégradé et halos          | Au changement de taille ou de pochette | Oui (`_bg`)                        |
| Barres                    | Chaque image (≈ 60 /s)                 | Non, mais les valeurs sont lissées |
| Pochette mise à l'échelle | Au changement de taille ou de pochette | Oui (`_scaled`)                    |
| Labels de temps           | Seulement si le texte change           | Comparaison avec `_times`          |
| Jauge                     | Chaque image                           | Non                                |

### 4.4 Ondulation de la jauge

L'ondulation est indépendante de la musique. Elle est purement cosmétique :

- Pendant la lecture, la phase avance de `WAVE_SPEED` radians par seconde.
- L'amplitude vaut `WAVE_AMP` pendant la lecture, et revient à 0 en pause, avec un lissage exponentiel.
- La longueur d'onde est fixée par `WAVELENGTH`.

## 5. Réglages

### Constantes générales (en haut de `main.py`)

| Constante         | Valeur par défaut     | Description                                                                          |
| ----------------- | --------------------- | ------------------------------------------------------------------------------------ |
| `SEP`             | `"                    |                                                                                      |     | "`  | Séparateur des champs retournés par `playerctl`. Ne doit pas apparaître dans les titres. |
| `PALETTE_SIZE`    | `5`                   | Nombre de couleurs extraites de la pochette.                                         |
| `COVER_RATIO`     | `0.9`                 | Taille de la pochette, en proportion du plus petit côté. La jauge suit cette valeur. |
| `BAR_WIDTH`       | `6`                   | Largeur d'une barre, en pixels.                                                      |
| `BAR_GAP`         | `3`                   | Espace entre deux barres, en pixels.                                                 |
| `DEFAULT_PALETTE` | 5 couleurs fixes      | Utilisée sans pochette ou si l'extraction échoue.                                    |
| `GLOW_POSITIONS`  | 5 positions relatives | Centres des halos colorés de l'arrière-plan.                                         |

### Analyseur (`Analyzer`)

| Attribut            | Valeur             | Effet                                                                                |
| ------------------- | ------------------ | ------------------------------------------------------------------------------------ |
| `RATE`              | `44100`            | Fréquence d'échantillonnage demandée à `parec`.                                      |
| `HOP`               | `1024`             | Nouveaux échantillons par trame. Plus petit = réactivité accrue, plus de calcul.     |
| `N`                 | `2048`             | Taille de la FFT. Plus grand = meilleure résolution des basses, réaction plus lente. |
| `BANDS`             | `40`               | Nombre de bandes calculées.                                                          |
| Plage de fréquences | 40 Hz – 16 kHz     | Bornes de `geomspace` dans `__init__`.                                               |
| Montée / retombée   | `28` / `9` (en /s) | Dans `VisualizerWindow._bar_values`.                                                 |

### Jauge (`ProgressWidget`)

| Attribut     | Valeur           | Effet                                         |
| ------------ | ---------------- | --------------------------------------------- |
| `WAVE_AMP`   | `3.0` px         | Amplitude de l'ondulation pendant la lecture. |
| `WAVE_SPEED` | `2π × 0,8` rad/s | Vitesse de défilement de l'onde.              |
| `WAVELENGTH` | `90` px          | Longueur d'une période de l'onde.             |
| Hauteur      | `40` px          | `setFixedHeight` dans `__init__`.             |

### Fenêtre et intervalles

| Réglage                             | Valeur          | Emplacement                      |
| ----------------------------------- | --------------- | -------------------------------- |
| Taille initiale                     | 380 × 600       | `VisualizerWindow.__init__`      |
| Taille minimale                     | 260 × 380       | `VisualizerWindow.__init__`      |
| Intervalle d'interrogation MPRIS    | 0,5 s           | `_poll_loop`                     |
| Délai `playerctl`                   | 2 s             | `playerctl()`                    |
| Délai de téléchargement de pochette | 5 s             | `load_image_bytes()`             |
| Rafraîchissement de l'interface     | 16 ms (≈ 60 /s) | `QTimer` dans `VisualizerWindow` |

## 6. Construction de l'AppImage

`build_appimage.sh` procède en cinq étapes :

1. **Environnement de build** : création d'un venv dans `build/venv`, puis installation de `requirements.txt`.
2. **Copie des dépendances** : `site-packages` est copié dans `build/AppDir/usr/lib/mpris-visualizer/`.
3. **Code** : `main.py` est copié dans le même dossier.
4. **Lanceur** : le script `AppRun` cherche `main.py` dans l'AppDir (sans chemin fixe) et lance Python avec `PYTHONPATH` pointant vers les dépendances embarquées.
5. **Métadonnées** : fichier `.desktop` et icône SVG, puis appel à `appimagetool`.

Pour modifier le nom de l'AppImage, change la variable `OUT`. Le nom de l'application dans le dossier interne est défini par `APP_ID`.

### Dépannage du build

| Message                                | Cause probable                                                                |
| -------------------------------------- | ----------------------------------------------------------------------------- |
| `appimagetool introuvable`             | `appimagetool` n'est pas dans le `PATH`.                                      |
| `main.py introuvable dans l'AppImage`  | Le contenu de l'AppImage ne correspond pas au script. Reconstruis-la.         |
| `python3: can't open file .../main.py` | Ancienne AppImage dont le lanceur pointe vers un chemin fixe. Reconstruis-la. |

Pour inspecter le contenu d'une AppImage sans la lancer :

```bash
./MPRIS-Visualizer-x86_64.AppImage --appimage-extract
ls squashfs-root/usr/lib/*
```

## 7. Performances

Le programme a été conçu pour limiter le travail à chaque image :

- **Une seule FFT par trame** (environ 43 trames/s), au lieu d'un calcul par bande.
- **Dégradé et halos mis en cache**, redessinés seulement au changement de taille ou de pochette.
- **Pochette redimensionnée une seule fois**, puis réutilisée.
- **Labels de temps mis à jour seulement si le texte change**.
- **Interrogation de `playerctl` espacée** : deux appels toutes les 0,5 s, dans un thread séparé.

Pour réduire la charge sur une machine modeste, augmente `HOP` ou diminue `BANDS`. Pour un rendu plus fin, fais l'inverse.

## 8. Limites connues

- **Un seul lecteur à la fois** : `playerctl` suit le lecteur considéré comme actif. Pour cibler un lecteur précis, ajoute `--player=<nom>` aux appels dans `playerctl()`.
- **Durée absente pour certains flux** : les radios et certains flux web ne fournissent pas `mpris:length`. La jauge reste vide.
- **Pochettes HTTP bloquantes** : le téléchargement est limité à 5 secondes, mais une pochette lente retarde l'affichage de la nouvelle image.
- **Sortie audio par défaut** : le visualiseur écoute la sortie par défaut. Si la musique sort ailleurs (casque Bluetooth sélectionné après le lancement, par exemple), les barres peuvent rester à zéro.
- **Avertissement Qt sous Wayland** : le message `qt.qpa.wayland.textinput` est sans conséquence. Voir le README pour le masquer.
- **Pas de mise en pause de l'analyse** : `parec` tourne même quand rien ne joue.
