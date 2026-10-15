#!/usr/bin/env bash
# Construit MPRIS-Visualizer-x86_64.AppImage
# Prérequis de build : python3 (avec venv), appimagetool dans le PATH.
# Prérequis à l'exécution (sur la machine de l'utilisateur) : python3, playerctl,
# et parec (paquet pulseaudio-utils ou pipewire-pulse).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_ID="MPRIS-Visualizer"
BUILD="$HERE/build"
APPDIR="$BUILD/AppDir"
LIBDIR="$APPDIR/usr/lib/$APP_ID"
OUT="$HERE/MPRIS-Visualizer-x86_64.AppImage"

if ! command -v appimagetool >/dev/null 2>&1; then
    echo "appimagetool introuvable. Télécharge-le sur https://github.com/AppImage/appimagetool/releases" >&2
    exit 1
fi

rm -rf "$BUILD"
mkdir -p "$APPDIR/usr/bin" "$LIBDIR"

# 1. Dépendances Python installées dans un venv de build, puis copiées dans l'AppDir
python3 -m venv "$BUILD/venv"
"$BUILD/venv/bin/pip" install --upgrade pip
"$BUILD/venv/bin/pip" install -r "$HERE/requirements.txt"
cp -r "$BUILD"/venv/lib/python3*/site-packages "$LIBDIR/site-packages"

# 2. Code de l'application
cp "$HERE/main.py" "$LIBDIR/main.py"

# 3. Lanceur : cherche main.py et site-packages à l'intérieur de l'AppImage,
#    sans chemin codé en dur, pour éviter les écarts de nom.
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
MAIN="$(find "$HERE/usr/lib" -maxdepth 2 -name main.py | head -n 1)"
if [ -z "$MAIN" ]; then
    echo "main.py introuvable dans l'AppImage" >&2
    exit 1
fi
export PYTHONPATH="$(dirname "$MAIN")/site-packages"
exec python3 "$MAIN" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# 4. Fichier .desktop et icône
cat > "$APPDIR/MPRIS-Visualizer.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=MPRIS Visualizer
Comment=Pochette, dégradé et visualiseur du média en cours
Exec=AppRun
Icon=MPRIS-Visualizer
Categories=AudioVideo;Player;
Terminal=false
EOF

cat > "$APPDIR/MPRIS-Visualizer.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#312e81"/>
      <stop offset="0.5" stop-color="#0e7490"/>
      <stop offset="1" stop-color="#be185d"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="48" fill="url(#g)"/>
  <rect x="48" y="150" width="20" height="60" rx="6" fill="#ffffff" opacity="0.6"/>
  <rect x="82" y="110" width="20" height="100" rx="6" fill="#ffffff" opacity="0.7"/>
  <rect x="116" y="82" width="20" height="128" rx="6" fill="#ffffff" opacity="0.8"/>
  <rect x="150" y="120" width="20" height="90" rx="6" fill="#ffffff" opacity="0.7"/>
  <rect x="184" y="160" width="20" height="50" rx="6" fill="#ffffff" opacity="0.6"/>
</svg>
EOF

# 5. Génération de l'AppImage
ARCH=x86_64 appimagetool "$APPDIR" "$OUT"
echo "AppImage créée : $OUT"
