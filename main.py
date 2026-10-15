#!/usr/bin/env python3
"""MPRIS Visualizer : pochette centrée, dégradé extrait de la pochette,
visualiseur audio en arrière-plan (barres de largeur fixe), jauge de
progression ondulante et boutons précédent / lecture / suivant."""

import math
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

SEP = "|||"
FMT = (
    f"{{{{status}}}} {SEP} {{{{title}}}} {SEP} {{{{artist}}}} {SEP} "
    f"{{{{mpris:artUrl}}}} {SEP} {{{{mpris:length}}}}"
)
PALETTE_SIZE = 5
COVER_RATIO = 0.9  # doit correspondre au facteur utilisé dans CoverWidget.paintEvent
BAR_WIDTH = 20  # largeur fixe d'une barre (px)
BAR_GAP = 3  # espace entre deux barres (px)
DEFAULT_PALETTE = [
    QColor("#312e81"),
    QColor("#be185d"),
    QColor("#0e7490"),
    QColor("#b45309"),
    QColor("#4d7c0f"),
]
# Positions (relatives) des halos colorés de l'arrière-plan
GLOW_POSITIONS = [(0.15, 0.2), (0.85, 0.3), (0.2, 0.8), (0.8, 0.85), (0.5, 0.5)]


# ---------------------------------------------------------------- MPRIS ----


def playerctl(*args):
    """Appelle playerctl et renvoie sa sortie (chaîne vide en cas d'erreur)."""
    try:
        r = subprocess.run(
            ["playerctl", *args], capture_output=True, text=True, timeout=2
        )
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def load_image_bytes(url):
    """Charge la pochette depuis file:// ou http(s)://."""
    if url.startswith("file://"):
        path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
        with open(path, "rb") as f:
            return f.read()
    if url.startswith(("http://", "https://")):
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()
    return None


def fmt_time(seconds):
    """Formate des secondes en m:ss (ou h:mm:ss)."""
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


