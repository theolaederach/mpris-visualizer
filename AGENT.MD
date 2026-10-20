# AGENT.MD

## 1. Vue d’ensemble du projet
- **Objectif** : Afficher un visualiseur d’audio pour les lecteurs compatibles MPRIS (Spotify, VLC, etc.) sous Linux.
- **Description** : Le programme lit les métadonnées du lecteur, capture l’audio de la sortie système et affiche une fenêtre Qt avec :
  * pochette centrée (image du média)
  * dégradé de couleurs extrait de la pochette
  * visualiseur audio (barres de fréquence)
  * jauge de progression ondulante
  * boutons contrôle (précédent / lecture / suivant)
- **Stack technique** :
  * **Langage** : Python 3.9+
  * **GUI** : PySide6 (Qt 6)
  * **Analyse audio** : numpy, FFT (parec → PCM → numpy)
  * **Dépendances** : déclarées dans `requirements.txt`
  * **Packaging** : AppImage (script `build_appimage.sh`)

## 2. Architecture et structure du projet
```
mpris-visualizer/
├── main.py          # Point d’entrée, classes et fonctions
├── requirements.txt # PySide6, numpy
├── build_appimage.sh # Build AppImage
├── README.md
├── LICENSE
├── docs/
│   ├── FONCTIONNEMENT.md
│   └── DOCUMENTATION.md
└── .gitignore
```
- **`main.py`** : contient toute la logique (threads, GUI, utilitaires).
- **`docs/`** : documentation technique et fonctionnelle.
- **`build_appimage.sh`** : génère l’AppImage autonome.

### Flux de données
1. `playerctl` (MPRIS) → métadonnées et position.
2. `parec` (monitor audio) → flux PCM → FFT → bandes → visualiseur.
3. Image pochette (local ou HTTP) → palette → dégradé + halo + barres.

## 3. Conventions de code et règles
- **Nommage** : variables en `snake_case`, classes en `PascalCase`.
- **Style** : PEP‑8 pour Python, minimal d’indentation de 4 espaces.
- **Commentaires** : uniquement sur le pourquoi, pas le comment‑how.
- **Gestion des erreurs** : fonctions utilitaires retournent une valeur par défaut (ex. chaîne vide, `None`) plutôt que d’arbres d’exception non‑capturés.
- **Logs** : pas de `print`. Utilise `logging` si besoin.
- **Thread safety** : `PlaybackState` protégé par `threading.Lock`.

## 4. État d’avancement et roadmap
- **Implémenté** :
  * Visualisation avec dégradé, barres, jauge et bouton contrôle.
  * Extraction de 5 couleurs de la pochette.
  * Thread `Analyzer` pour la FFT.
  * Thread `_poll_loop` pour `playerctl` toutes les 0.5s.
  * AppImage autonome généré par `build_appimage.sh`.
- **À faire** :
  1. Mettre la couverture de l’image en arrière‑plan (blur) – à ajouter dans `CoverWidget`.
  2. Afficher la couverture sans interroger `playerctl` (cache/éviction).
  3. Rendre l’AppImage totalement autonome (exclure Python 3 du système, empaqueter Python venv).
  4. Fichier de configuration (JSON/TOML) pour ajuster constants (palette, bar width, etc.).
  5. Tests unitaires (optionnel).

## 5. Directives pour l’Agent IA
- **Priorité** : toujours lire les fichiers `main.py` et `docs/DOCUMENTATION.md` avant de modifier.
- **Fichiers clés** : `main.py`, `build_appimage.sh`, `requirements.txt`, `docs/DOCUMENTATION.md`.
- **Style de réponse** : explications courtes en français, code en anglais. Fournir un diff des lignes modifiées.
- **Conformité** : respecter les conventions de code listées dans la section 3.
- **Validation** : après modification, proposer d’exécuter `python -m pip install -r requirements.txt && python main.py` (si possible) ou au moins de relire les diagnostics.

---
> *Ce fichier sert de mémoire rapide pour l’IA ; il est automatiquement rechargé entre les requêtes.*