class PlaybackState:
    """Position de lecture, mise à jour toutes les 0,5 s et interpolée à l'affichage."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pos = 0.0
        self._pos_time = time.monotonic()
        self._length = 0.0
        self._playing = False

    def update(self, pos, length, playing):
        with self._lock:
            self._pos = pos
            self._pos_time = time.monotonic()
            self._length = length
            self._playing = playing

    def snapshot(self):
        """Renvoie (position, durée, en_lecture) avec position interpolée."""
        with self._lock:
            pos = self._pos
            if self._playing:
                pos += time.monotonic() - self._pos_time
            if self._length > 0:
                pos = min(pos, self._length)
            return pos, self._length, self._playing


# ------------------------------------------------------------- palette ----


def _dist(a, b):
    return math.sqrt(
        (a.red() - b.red()) ** 2
        + (a.green() - b.green()) ** 2
        + (a.blue() - b.blue()) ** 2
    )


def _lerp_color(a, b, t):
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def extract_palette(image, count=PALETTE_SIZE):
    """Extrait les couleurs dominantes (et les plus saturées) de la pochette."""
    small = image.convertToFormat(QImage.Format.Format_RGB32).scaled(
        48,
        48,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    # Regroupement grossier des couleurs par seaux de 32 niveaux
    buckets = {}
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            key = (c.red() // 32, c.green() // 32, c.blue() // 32)
            n, r, g, b = buckets.get(key, (0, 0, 0, 0))
            buckets[key] = (n + 1, r + c.red(), g + c.green(), b + c.blue())

    scored = []
    for n, r, g, b in buckets.values():
        col = QColor(r // n, g // n, b // n)
        sat = col.hsvSaturation() / 255
        scored.append((n * (0.2 + sat), col))
    scored.sort(key=lambda t: t[0], reverse=True)

    chosen = []
    for _, col in scored:
        if all(_dist(col, c) > 60 for c in chosen):
            chosen.append(col)
        if len(chosen) == count:
            break
    i = 0
    while len(chosen) < count:
        chosen.append(DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)])
        i += 1
    return chosen


def white_icon(icon, size=32):
    """Recolore une icône en blanc (les icônes standard sont sombres)."""
    pm = icon.pixmap(size, size)
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, pm)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor(255, 255, 255))
    p.end()
    return QIcon(out)


# ------------------------------------------------------------ analyseur ----


class Analyzer(threading.Thread):
    """Capture la sortie audio par défaut (monitor) et calcule le spectre
    en bandes de fréquence. Un seul calcul FFT par trame, vectorisé."""

    RATE = 44100
    HOP = 1024  # nouveaux échantillons par trame (~43 trames/s)
    N = 2048  # taille de la FFT (recouvrement de 50 %)
    BANDS = 40  # nombre de bandes calculées

    def __init__(self):
        super().__init__(daemon=True)
        self.bands = np.zeros(self.BANDS)
        self._proc = None
        self._stop = threading.Event()
        freqs = np.fft.rfftfreq(self.N, 1.0 / self.RATE)
        edges = np.geomspace(40, 16000, self.BANDS + 1)
        idx = np.searchsorted(freqs, edges)
        self._limit = int(idx[-1])
        self._starts = np.minimum(idx[:-1], self._limit - 1)
        self._counts = np.maximum(1, idx[1:] - idx[:-1]).astype(np.float64)
        self._window = np.hanning(self.N)
        self._boost = 1 + 1.5 * np.arange(self.BANDS) / self.BANDS
        self._kernel = np.array([0.25, 0.5, 0.25])

    def run(self):
        try:
            self._proc = subprocess.Popen(
                [
                    "parec",
                    "--format=s16le",
                    f"--rate={self.RATE}",
                    "--channels=1",
                    "--latency-msec=20",
                    "-d",
                    "@DEFAULT_MONITOR@",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return  # parec absent : pas de visualisation

        buf = np.zeros(self.N)
        stream = self._proc.stdout
        nbytes = self.HOP * 2  # int16 mono

        while not self._stop.is_set():
            data = stream.read(nbytes)
            if len(data) < nbytes:
                break
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float64) / 32768.0
            buf = np.concatenate((buf[self.HOP :], samples))
            mag = np.abs(np.fft.rfft(buf * self._window))[: self._limit] / (self.N / 2)
            raw = np.add.reduceat(mag, self._starts) / self._counts
            target = np.clip(np.sqrt(raw) * 3.0 * self._boost, 0, 1)
            # Lissage léger entre bandes voisines
            self.bands = np.convolve(
                np.pad(target, 1, mode="edge"), self._kernel, mode="valid"
            )

    def stop(self):
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


# ------------------------------------------------------------------ UI ----


class Bridge(QObject):
    """Transmet les données des threads de fond vers le thread graphique."""

    meta_changed = Signal(object)
    cover_loaded = Signal(str, object)


class CoverWidget(QWidget):
    """Pochette carrée centrée, avec coins arrondis et ombre."""

    def __init__(self):
        super().__init__()
        self.pixmap = None
        self._scaled = None
        self._scaled_side = 0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_pixmap(self, pm):
        self.pixmap = pm
        self._scaled = None  # force le redimensionnement au prochain rendu
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        side = int(min(self.width(), self.height()) * COVER_RATIO)
        x = (self.width() - side) / 2
        y = (self.height() - side) / 2
        rect = QRectF(x, y, side, side)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawRoundedRect(rect.translated(0, 8).adjusted(6, 0, -6, 0), 18, 18)

        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)
        p.setClipPath(path)

        if self.pixmap and not self.pixmap.isNull():
            # Mise à l'échelle mise en cache : elle ne se refait qu'au changement de taille
            if self._scaled is None or self._scaled_side != side:
                self._scaled = self.pixmap.scaled(
                    side,
                    side,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._scaled_side = side
            sx = (self._scaled.width() - side) / 2
            sy = (self._scaled.height() - side) / 2
            p.drawPixmap(rect, self._scaled, QRectF(sx, sy, side, side))
        else:
            p.fillRect(rect, QColor(255, 255, 255, 30))
            p.setPen(QColor(255, 255, 255, 160))
            font = p.font()
            font.setPointSize(max(12, side // 4))
            p.setFont(font)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "♪")
        p.end()


class ProgressWidget(QWidget):
    """Jauge de progression : une ligne qui ondule quand la musique joue."""

    seek_requested = Signal(float)  # position cible en secondes

    WAVELENGTH = 90  # px
    WAVE_AMP = 3.0  # amplitude fixe de l'ondulation (px)
    WAVE_SPEED = 2 * math.pi * 0.8  # rad/s, constante et indépendante de la musique

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.amp = 0.0  # amplitude courante (animée vers 0 en pause)
        self.phase = 0.0  # phase courante de l'onde
        self._last = time.monotonic()
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        _, length, _ = self.state.snapshot()
        if length > 0:
            frac = min(1.0, max(0.0, e.position().x() / max(1, self.width())))
            self.seek_requested.emit(frac * length)

    def paintEvent(self, _):
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        pos, length, playing = self.state.snapshot()

        # L'onde n'ondule que pendant la lecture, à vitesse constante
        if playing:
            self.phase += dt * self.WAVE_SPEED
        target_amp = self.WAVE_AMP if playing else 0.0
        self.amp += (target_amp - self.amp) * min(1.0, dt * 4)

        freq = 2 * math.pi / self.WAVELENGTH
        frac = pos / length if length > 0 else 0.0
        w, h = self.width(), self.height()
        mid = h / 2
        steps = max(2, int(w / 4))

        path = QPainterPath()
        for i in range(steps + 1):
            x = i * w / steps
            y = mid + math.sin(x * freq + self.phase) * self.amp
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Ligne complète, discrète
        pen = QPen(QColor(255, 255, 255, 70), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawPath(path)

        # Partie déjà jouée, plus lumineuse
        p.save()
        p.setClipRect(QRectF(0, 0, frac * w, h))
        pen = QPen(QColor(255, 255, 255, 235), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawPath(path)
        p.restore()

        # Curseur à la position actuelle
        knob_x = frac * w
        knob_y = mid + math.sin(knob_x * freq + self.phase) * self.amp
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 240))
        p.drawEllipse(QPointF(knob_x, knob_y), 5, 5)
        p.end()


class VisualizerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MPRIS Visualizer")
        self.resize(380, 600)
        self.setMinimumSize(260, 380)

        self.palette_colors = list(DEFAULT_PALETTE)
        self.current_art = None
        self._bg = None  # arrière-plan mis en cache (dégradé + halos)
        self._disp = None  # hauteurs de barres lissées à l'affichage
        self._disp_t = time.monotonic()
        self._times = ("", "")
        self._apply_palette()

        self.bridge = Bridge()
        self.bridge.meta_changed.connect(self.on_meta)
        self.bridge.cover_loaded.connect(self.on_cover)

        self.state = PlaybackState()
        self.analyzer = Analyzer()

        self.cover = CoverWidget()
        self.title = QLabel("Aucun média en lecture")
        self.artist = QLabel("")
        for lbl, css in (
            (self.title, "color: white; font-size: 15pt; font-weight: bold;"),
            (self.artist, "color: rgba(255,255,255,190); font-size: 11pt;"),
        ):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(css)

        # Jauge, dont la largeur suit celle de la pochette (voir _fit_progress)
        self.progress = ProgressWidget(self.state)
        self.progress.seek_requested.connect(
            lambda s: self._control("position", f"{s:.2f}")
        )
        time_css = "color: rgba(255,255,255,200); font-size: 9pt;"
        self.time_left = QLabel("0:00")
        self.time_right = QLabel("0:00")
        self.time_left.setStyleSheet(time_css)
        self.time_right.setStyleSheet(time_css)
        self.times_box = QWidget()
        times = QHBoxLayout(self.times_box)
        times.setContentsMargins(0, 0, 0, 0)
        times.addWidget(self.time_left)
        times.addStretch(1)
        times.addWidget(self.time_right)

        style = self.style()
        self.prev_btn = self._make_button(
            white_icon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        )
        self.play_btn = self._make_button(
            white_icon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        )
        self.next_btn = self._make_button(
            white_icon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        )
        self._icon_play = white_icon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self._icon_pause = white_icon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        )
        self.prev_btn.clicked.connect(lambda: self._control("previous"))
        self.play_btn.clicked.connect(lambda: self._control("play-pause"))
        self.next_btn.clicked.connect(lambda: self._control("next"))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.prev_btn)
        buttons.addWidget(self.play_btn)
        buttons.addWidget(self.next_btn)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 20, 12, 20)
        layout.addWidget(self.cover, 1)
        layout.addWidget(self.title)
        layout.addWidget(self.artist)
        layout.addSpacing(12)
        layout.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.times_box, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        layout.addLayout(buttons)

        self.analyzer.start()
        threading.Thread(target=self._poll_loop, daemon=True).start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)  # ~60 images/s

    # --- boutons -----------------------------------------------------------

    def _make_button(self, icon):
        b = QPushButton()
        b.setIcon(icon)
        b.setIconSize(QSize(32, 32))
        b.setFixedSize(64, 64)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,40); border: none; border-radius: 32px; }"
            "QPushButton:hover { background: rgba(255,255,255,80); }"
            "QPushButton:pressed { background: rgba(255,255,255,120); }"
        )
        return b

    def _control(self, *args):
        threading.Thread(target=playerctl, args=args, daemon=True).start()

    # --- MPRIS -------------------------------------------------------------

    def _poll_loop(self):
        last = None
        while True:
            out = playerctl("metadata", "--format", FMT)
            parts = [p.strip() for p in out.split(SEP)] if out else []
            parts += [""] * (5 - len(parts))
            length_us = parts[4]
            meta = {
                "status": parts[0],
                "title": parts[1],
                "artist": parts[2],
                "art": parts[3],
                "length": int(length_us) / 1e6 if length_us.isdigit() else 0.0,
            }

            # Position réelle, pour recaler l'interpolation de la jauge
            pos_out = playerctl("position")
            try:
                pos = float(pos_out)
            except ValueError:
                pos = self.state.snapshot()[0]
            self.state.update(pos, meta["length"], meta["status"] == "Playing")

            if meta != last:
                last = meta
                self.bridge.meta_changed.emit(meta)
            time.sleep(0.5)

    def on_meta(self, meta):
        self.title.setText(meta["title"] or "Aucun média en lecture")
        self.artist.setText(meta["artist"])
        playing = meta["status"] == "Playing"
        self.play_btn.setIcon(self._icon_pause if playing else self._icon_play)

        if meta["art"] != self.current_art:
            self.current_art = meta["art"]
            if meta["art"]:
                threading.Thread(
                    target=self._load_cover, args=(meta["art"],), daemon=True
                ).start()
            else:
                self._set_cover(None)

    def _load_cover(self, url):
        image = None
        try:
            data = load_image_bytes(url)
            if data:
                image = QImage.fromData(data)
        except Exception:
            image = None
        self.bridge.cover_loaded.emit(url, image)

    def on_cover(self, url, image):
        if url != self.current_art:
            return  # une pochette plus récente est arrivée entre-temps
        if image is None or image.isNull():
            self._set_cover(None)
        else:
            self._set_cover(image)

    def _set_cover(self, image):
        if image is None:
            self.cover.set_pixmap(None)
            self.palette_colors = list(DEFAULT_PALETTE)
        else:
            self.cover.set_pixmap(QPixmap.fromImage(image))
            self.palette_colors = extract_palette(image)
        self._apply_palette()

    # --- couleurs ----------------------------------------------------------

    def _apply_palette(self):
        c = self.palette_colors
        n = len(c)
        # Dégradé diagonal qui passe par toutes les couleurs de la palette
        self.bg_stops = [(i / (n - 1), c[i].darker(160)) for i in range(n)]
        # Halos colorés superposés pour un fond plus vivant
        self.glows = [
            (GLOW_POSITIONS[i % len(GLOW_POSITIONS)], c[i].lighter(110))
            for i in range(n)
        ]
        # Couleurs des barres : interpolation le long de la palette, éclaircies
        self.accents = [col.lighter(130) for col in c]
        self._bg = None  # l'arrière-plan doit être redessiné
        self.update()

    def _bar_color(self, i, total):
        """Couleur de la barre i, interpolée sur toute la palette."""
        n = len(self.accents)
        pos = i / max(1, total - 1) * (n - 1)
        k = min(int(pos), n - 2)
        return _lerp_color(self.accents[k], self.accents[k + 1], pos - k)

    # --- rafraîchissement --------------------------------------------------

    def _fit_progress(self):
        """Aligne la largeur de la jauge sur celle de la pochette affichée."""
        side = max(40, int(min(self.cover.width(), self.cover.height()) * COVER_RATIO))
        if self.progress.width() != side:
            self.progress.setFixedWidth(side)
            self.times_box.setFixedWidth(side)

    def _tick(self):
        self._fit_progress()
        pos, length, _ = self.state.snapshot()
        texts = (fmt_time(pos), fmt_time(length))
        if texts != self._times:  # ne met à jour les labels que si le texte change
            self._times = texts
            self.time_left.setText(texts[0])
            self.time_right.setText(texts[1])
        self.progress.update()
        self.update()

    # --- rendu -------------------------------------------------------------

    def _build_background(self, w, h):
        """Dessine le dégradé et les halos une seule fois (mis en cache)."""
        pm = QPixmap(w, h)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, w, h)
        for t, col in self.bg_stops:
            grad.setColorAt(t, col)
        p.fillRect(pm.rect(), grad)

        diag = math.hypot(w, h)
        p.setPen(Qt.PenStyle.NoPen)
        for (rx, ry), col in self.glows:
            rg = QRadialGradient(QPointF(rx * w, ry * h), diag * 0.45)
            halo = QColor(col)
            halo.setAlpha(150)
            rg.setColorAt(0.0, halo)
            halo.setAlpha(0)
            rg.setColorAt(1.0, halo)
            p.setBrush(rg)
            p.drawRect(pm.rect())
        p.end()
        return pm

    def _bar_values(self, n):
        """Hauteurs des barres : rééchantillonnage du spectre puis lissage temporel."""
        src = self.analyzer.bands
        target = np.interp(np.linspace(0, len(src) - 1, n), np.arange(len(src)), src)
        if self._disp is None or len(self._disp) != n:
            self._disp = target.copy()
        else:
            now = time.monotonic()
            dt = min(0.1, now - self._disp_t)
            self._disp_t = now
            k_rise = 1 - math.exp(-dt * 28)  # montée rapide
            k_fall = 1 - math.exp(-dt * 9)  # retombée douce
            k = np.where(target > self._disp, k_rise, k_fall)
            self._disp = self._disp + (target - self._disp) * k
        self._disp_t = time.monotonic()
        return self._disp

    def paintEvent(self, _):
        w, h = self.width(), self.height()
        p = QPainter(self)

        # 1. Arrière-plan (mis en cache)
        if self._bg is None or self._bg.size() != self.size():
            self._bg = self._build_background(w, h)
        p.drawPixmap(0, 0, self._bg)

        # 2. Barres : largeur fixe, leur nombre s'adapte à la largeur de la fenêtre
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar_w = float(BAR_WIDTH)
        n = max(4, int((w + BAR_GAP) // (bar_w + BAR_GAP)))
        used = n * bar_w + (n - 1) * BAR_GAP
        x0 = (w - used) / 2
        values = self._bar_values(n)

        max_h = h * 0.6
        radius = bar_w / 2
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            bh = max(bar_w, float(values[i]) * max_h)  # hauteur minimale = largeur
            x = x0 + i * (bar_w + BAR_GAP)
            top = h - bh
            col = self._bar_color(i, n)

            bar_grad = QLinearGradient(x, top, x, h)
            hi = QColor(col.lighter(120))
            hi.setAlpha(235)
            mid = QColor(col)
            mid.setAlpha(190)
            low = QColor(col.darker(120))
            low.setAlpha(110)
            bar_grad.setColorAt(0.0, hi)
            bar_grad.setColorAt(0.5, mid)
            bar_grad.setColorAt(1.0, low)
            p.setBrush(bar_grad)
            p.drawRoundedRect(QRectF(x, top, bar_w, bh), radius, radius)
        p.end()

    def closeEvent(self, event):
        self.analyzer.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MPRIS Visualizer")
    win = VisualizerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
