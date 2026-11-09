# -*- coding: utf-8 -*-
"""
Lamina da Aurora - versao 3 (terceira pessoa, arte realista gerada por IA)

O cavaleiro caminha pela estrada antiga; a camera vai atras e acima dele.
Monstros (esqueletos, morcegos, gosmas) vem de frente; no fim de cada fase
aparece o Rei Ossudo.

Controles
  A / D  ou  <- / ->     andar para os lados
  Mouse                  mirar (a mira gruda no alvo mais proximo)
  Clique / Espaco / J    atacar (onda magica da espada)
  P pausa   F tela cheia   F3 fps   F12 captura   Esc sai

Musica: coloque arquivos .mp3/.ogg/.wav na pasta  musica/  e eles tocam no
lugar da musica sintetizada (um por fase, em ordem alfabetica).
"""
import math
import os
import random
import sys

import numpy as np
import pygame

AQUI = os.path.dirname(os.path.abspath(__file__))
ARTE = os.path.join(AQUI, "arte")
MUSICA = os.path.join(AQUI, "musica")

TITLE = "Lâmina da Aurora"
W, H = 1280, 720
HORIZON = 200
FOCAL = 620.0
CAM_H = 3.4            # altura da camera (m)
PLAYER_DZ = 6.5        # distancia do cavaleiro a frente da camera
SEG = 2.0
FAR = 200.0
DRAW_SEGS = int(FAR / SEG)
ROAD_W = 3.2           # meia largura da estrada
WALK_LIM = ROAD_W + 0.9
FWD_SPEED = 4.2        # passo do cavaleiro (m/s)
STRAFE_SPEED = 4.5
SHOT_SPEED = 26.0
SPAWN_DIST = 85.0
STAGE_LEN = float(os.environ.get("LAMINA_FASE", "420"))
MAX_HP = 6
GAME_SPEED = float(os.environ.get("LAMINA_VELOCIDADE", "0.7"))   # 1.0 = ritmo original; menor = mais lento
SRCALPHA = pygame.SRCALPHA

STAGES = [
    dict(name="Estrada das Colunas", fog=(178, 182, 184), grade=None, curve=(4.0, 1.5),
         enemies={"esqueleto": 3, "morcego": 3, "gosma": 3}, boss_hp=60, root=110.0, bpm=96,
         ambient=(235, 235, 220)),
    dict(name="Crepúsculo dos Ciprestes", fog=(206, 186, 168), grade=(255, 212, 172), curve=(6.0, 2.5),
         enemies={"esqueleto": 4, "morcego": 3, "gosma": 2}, boss_hp=80, root=98.0, bpm=88,
         ambient=(255, 190, 110)),
    dict(name="Noite do Rei Ossudo", fog=(118, 124, 138), grade=(132, 150, 205), curve=(7.0, 3.0),
         enemies={"esqueleto": 4, "morcego": 4, "gosma": 2}, boss_hp=100, root=82.4, bpm=104,
         ambient=(190, 255, 140)),
]

ITEMS = {
    "coracao": ((255, 80, 110), "Coração", 2.0),
    "triplo": ((255, 200, 60), "Tiro Triplo", 2.0),
    "rajada": ((255, 240, 120), "Rajada", 2.0),
    "gelo": ((120, 200, 255), "Gelo", 1.4),
    "bomba": ((255, 120, 40), "Bomba", 1.2),
    "escudo": ((140, 255, 180), "Escudo", 1.3),
    "tesouro": ((255, 215, 0), "Tesouro", 2.0),
}


# ----------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------
def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp_col(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t), int(c1[1] + (c2[1] - c1[1]) * t), int(c1[2] + (c2[2] - c1[2]) * t))


def seg_dist2(ax, ay, az, bx, by, bz, px, py, pz):
    dx, dy, dz = bx - ax, by - ay, bz - az
    L = dx * dx + dy * dy + dz * dz
    t = 0.0 if L == 0 else clamp(((px - ax) * dx + (py - ay) * dy + (pz - az) * dz) / L, 0.0, 1.0)
    return (px - ax - dx * t) ** 2 + (py - ay - dy * t) ** 2 + (pz - az - dz * t) ** 2


def wchoice(weights):
    r = random.uniform(0, sum(weights.values()))
    for k, w in weights.items():
        r -= w
        if r <= 0:
            return k
    return k


class Ent:
    def __init__(self, **kw):
        self.dead = False
        self.__dict__.update(kw)


def make_glow(color, radius=64, power=2.2):
    size = radius * 2
    y, x = np.mgrid[0:size, 0:size]
    d = np.sqrt((x - radius + 0.5) ** 2 + (y - radius + 0.5) ** 2) / radius
    f = np.clip(1 - d, 0, 1) ** power
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    for i in range(3):
        arr[..., i] = (f * color[i]).astype(np.uint8)
    return pygame.surfarray.make_surface(arr.swapaxes(0, 1)).convert()


def make_vignette():
    y, x = np.mgrid[0:H, 0:W]
    d = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    a = (np.clip((d - 0.75) / 0.7, 0, 1) ** 1.6 * 150).astype(np.uint8)
    s = pygame.Surface((W, H), SRCALPHA)
    s.fill((0, 0, 0, 255))
    pa = pygame.surfarray.pixels_alpha(s)
    pa[:] = a.T
    del pa
    return s


def make_edge_glow(color):
    w2, h2 = W // 4, H // 4
    y, x = np.mgrid[0:h2, 0:w2]
    d = np.sqrt(((x - w2 / 2) / (w2 / 2)) ** 2 + ((y - h2 / 2) / (h2 / 2)) ** 2)
    f = np.clip((d - 0.7) / 0.6, 0, 1) ** 1.3
    arr = np.zeros((h2, w2, 3), dtype=np.uint8)
    for i in range(3):
        arr[..., i] = (f * color[i]).astype(np.uint8)
    s = pygame.surfarray.make_surface(arr.swapaxes(0, 1))
    return pygame.transform.smoothscale(s, (W, H)).convert()


def heart_points(cx, cy, size, n=40):
    pts = []
    for i in range(n):
        t = i / n * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * size / 34, cy - y * size / 34))
    return pts


def art_orb(color, icon):
    s = pygame.Surface((160, 160), SRCALPHA)
    c = (80, 80)
    for r, a in ((78, 40), (70, 90), (62, 170), (56, 230)):
        pygame.draw.circle(s, lerp_col(color, (0, 0, 0), 0.35 if r < 60 else 0) + (a,), c, r)
    pygame.draw.circle(s, lerp_col(color, (255, 255, 255), 0.5) + (255,), c, 56, 4)
    wc = (255, 255, 255)
    if icon == "coracao":
        pygame.draw.polygon(s, wc, heart_points(80, 84, 64))
    elif icon == "bomba":
        pygame.draw.circle(s, (30, 30, 36), (76, 90), 26)
        pygame.draw.line(s, (220, 200, 160), (92, 68), (106, 50), 5)
        pygame.draw.circle(s, (255, 240, 120), (108, 47), 8)
    elif icon == "gelo":
        for k in range(3):
            a = k * math.pi / 3
            dx, dy = math.cos(a) * 34, math.sin(a) * 34
            pygame.draw.line(s, wc, (80 - dx, 80 - dy), (80 + dx, 80 + dy), 5)
    elif icon == "triplo":
        for a in (-0.5, 0, 0.5):
            ex, ey = 80 + math.sin(a) * 36, 80 - math.cos(a) * 36
            pygame.draw.line(s, wc, (80, 112), (ex, ey), 5)
            pygame.draw.circle(s, wc, (int(ex), int(ey)), 8)
    elif icon == "rajada":
        pygame.draw.polygon(s, wc, [(90, 34), (56, 88), (78, 88), (66, 128), (106, 70), (82, 70)])
    elif icon == "escudo":
        pygame.draw.polygon(s, wc, [(80, 38), (114, 50), (110, 92), (80, 122), (50, 92), (46, 50)])
    elif icon == "tesouro":
        pygame.draw.polygon(s, wc, [(56, 66), (80, 40), (104, 66), (80, 118)])
    return s


def art_shadow():
    s = pygame.Surface((200, 80), SRCALPHA)
    for i in range(12):
        pygame.draw.ellipse(s, (20, 18, 14, 12 + i * 11), (i * 7, i * 2.8, 200 - i * 14, 80 - i * 5.6))
    return s


def tile_noise(size, cells, rnd):
    g = np.random.default_rng(rnd.randrange(1 << 30)).random((cells, cells))
    t = np.arange(size) * cells / size
    i0 = t.astype(int) % cells
    i1 = (i0 + 1) % cells
    f = t - np.floor(t)
    f = f * f * (3 - 2 * f)
    a = g[i0][:, i0] * (1 - f)[None, :] + g[i0][:, i1] * f[None, :]
    b = g[i1][:, i0] * (1 - f)[None, :] + g[i1][:, i1] * f[None, :]
    return a * (1 - f)[:, None] + b * f[:, None]


def fbm(size, rnd, octaves=((4, 0.5), (8, 0.25), (16, 0.15), (32, 0.1))):
    out = np.zeros((size, size))
    for cells, w in octaves:
        out += tile_noise(size, cells, rnd) * w
    return out / sum(w for _, w in octaves)


def mips(tex, levels=6):
    out = [tex.astype(np.float32)]
    for _ in range(levels - 1):
        t = out[-1]
        out.append((t[0::2, 0::2] + t[1::2, 0::2] + t[0::2, 1::2] + t[1::2, 1::2]) / 4)
    return out


def surf_to_array(s):
    return pygame.surfarray.array3d(s).swapaxes(0, 1).astype(np.float32)


# ----------------------------------------------------------------------------
# Audio: efeitos sintetizados + musica opcional da pasta musica/
# ----------------------------------------------------------------------------
class Audio:
    def __init__(self):
        self.ok = False
        self.snd = {}
        self.synth_music = {}
        self.music_ch = None
        self.files = []
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 512)
            self.sr, _, self.ch = pygame.mixer.get_init()
            pygame.mixer.set_num_channels(32)
            self.ok = True
            self.build()
        except Exception as e:
            print("audio desativado:", e)
            self.ok = False
        if os.path.isdir(MUSICA):
            self.files = sorted(os.path.join(MUSICA, f) for f in os.listdir(MUSICA)
                                if f.lower().endswith((".mp3", ".ogg", ".wav")))

    def to_sound(self, mono, vol=0.9):
        peak = float(np.max(np.abs(mono))) or 1.0
        a = (np.clip(mono / peak, -1, 1) * 32767 * vol).astype(np.int16)
        if self.ch == 2:
            a = np.column_stack([a, a])
        return pygame.sndarray.make_sound(np.ascontiguousarray(a))

    def build(self):
        sr = self.sr
        rng = np.random.default_rng(7)

        def tt(d):
            return np.arange(int(sr * d)) / sr

        def sweep(f0, f1, d, wave="sine"):
            t = tt(d)
            f = np.geomspace(f0, f1, len(t))
            ph = 2 * np.pi * np.cumsum(f) / sr
            if wave == "square":
                return np.sign(np.sin(ph)) * 0.6
            if wave == "saw":
                return 2 * ((ph / (2 * np.pi)) % 1) - 1
            return np.sin(ph)

        def env(n, attack=0.004, decay=6.0):
            t = np.arange(n) / sr
            e = np.exp(-t * decay)
            a = max(1, int(sr * attack))
            e[:a] *= np.linspace(0, 1, a)
            return e

        def noise(d):
            return rng.uniform(-1, 1, int(sr * d))

        def lowpass(x, k):
            return np.convolve(x, np.ones(k) / k, mode="same")

        def bandsweep(d, k0, k1):
            """ruido filtrado com corte variavel (som de 'vush' da espada)"""
            x = noise(d)
            out = np.zeros_like(x)
            ks = np.linspace(k0, k1, 12).astype(int)
            seg = len(x) // len(ks)
            for i, k in enumerate(ks):
                a, b = i * seg, (i + 1) * seg if i < len(ks) - 1 else len(x)
                hp = x - lowpass(x, max(2, k * 3))
                out[a:b] = lowpass(hp, max(1, k))[a:b]
            return out

        def partials(freqs, d, decay):
            t = tt(d)
            return sum(np.sin(2 * np.pi * f * t) * np.exp(-t * decay * (1 + i * 0.6)) for i, f in enumerate(freqs))

        # golpe da espada: vush (ruido com envelope em sino)
        x = bandsweep(0.26, 6, 2)
        bell = np.sin(np.linspace(0, np.pi, len(x))) ** 2
        self.snd["espada"] = self.to_sound(x * bell, 0.75)
        # onda magica: zing com vibrato e brilho
        t = tt(0.38)
        f = np.geomspace(1900, 700, len(t)) * (1 + 0.03 * np.sin(2 * np.pi * 28 * t))
        ph = 2 * np.pi * np.cumsum(f) / sr
        x = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3.01 * ph)
        self.snd["magia"] = self.to_sound(x * env(len(x), 0.01, 7), 0.45)
        # acerto em osso: estalo seco inarmonico
        x = partials((1180, 1730, 2470, 3320), 0.18, 28) + noise(0.18) * env(int(sr * 0.18), 0.001, 80) * 1.5
        self.snd["osso"] = self.to_sound(x, 0.8)
        # metal (escudo / armadura)
        x = partials((520, 1310, 2210, 3170, 4300), 0.7, 6) + noise(0.7) * env(int(sr * 0.7), 0.001, 60)
        self.snd["metal"] = self.to_sound(x, 0.7)
        # gosma: chape molhado
        n = int(sr * 0.28)
        x = lowpass(noise(0.28), 10) * env(n, 0.003, 14) + sweep(320, 70, 0.28) * env(n, 0.002, 9)
        self.snd["gosma"] = self.to_sound(x, 0.8)
        # morcego: guincho
        t = tt(0.22)
        x = sweep(3200, 2100, 0.22) * (0.6 + 0.4 * np.sin(2 * np.pi * 60 * t))
        self.snd["morcego"] = self.to_sound(x * env(len(x), 0.005, 10), 0.4)
        # explosao / morte
        x = lowpass(noise(0.7), 16) + sweep(120, 36, 0.7) * 0.6
        self.snd["explosao"] = self.to_sound(x * env(len(x), 0.002, 5), 0.75)
        x = lowpass(noise(1.4), 26) * 2 + sweep(90, 30, 1.4) * 0.8
        self.snd["bomba"] = self.to_sound(x * env(len(x), 0.002, 2.6), 0.95)
        # item / cristal
        parts = []
        for fq in (784, 988, 1319, 1568):
            y = np.sin(2 * np.pi * fq * tt(0.09)) + 0.3 * np.sin(2 * np.pi * fq * 2 * tt(0.09))
            parts.append(y * env(len(y), 0.002, 12))
        self.snd["item"] = self.to_sound(np.concatenate(parts), 0.6)
        # dano no cavaleiro: pancada metalica + grave
        n = int(sr * 0.45)
        x = partials((300, 790, 1460), 0.45, 9) + sweep(160, 60, 0.45, "saw") * env(n, 0.002, 8)
        self.snd["dano"] = self.to_sound(x, 0.8)
        x = sweep(800, 1500, 0.22)
        self.snd["escudo"] = self.to_sound(x * env(len(x), 0.004, 9), 0.5)
        x = lowpass(sweep(70, 40, 1.8, "saw"), 8) + lowpass(noise(1.8), 30) * 0.5
        self.snd["chefe"] = self.to_sound(x * env(len(x), 0.25, 1.4), 0.95)
        x = sweep(600, 250, 0.2, "square")
        self.snd["inimigo_tiro"] = self.to_sound(x * env(len(x), 0.002, 14), 0.35)
        # passo na terra
        x = lowpass(noise(0.09), 24) * env(int(sr * 0.09), 0.002, 45)
        self.snd["passo"] = self.to_sound(x, 0.25)

    def play(self, name, vol=1.0):
        if not self.ok:
            return
        s = self.snd.get(name)
        if s:
            ch = s.play()
            if ch:
                ch.set_volume(vol)

    def make_music(self, root, bpm):
        sr = self.sr
        beat = 60.0 / bpm
        bar = 4 * beat
        bars = 8
        n = int(sr * bar * bars)
        out = np.zeros(n)
        prog = [(0, (0, 3, 7)), (8, (0, 4, 7)), (3, (0, 4, 7)), (10, (0, 4, 7))]
        for b in range(bars):
            r, tri = prog[b % 4]
            start = int(b * bar * sr)
            L = min(int(bar * sr), n - start)
            t = np.arange(L) / sr
            e = np.minimum(1, t / 0.5) * np.minimum(1, (bar - t) / 0.5)
            pad = sum(np.sin(2 * np.pi * root * 2 * 2 ** ((r + iv) / 12) * t) for iv in tri)
            out[start:start + L] += pad * e * 0.05
            fb = root * 2 ** (r / 12) / (2 if r > 6 else 1)
            for k in range(4):
                s0 = start + int(k * beat * sr)
                Ln = min(int(beat * sr), n - s0)
                t2 = np.arange(Ln) / sr
                out[s0:s0 + Ln] += np.sin(2 * np.pi * fb * t2) * np.exp(-t2 * 4) * 0.16
            for k in range(8):
                iv = tri[k % 3] + (12 if (k // 3) % 2 else 0)
                f = root * 4 * 2 ** ((r + iv) / 12)
                s0 = start + int(k * beat / 2 * sr)
                Ln = min(int(beat / 2 * sr), n - s0)
                t2 = np.arange(Ln) / sr
                out[s0:s0 + Ln] += (2 * np.abs(2 * ((f * t2) % 1) - 1) - 1) * np.exp(-t2 * 6) * 0.045
        return self.to_sound(out, 0.8)

    def music(self, stage):
        if not self.ok:
            return
        if self.music_ch:
            self.music_ch.stop()
            self.music_ch = None
        if self.files:
            try:
                pygame.mixer.music.load(self.files[stage % len(self.files)])
                pygame.mixer.music.set_volume(0.6)
                pygame.mixer.music.play(-1)
                return
            except Exception as e:
                print("nao consegui tocar", self.files[stage % len(self.files)], e)
        if stage not in self.synth_music:
            st = STAGES[stage]
            self.synth_music[stage] = self.make_music(st["root"], st["bpm"])
        self.music_ch = self.synth_music[stage].play(loops=-1)
        if self.music_ch:
            self.music_ch.set_volume(0.45)


# ----------------------------------------------------------------------------
# Jogo
# ----------------------------------------------------------------------------
class Game:
    def __init__(self, test=False):
        self.test = test
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        self.screen = pygame.display.set_mode((W, H), 0 if test else pygame.SCALED)
        pygame.display.set_caption(TITLE)
        self.view = pygame.Surface((W, H)).convert()
        self.clock = pygame.time.Clock()
        fn = "georgia,timesnewroman,serif"
        self.f_huge = pygame.font.SysFont(fn, 86, bold=True)
        self.f_big = pygame.font.SysFont(fn, 56, bold=True)
        self.f_med = pygame.font.SysFont(fn, 32, bold=True)
        self.f_small = pygame.font.SysFont(fn, 22, bold=True)
        self.f_tiny = pygame.font.SysFont(fn, 17)
        self.audio = Audio()
        self.cache, self.base_mips, self.glow_cache, self.glow_base = {}, {}, {}, {}
        self.load_art()
        self.hiscore = 0
        self.show_fps = False
        self.aim_pos = (W // 2, HORIZON + 160)
        self.firing = False
        self.mouse_held = False
        self.reset_game()
        self.start_stage(0, silent=True)
        self.state = "titulo"
        self.audio.music(0)

    # ------------------------------------------------------------------ arte
    def load_art(self):
        def img(name):
            return pygame.image.load(os.path.join(ARTE, name + ".png")).convert_alpha()

        b = {}
        for name in ("cavaleiro", "esqueleto", "morcego", "gosma", "chefe", "cristal",
                     "coluna_quebrada", "carvalho", "cipreste"):
            b[name] = img(name)
        b["coluna"] = b.pop("coluna_quebrada")
        # ciclos de caminhada (8 quadros) gerados por ferramentas/anima_pernas.py
        self.cav_frames = []
        for k in range(8):
            for pref, lst in (("cav_andar", "cav"), ("esq_andar", "esq")):
                path = os.path.join(ARTE, "%s_%d.png" % (pref, k))
                if os.path.exists(path):
                    b["%s%d" % (lst, k)] = img("%s_%d" % (pref, k))
        self.has_cav = "cav0" in b
        self.has_esq = "esq0" in b
        for key, ang in (("cavaleiro", 2.5), ("esqueleto", 5), ("chefe", 2.5)):
            b[key + "_l"] = pygame.transform.rotozoom(b[key], ang, 1.0)
            b[key + "_r"] = pygame.transform.rotozoom(b[key], -ang, 1.0)
        m = b["morcego"]
        b["morcego1"] = pygame.transform.smoothscale(m, (int(m.get_width() * 0.92), int(m.get_height() * 0.62)))
        g = b["gosma"]
        b["gosma_sq"] = pygame.transform.smoothscale(g, (int(g.get_width() * 1.22), int(g.get_height() * 0.74)))
        b["gosma_st"] = pygame.transform.smoothscale(g, (int(g.get_width() * 0.84), int(g.get_height() * 1.2)))
        for key in [k for k in b if k.split("_")[0] in ("esqueleto", "morcego", "morcego1", "gosma", "chefe")
                    or (k.startswith("esq") and k[3:].isdigit())]:
            hit = b[key].copy()
            hit.fill((110, 110, 110), special_flags=pygame.BLEND_RGB_ADD)
            b[key + "_hit"] = hit
        b["sombra"] = art_shadow().convert_alpha()
        for k, (c, _, _) in ITEMS.items():
            b["item_" + k] = art_orb(c, k).convert_alpha()
        self.base = b
        self.vignette = make_vignette().convert_alpha()
        self.edge_shield = make_edge_glow((40, 150, 90))
        self.edge_ice = make_edge_glow((40, 90, 160))
        self.heart_full = pygame.Surface((38, 36), SRCALPHA)
        pygame.draw.polygon(self.heart_full, (120, 10, 30), heart_points(19, 19, 36))
        pygame.draw.polygon(self.heart_full, (235, 45, 75), heart_points(19, 18, 31))
        pygame.draw.circle(self.heart_full, (255, 170, 180), (12, 12), 4)
        self.heart_empty = pygame.Surface((38, 36), SRCALPHA)
        pygame.draw.polygon(self.heart_empty, (90, 30, 45), heart_points(19, 18, 33), 3)
        # ceu: faixa larga que emenda espelhada
        sky = pygame.image.load(os.path.join(ARTE, "ceu.png")).convert()
        sw = 1920
        sh = int(sky.get_height() * sw / sky.get_width())
        sky = pygame.transform.smoothscale(sky, (sw, sh))
        hh = HORIZON + 60
        top = max(0, sh - hh - 140)
        strip = sky.subsurface((0, top, sw, hh)).copy()
        self.sky = pygame.Surface((sw * 2, hh)).convert()
        self.sky.blit(strip, (0, 0))
        self.sky.blit(pygame.transform.flip(strip, True, False), (sw, 0))
        # texturas do chao
        road = surf_to_array(pygame.image.load(os.path.join(ARTE, "estrada.png")).convert())
        grass = surf_to_array(pygame.image.load(os.path.join(ARTE, "grama.png")).convert())
        self.tex_road, self.tex_grass = mips(road), mips(grass)
        self.edge_noise = fbm(256, random.Random(5), ((8, 0.6), (32, 0.4))).astype(np.float32).ravel()
        self.floor_small = pygame.Surface((W // 2, (H - HORIZON) // 2)).convert()
        self.floor_big = pygame.Surface((W, H - HORIZON)).convert()
        self.setup_floor()

    def setup_floor(self):
        rh, rw = (H - HORIZON) // 2, W // 2
        fy = np.arange(rh) * 2 + 1.0
        xs = ((np.arange(rw) * 2 + 1) - W / 2) / FOCAL
        dz = CAM_H * FOCAL / fy
        r0 = int(np.searchsorted(-dz, -FAR * 1.05))
        self.fl_r0 = r0
        self.fl_dz = dz[r0:].astype(np.float32)
        self.fl_xd = (xs[None, :] * self.fl_dz[:, None]).astype(np.float32)
        shifts = self.floor_small.get_shifts()

        def pack(t):
            t = np.clip(t, 0, 255).astype(np.uint32)
            return ((t[..., 0] << shifts[0]) | (t[..., 1] << shifts[1]) | (t[..., 2] << shifts[2])).ravel()

        def bands(T0, tile, n):
            tpp = (T0 / tile) * self.fl_dz * 2 / FOCAL
            lvl = np.clip(np.floor(np.log2(np.maximum(tpp, 1.0))), 0, n - 1).astype(int)
            out = []
            for k in range(n):
                rows = np.nonzero(lvl == k)[0]
                if len(rows):
                    out.append((rows[0], rows[-1] + 1, k))
            return out

        self.road_p = [(pack(t), t.shape[0]) for t in self.tex_road]
        self.grass_p = [(pack(t), t.shape[0]) for t in self.tex_grass]
        self.road_tile, self.grass_tile = 3.0, 5.0
        self.b_road = bands(self.tex_road[0].shape[0], self.road_tile, len(self.tex_road))
        self.b_grass = bands(self.tex_grass[0].shape[0], self.grass_tile, len(self.tex_grass))
        self.fog_over, self.fog_p, self.haze = [], [], []
        yb = np.arange(H - HORIZON) + 0.5
        alpha = (np.clip((CAM_H * FOCAL / yb) / FAR, 0, 1) ** 1.15 * 255).astype(np.uint8)
        for st in STAGES:
            o = pygame.Surface((W, H - HORIZON), SRCALPHA)
            o.fill(st["fog"] + (255,))
            pa = pygame.surfarray.pixels_alpha(o)
            pa[:] = alpha[None, :]
            del pa
            self.fog_over.append(o.convert_alpha())
            self.fog_p.append(int(pack(np.array(st["fog"], np.float32)[None, None, :])[0]))
            hz = pygame.Surface((W, 110), SRCALPHA)
            hz.fill(st["fog"] + (255,))
            pa = pygame.surfarray.pixels_alpha(hz)
            pa[:] = (np.linspace(0, 1, 110) ** 1.6 * 255).astype(np.uint8)[None, :]
            del pa
            self.haze.append(hz.convert_alpha())

    def scaled(self, key, h, flip=False):
        if h > 48:
            h = int(round(1.035 ** round(math.log(h) / 0.0344014)))
        ck = (key, h, flip)
        img = self.cache.get(ck)
        if img is None:
            chain = self.base_mips.get(key)
            if chain is None:
                chain = [self.base[key]]
                while chain[-1].get_height() > 32:
                    c = chain[-1]
                    chain.append(pygame.transform.smoothscale(c, (max(1, c.get_width() // 2), c.get_height() // 2)))
                self.base_mips[key] = chain
            src = chain[0]
            for c in chain:
                if c.get_height() >= h:
                    src = c
            w = max(1, int(src.get_width() * h / src.get_height()))
            img = pygame.transform.smoothscale(src, (w, h))
            if flip:
                img = pygame.transform.flip(img, True, False)
            if len(self.cache) > 3000:
                self.cache.clear()
            self.cache[ck] = img
        return img

    def glow_img(self, color, r):
        r = max(2, int(r))
        if r > 32:
            r = int(round(1.05 ** round(math.log(r) / 0.0487902)))
        ck = (color, r)
        img = self.glow_cache.get(ck)
        if img is None:
            base = self.glow_base.get(color)
            if base is None:
                base = make_glow(color, 64)
                self.glow_base[color] = base
            img = pygame.transform.smoothscale(base, (2 * r, 2 * r))
            if len(self.glow_cache) > 1800:
                self.glow_cache.clear()
            self.glow_cache[ck] = img
        return img

    # ------------------------------------------------------------- projecao
    def cx(self, z):
        A, B = self.st["curve"]
        return A * math.sin(z / 110.0) + B * math.sin(z / 47.0 + 1.3)

    def dcx(self, z):
        A, B = self.st["curve"]
        return A / 110.0 * math.cos(z / 110.0) + B / 47.0 * math.cos(z / 47.0 + 1.3)

    def d2cx(self, z):
        A, B = self.st["curve"]
        return -A / 12100.0 * math.sin(z / 110.0) - B / 2209.0 * math.sin(z / 47.0 + 1.3)

    def warp_x(self, z):
        return self.cx(z) - self._cxc - self._dcxc * (z - self.cam_z)

    def warp_x_np(self, z):
        A, B = self.st["curve"]
        return A * np.sin(z / 110.0) + B * np.sin(z / 47.0 + 1.3) - self._cxc - self._dcxc * (z - self.cam_z)

    def proj(self, x, y, z):
        dz = z - self.cam_z
        if dz < 0.3:
            return None
        s = FOCAL / dz
        return W / 2 + (x + self.warp_x(z) - self.cam_x) * s, HORIZON - (y - CAM_H) * s, s

    # -------------------------------------------------------------- estado
    def reset_game(self):
        self.score = 0
        self.lives = 3
        self.hp = MAX_HP
        self.powers = {"triplo": 0.0, "rajada": 0.0, "gelo": 0.0, "escudo": 0.0}
        self.shield_hits = 0

    def start_stage(self, i, silent=False):
        self.stage_i = i
        self.st = STAGES[i]
        self.cam_z = 0.0
        self.cam_x = 0.0
        self.px = 0.0
        self.pvx = 0.0
        self.pz = PLAYER_DZ
        self.walk = 0.0
        self.last_step = 0
        self.bg_off = 0.0
        self.enemies, self.shots, self.fireballs, self.items, self.parts = [], [], [], [], []
        self.boss = None
        self.boss_spawned = False
        self.spawn_t = 2.5
        self.next_item_z = 45.0
        self.fire_cd = 0.0
        self.recoil = 0.0
        self.invul = 2.0
        self.shake = self.red_flash = self.white_flash = 0.0
        self.msg = None
        self.popups = []
        self.scen_cache = {}
        self.time = 0.0
        self._cxc, self._dcxc = self.cx(0), self.dcx(0)
        self.ambient = [self.new_ambient(random.uniform(3, 60)) for _ in range(45)]
        if not silent:
            self.message("Fase %d" % (i + 1), self.st["name"], 3.5)
            self.audio.music(i)

    def message(self, title, sub="", dur=2.5):
        self.msg = [title, sub, dur, dur]

    def popup(self, text, color):
        self.popups.append([text, color, 1.6])

    def progress(self):
        return clamp(self.cam_z / STAGE_LEN, 0, 1)

    # ------------------------------------------------------------- cenario
    def scenery_for(self, n):
        objs = self.scen_cache.get(n)
        if objs is not None:
            return objs
        rnd = random.Random(n * 7919 + self.stage_i * 104729)
        objs = []
        z0 = n * SEG
        if n % 4 == 0:
            for side in (-1, 1):
                objs.append((side * (ROAD_W + 1.9), z0, "coluna", 4.4, side > 0))
        for side in (-1, 1):
            if rnd.random() < 0.32:
                objs.append((side * (ROAD_W + rnd.uniform(4.0, 8.0)), z0 + rnd.random() * SEG, "carvalho",
                             rnd.uniform(6.0, 8.5), rnd.random() < 0.5))
            if rnd.random() < 0.18:
                objs.append((side * (ROAD_W + rnd.uniform(3.4, 6.5)), z0 + rnd.random() * SEG, "cipreste",
                             rnd.uniform(7.5, 10.0), rnd.random() < 0.5))
            if rnd.random() < 0.55:
                k = "carvalho" if rnd.random() < 0.6 else "cipreste"
                objs.append((side * (ROAD_W + rnd.uniform(10, 32)), z0 + rnd.random() * SEG, k,
                             rnd.uniform(7, 11), rnd.random() < 0.5))
        self.scen_cache[n] = objs
        return objs

    def new_ambient(self, dz=None):
        if dz is None:
            dz = random.uniform(40, 70)
        return [self.px + random.uniform(-10, 10), random.uniform(0.3, 4.0), self.cam_z + dz,
                random.uniform(0, 6.28), random.uniform(-0.3, 0.3)]

    # ------------------------------------------------------------ entidades
    def make_enemy(self, kind, x, z):
        if kind == "esqueleto":
            return Ent(kind=kind, x=x, y=0.0, cy=1.0, z=z, hp=3, r=0.65, h=1.95, v=random.uniform(1.1, 1.8),
                       t=random.uniform(0, 3), vzw=0.0, flash=0.0, score=150, cd=0.0, ph=0.0)
        if kind == "morcego":
            by = random.uniform(1.7, 3.0)
            return Ent(kind=kind, x=x, bx=x, y=by, by=by, cy=by, z=z, hp=1, r=0.8, h=1.0, v=random.uniform(2.6, 3.8),
                       t=0.0, ph=random.uniform(0, 6.28), amp=random.uniform(0.8, 2.0), vzw=0.0, flash=0.0,
                       score=100, cd=0.0)
        return Ent(kind="gosma", x=x, y=0.0, cy=0.4, z=z, hp=2, r=0.6, h=0.8, v=1.6, t=random.uniform(0, 3),
                   vzw=0.0, flash=0.0, score=120, cd=random.uniform(2.0, 4.0), ph=0.0, hop=0.0)

    def spawn(self, dt):
        if self.boss_spawned:
            return
        p = self.progress()
        if self.next_item_z - self.cam_z < SPAWN_DIST and p < 0.95:
            kind = random.choices(list(ITEMS), [v[2] for v in ITEMS.values()])[0]
            self.items.append(Ent(kind=kind, x=random.uniform(-ROAD_W + 0.8, ROAD_W - 0.8), y=0.55, cy=0.55,
                                  z=self.next_item_z, t=random.uniform(0, 6)))
            self.next_item_z += random.uniform(32, 50)
        self.spawn_t -= dt
        if self.spawn_t > 0 or p > 0.97:
            return
        self.spawn_t = max(1.3, 3.4 - 0.4 * self.stage_i - 1.0 * p) * random.uniform(0.8, 1.2)
        kind = wchoice(self.st["enemies"])
        z = self.cam_z + SPAWN_DIST
        if kind == "morcego":
            n = random.randint(2, 4)
            for i in range(n):
                self.enemies.append(self.make_enemy(kind, (i - (n - 1) / 2) * 1.8, z + abs(i - (n - 1) / 2) * 4))
        elif kind == "esqueleto":
            n = random.choice((1, 2, 3))
            for i in range(n):
                self.enemies.append(self.make_enemy(kind, (i - (n - 1) / 2) * 1.6 + random.uniform(-0.4, 0.4),
                                                    z + random.uniform(0, 3)))
        else:
            for i in range(random.randint(1, 3)):
                self.enemies.append(self.make_enemy(kind, random.uniform(-ROAD_W + 0.6, ROAD_W - 0.6), z + i * 5))

    def enemy_fire(self, x, y, z, speed=5.0, kind="fogo", aim_dx=0.0, aim_dy=0.0, color=(255, 140, 60)):
        dz = z - self.pz
        if dz < 3:
            return
        T = dz / (speed + FWD_SPEED)
        tx, ty = self.px + aim_dx, 1.0 + aim_dy
        self.fireballs.append(Ent(x=x, y=y, cy=y, z=z, vx=(tx - x) / T, vy=(ty - y) / T, vz=-speed, kind=kind,
                                  r=0.45, vzw=-speed, t=0.0, color=color))

    def spawn_boss(self):
        self.boss_spawned = True
        hp = self.st["boss_hp"]
        self.boss = Ent(x=0.0, y=0.0, cy=2.2, z=self.pz + 45, dist=45.0, hp=hp, maxhp=hp, t=0.0, cd=3.0,
                        summon=8.0, flash=0.0, r=1.5, dying=False, dying_t=0.0, vzw=FWD_SPEED, pattern=0)
        self.message("O Rei Ossudo desperta!", "Derrube o guardião da estrada", 3.2)
        self.audio.play("chefe")

    # ---------------------------------------------------------------- tiro
    def aim(self):
        if not self.test:
            self.aim_pos = pygame.mouse.get_pos()
        return self.aim_pos

    def targets(self):
        t = [e for e in self.enemies if not e.dead] + [f for f in self.fireballs if not f.dead]
        if self.boss and not self.boss.dying:
            t.append(self.boss)
        return t

    def pick_target(self, mx, my):
        best, bd = None, 1e9
        for o in self.targets():
            dz = o.z - self.pz
            if dz < 0.8 or o.z - self.cam_z > FAR * 0.8:
                continue
            p = self.proj(o.x, o.cy, o.z)
            if not p:
                continue
            rad = max(30, o.r * p[2] * 1.4)
            d = math.hypot(p[0] - mx, p[1] - my)
            if d < rad + 24 and d < bd:
                best, bd = o, d
        return best

    def fire(self):
        mx, my = self.aim()
        sx0, sy0, sz0 = self.px - 0.35, 1.05, self.pz + 0.4
        tgt = self.pick_target(mx, my)
        if tgt is not None:
            vz = tgt.vzw
            t = max(0.01, (tgt.z - sz0) / (SHOT_SPEED - vz))
            tx, ty, tz = tgt.x, tgt.cy, tgt.z + vz * t
        else:
            ax = (mx - W / 2) / FOCAL
            ay = (HORIZON - my) / FOCAL
            tt = (1.05 - CAM_H) / ay if ay < -0.02 else 60.0
            tt = clamp(tt, PLAYER_DZ + 4, 70)
            tz = self.cam_z + tt
            tx = self.cam_x + ax * tt - self.warp_x(tz)
            ty = 1.05
        angles = (-0.12, 0.0, 0.12) if self.powers["triplo"] > 0 else (0.0,)
        for a in angles:
            dx, dy, dz = tx - sx0, ty - sy0, tz - sz0
            ca, sa = math.cos(a), math.sin(a)
            dx, dz = dx * ca + dz * sa, -dx * sa + dz * ca
            n = math.sqrt(dx * dx + dy * dy + dz * dz) or 1
            self.shots.append(Ent(x=sx0, y=sy0, z=sz0, vx=dx / n * SHOT_SPEED, vy=dy / n * SHOT_SPEED,
                                  vz=dz / n * SHOT_SPEED, life=3.0, dmg=1, t=0.0))
        self.recoil = 1.0
        self.audio.play("espada", 0.7)
        self.audio.play("magia", 0.4)

    # -------------------------------------------------------------- efeitos
    def explode(self, x, y, z, color, n=26, power=4.0, size=0.18):
        if len(self.parts) > 600:
            n //= 3
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            b = random.uniform(-1, 1)
            sp = power * random.uniform(0.3, 1.0)
            r = math.sqrt(1 - b * b)
            self.parts.append(Ent(x=x, y=y, z=z, vx=math.cos(a) * r * sp, vy=b * sp + 1.5, vz=math.sin(a) * r * sp,
                                  life=random.uniform(0.4, 0.9), max=0.9, color=color, size=size, grav=True))
        self.parts.append(Ent(x=x, y=y, z=z, vx=0, vy=0, vz=0, life=0.25, max=0.25, color=(255, 235, 200),
                              size=size * 8, grav=False))

    def bones(self, x, z, n=10):
        """lascas de osso voando (morte do esqueleto)"""
        for _ in range(n):
            self.parts.append(Ent(x=x + random.uniform(-0.3, 0.3), y=random.uniform(0.4, 1.8), z=z,
                                  vx=random.uniform(-2.5, 2.5), vy=random.uniform(1, 4), vz=random.uniform(-1, 2.5),
                                  life=random.uniform(0.6, 1.1), max=1.1, color=(220, 210, 170), size=0.12, grav=True))

    def sparks(self, x, y, z, color, n=6):
        for _ in range(n):
            self.parts.append(Ent(x=x, y=y, z=z, vx=random.uniform(-3, 3), vy=random.uniform(-1, 4),
                                  vz=random.uniform(-3, 3), life=random.uniform(0.15, 0.35), max=0.35, color=color,
                                  size=0.1, grav=True))

    def hurt(self):
        if self.invul > 0 or self.state != "jogando":
            return
        if self.powers["escudo"] > 0:
            self.shield_hits -= 1
            self.invul = 0.6
            self.audio.play("escudo")
            self.audio.play("metal", 0.5)
            self.popup("Escudo!", (140, 255, 180))
            if self.shield_hits <= 0:
                self.powers["escudo"] = 0
            return
        self.hp -= 1
        self.invul = 1.4
        self.shake = 0.35
        self.red_flash = 0.5
        self.audio.play("dano")
        if self.hp <= 0:
            self.lives -= 1
            if self.lives <= 0:
                self.state = "game_over"
                self.over_t = 0.0
                self.hiscore = max(self.hiscore, self.score)
                return
            self.hp = MAX_HP
            self.invul = 3.0
            for f in self.fireballs:
                f.dead = True
            self.message("Você caiu!", "Vidas restantes: %d" % self.lives, 2.5)

    def kill_enemy(self, e):
        e.dead = True
        self.score += e.score
        if e.kind == "esqueleto":
            self.bones(e.x, e.z, 14)
            self.explode(e.x, 1.0, e.z, (230, 220, 180), n=12, power=3)
            self.audio.play("osso")
        elif e.kind == "morcego":
            self.explode(e.x, e.y, e.z, (150, 70, 60), n=22, power=4)
            self.audio.play("morcego", 0.6)
        else:
            self.explode(e.x, 0.4, e.z, (90, 230, 90), n=30, power=4, size=0.2)
            self.audio.play("gosma")

    def damage(self, o, dmg):
        if o is self.boss:
            o.hp -= dmg
            o.flash = 0.07
            self.sparks(o.x + random.uniform(-0.8, 0.8), o.cy + random.uniform(-1, 1.2), o.z - 0.8, (255, 230, 180), 5)
            self.audio.play("metal", 0.45)
            if o.hp <= 0 and not o.dying:
                o.dying = True
                o.dying_t = 0.0
                self.score += 5000 * (self.stage_i + 1)
                for e in self.enemies:
                    e.dead = True
                for f in self.fireballs:
                    f.dead = True
            return
        if o in self.fireballs:
            o.dead = True
            self.score += 10
            self.explode(o.x, o.y, o.z, o.color, n=10, power=3, size=0.12)
            return
        o.hp -= dmg
        o.flash = 0.09
        self.audio.play({"esqueleto": "osso", "morcego": "morcego", "gosma": "gosma"}[o.kind], 0.55)
        self.sparks(o.x, o.cy, o.z - 0.4, (255, 255, 220), 4)
        if o.hp <= 0:
            self.kill_enemy(o)

    def collect(self, it):
        it.dead = True
        c, name, _ = ITEMS[it.kind]
        self.popup("+ " + name, c)
        self.audio.play("item")
        self.explode(it.x, it.y, it.z, (140, 200, 255), n=18, power=2.5, size=0.12)
        k = it.kind
        if k == "coracao":
            self.hp = min(MAX_HP, self.hp + 2)
        elif k in ("triplo", "rajada"):
            self.powers[k] = 15.0
        elif k == "gelo":
            self.powers["gelo"] = 6.0
        elif k == "escudo":
            self.powers["escudo"] = 15.0
            self.shield_hits = 3
        elif k == "tesouro":
            self.score += 1000
        elif k == "bomba":
            self.white_flash = 0.7
            self.shake = 0.5
            self.audio.play("bomba")
            for e in self.enemies:
                if not e.dead and e.z - self.cam_z < FAR * 0.8:
                    self.kill_enemy(e)
            for f in self.fireballs:
                f.dead = True
            if self.boss and not self.boss.dying:
                self.damage(self.boss, 10)

    # --------------------------------------------------------------- update
    def update(self, dt):
        self.time += dt
        if self.msg:
            self.msg[2] -= dt
            if self.msg[2] <= 0:
                self.msg = None
        for p in self.popups:
            p[2] -= dt
        self.popups = [p for p in self.popups if p[2] > 0]
        self.shake = max(0.0, self.shake - dt)
        self.red_flash = max(0.0, self.red_flash - dt)
        self.white_flash = max(0.0, self.white_flash - dt)
        self.recoil = max(0.0, self.recoil - dt * 5)
        if self.state == "titulo":
            self.advance(dt, FWD_SPEED, auto=True)
            self.update_parts(dt)
            return
        if self.state == "pausa":
            return
        if self.state == "game_over":
            self.over_t += dt
            self.update_parts(dt)
            return
        if self.state in ("fase_concluida", "vitoria"):
            self.clear_t -= dt
            self.advance(dt, FWD_SPEED, auto=True)
            self.update_parts(dt)
            if self.state == "fase_concluida" and self.clear_t <= 0:
                self.start_stage(self.stage_i + 1)
                self.state = "jogando"
            return
        self.update_play(dt)

    def advance(self, dt, speed, auto=False):
        if auto:
            self.px += (math.sin(self.time * 0.35) * 1.2 - self.px) * dt
        self.cam_x += (self.px * 0.65 - self.cam_x) * min(1.0, dt * 3.5)
        self.cam_z += speed * dt
        self.pz = self.cam_z + PLAYER_DZ
        self.walk += dt * speed * 2.1
        step = int(self.walk / math.pi)
        if step != self.last_step:
            self.last_step = step
            if self.state == "jogando":
                self.audio.play("passo", 0.35)
        self.bg_off += -self.d2cx(self.cam_z) * speed * dt * 9000 + self.pvx * dt * 4
        self._cxc, self._dcxc = self.cx(self.cam_z), self.dcx(self.cam_z)
        base = int(self.cam_z // SEG)
        for n in [k for k in self.scen_cache if k < base - 1]:
            del self.scen_cache[n]
        for a in self.ambient:
            a[3] += dt
            a[1] += (math.sin(a[3] * 1.3) * 0.3 + (0.25 if self.stage_i == 1 else 0)) * dt
            a[0] += a[4] * dt
            if a[2] < self.cam_z + 1 or a[1] > 6:
                a[:] = self.new_ambient()

    def update_parts(self, dt):
        for p in self.parts:
            p.life -= dt
            if p.grav:
                p.vy -= 9 * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.z += p.vz * dt
            if p.y < 0 and p.grav:
                p.y = 0
                p.vy *= -0.35
                p.vx *= 0.6
                p.vz *= 0.6
        self.parts = [p for p in self.parts if p.life > 0 and p.z > self.cam_z + 0.5]

    def update_play(self, dt):
        if self.test:
            self.autopilot()
            mv = self._auto_mv
        else:
            keys = pygame.key.get_pressed()
            mv = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
            self.firing = (self.mouse_held or pygame.mouse.get_pressed()[0] or keys[pygame.K_SPACE]
                           or keys[pygame.K_j] or keys[pygame.K_LCTRL])
        self.pvx += (mv * STRAFE_SPEED - self.pvx) * min(1.0, dt * 10)
        self.px = clamp(self.px + self.pvx * dt, -WALK_LIM, WALK_LIM)
        self.advance(dt, FWD_SPEED)
        for k in self.powers:
            self.powers[k] = max(0.0, self.powers[k] - dt)
        self.invul = max(0.0, self.invul - dt)
        frozen = self.powers["gelo"] > 0
        self.fire_cd -= dt
        if self.firing and self.fire_cd <= 0:
            self.fire()
            self.fire_cd = 0.11 if self.powers["rajada"] > 0 else 0.26
        self.spawn(dt)
        if not self.boss_spawned and self.progress() >= 1.0:
            self.spawn_boss()
        pz = self.pz
        for e in self.enemies:
            if e.dead:
                continue
            e.flash = max(0.0, e.flash - dt)
            if not frozen:
                self.update_enemy(e, dt)
            if e.z - pz < 0.5:
                if e.z - pz > -0.6 and abs(e.x - self.px) < e.r + 0.4 and (e.kind != "morcego" or e.y < 2.4):
                    self.hurt()
                    self.explode(e.x, e.cy, pz + 0.3, (255, 140, 120), n=10, power=2.5)
                    e.dead = True
                elif e.z - pz < -1.0:
                    e.dead = True
        for it in self.items:
            it.t += dt
            dz = it.z - pz
            if abs(dz) < 0.9 and abs(it.x - self.px) < 1.0:
                self.collect(it)
            elif dz < -2:
                it.dead = True
        for f in self.fireballs:
            if f.dead:
                continue
            if not frozen:
                f.t += dt
                f.x += f.vx * dt
                f.y += f.vy * dt
                f.z += f.vz * dt
                f.cy = f.y
            if f.z - pz < 0.35:
                if f.z - pz > -0.5 and abs(f.x - self.px) < 0.6 and abs(f.y - 1.0) < 1.0:
                    self.hurt()
                    self.explode(f.x, f.y, pz + 0.3, f.color, n=12, power=2.5, size=0.12)
                    f.dead = True
                elif f.z - pz < -1.5 or f.y < 0:
                    f.dead = True
        if self.boss:
            self.update_boss(dt, frozen)
        self.update_shots(dt)
        self.update_parts(dt)
        self.enemies = [e for e in self.enemies if not e.dead]
        self.items = [i for i in self.items if not i.dead]
        self.fireballs = [f for f in self.fireballs if not f.dead]

    def update_enemy(self, e, dt):
        e.t += dt
        dzk = e.z - self.pz
        lim = WALK_LIM + 0.5
        if e.kind == "esqueleto":
            spd = e.v * (2.0 if dzk < 7 else 1.0)          # arranca quando chega perto
            e.z -= spd * dt
            e.vzw = -spd
            e.x = clamp(e.x + clamp(self.px - e.x, -1, 1) * 0.6 * dt, -lim, lim)
            e.y = abs(math.sin(e.t * 5.0)) * 0.05
        elif e.kind == "morcego":
            e.z -= e.v * dt
            e.vzw = -e.v
            e.x = clamp(e.bx + math.sin(e.t * 1.5 + e.ph) * e.amp, -lim, lim)
            target_y = 1.3 if dzk < 12 else e.by
            e.by += (target_y - e.by) * min(1, dt * 1.5)
            e.y = e.by + math.sin(e.t * 6 + e.ph) * 0.18
            e.cy = e.y
            if dzk < 14:
                e.bx += clamp(self.px - e.bx, -1, 1) * 1.2 * dt
        else:
            prev = e.hop
            e.hop = abs(math.sin(e.t * 2.8))
            e.y = e.hop * 0.85
            e.cy = 0.35 + e.y
            if e.hop > 0.12:
                e.z -= e.v * 1.8 * dt
                e.vzw = -e.v * 1.8
                e.x = clamp(e.x + clamp(self.px - e.x, -1, 1) * 0.9 * dt, -lim, lim)
            else:
                e.vzw = 0.0
            if prev > 0.12 >= e.hop and 0 < dzk < 30:
                self.audio.play("gosma", 0.12)
            e.cd -= dt
            if e.cd <= 0 and 6 < dzk < 40:
                self.enemy_fire(e.x, 0.6, e.z - 0.3, speed=4.5, kind="gosma", color=(90, 230, 90))
                self.audio.play("inimigo_tiro", 0.3)
                e.cd = random.uniform(3.0, 4.5)

    def update_boss(self, dt, frozen):
        b = self.boss
        b.t += dt
        b.flash = max(0.0, b.flash - dt)
        if b.dist > 14:
            b.dist = max(14.0, b.dist - 6 * dt)
            b.vzw = FWD_SPEED - 6
        else:
            b.vzw = FWD_SPEED
        b.z = self.pz + b.dist + math.sin(b.t * 0.5) * 1.2
        b.x = math.sin(b.t * 0.55) * 2.2
        b.y = abs(math.sin(b.t * 2.2)) * 0.06
        b.cy = 2.2
        if b.dying:
            b.dying_t += dt
            if random.random() < dt * 14:
                self.explode(b.x + random.uniform(-1.4, 1.4), random.uniform(0.5, 4.0), b.z - 0.5,
                             random.choice([(120, 240, 255), (230, 220, 180), (255, 240, 200)]), n=20, power=5)
                if random.random() < 0.3:
                    self.audio.play("osso", 0.7)
                self.shake = 0.2
            if b.dying_t > 2.8:
                self.bones(b.x, b.z, 40)
                self.explode(b.x, 2.2, b.z, (200, 250, 255), n=120, power=10, size=0.3)
                self.white_flash = 0.8
                self.audio.play("bomba")
                self.boss = None
                self.stage_clear()
            return
        if frozen or b.dist > 20:
            return
        phase = 0 if b.hp > b.maxhp * 0.66 else 1 if b.hp > b.maxhp * 0.33 else 2
        b.cd -= dt
        if b.cd <= 0:
            b.pattern = (b.pattern + 1) % 3
            if b.pattern != 1:
                n = 5 + 2 * phase
                for i in range(n):
                    self.enemy_fire(b.x, 3.4, b.z - 0.6, speed=4 + phase, aim_dx=(i - (n - 1) / 2) * 1.3,
                                    color=(110, 230, 255))
            else:
                k = 8 + 2 * phase
                rot = random.uniform(0, 6.28)
                for i in range(k):
                    a = rot + i / k * 2 * math.pi
                    self.enemy_fire(b.x, 3.0, b.z - 0.6, speed=3.5 + phase, aim_dx=math.cos(a) * 2.2,
                                    aim_dy=math.sin(a) * 0.8 + 0.3, color=(170, 120, 255))
            self.audio.play("inimigo_tiro", 0.6)
            b.cd = 2.4 - 0.5 * phase
        b.summon -= dt
        if b.summon <= 0:
            kind = random.choice(("esqueleto", "morcego"))
            for i in range(2):
                self.enemies.append(self.make_enemy(kind, b.x + (i - 0.5) * 2.4, b.z - 1.5))
            b.summon = random.uniform(7, 10) - phase * 1.5

    def update_shots(self, dt):
        tg = self.targets()
        for s in self.shots:
            ox, oy, oz = s.x, s.y, s.z
            s.x += s.vx * dt
            s.y += s.vy * dt
            s.z += s.vz * dt
            s.life -= dt
            s.t += dt
            if len(self.parts) < 500 and int(s.t * 60) % 2 == 0:
                self.parts.append(Ent(x=s.x + random.uniform(-0.04, 0.04), y=s.y + random.uniform(-0.04, 0.04), z=s.z,
                                      vx=random.uniform(-0.3, 0.3), vy=random.uniform(-0.2, 0.3), vz=0, life=0.28,
                                      max=0.28, color=(90, 150, 255) if self.powers["triplo"] <= 0 else (220, 170, 60),
                                      size=0.14, grav=False))
            if s.y < 0:
                s.dead = True
                self.sparks(s.x, 0.05, s.z, (160, 210, 255), 5)
                continue
            for o in tg:
                if o.dead or abs(o.z - s.z) > 4:
                    continue
                if seg_dist2(ox, oy, oz - 0.6, s.x, s.y, s.z, o.x, o.cy, o.z) < o.r * o.r:
                    self.damage(o, s.dmg)
                    s.dead = True
                    break
        self.shots = [s for s in self.shots if not s.dead and s.life > 0 and s.z - self.cam_z < FAR]

    def stage_clear(self):
        bonus = 2000 * (self.stage_i + 1) + self.hp * 300
        self.score += bonus
        self.hiscore = max(self.hiscore, self.score)
        if self.stage_i + 1 < len(STAGES):
            self.state = "fase_concluida"
            self.clear_t = 5.0
            self.message("Fase concluída!", "Bônus %d" % bonus, 4.5)
        else:
            self.state = "vitoria"
            self.clear_t = 0
            self.message("A Aurora retorna!", "Bônus %d" % bonus, 6)
        self.enemies.clear()
        self.fireballs.clear()

    def autopilot(self):
        self.firing = True
        best = None
        for o in self.targets():
            dz = o.z - self.pz
            if 1 < dz < 60 and (best is None or dz < best.z - self.pz):
                best = o
        if best is not None:
            p = self.proj(best.x, best.cy, best.z)
            if p:
                self.aim_pos = (int(p[0]), int(p[1]))
        tx = 0.0
        for it in self.items:
            if 0 < it.z - self.pz < 25:
                tx = it.x
        for f in self.fireballs + self.enemies:
            if 0 < f.z - self.pz < 6 and abs(f.x - self.px) < 1.0:
                tx = self.px + (2.0 if f.x <= self.px else -2.0)
        self._auto_mv = clamp((tx - self.px) * 2, -1, 1)

    # ---------------------------------------------------------------- desenho
    def blit_world(self, surf, key, x, y, z, height_m, anchor="bottom", flip=False):
        p = self.proj(x, y, z)
        if not p:
            return None
        sx, sy, s = p
        hp = int(height_m * s)
        if hp < 2 or hp > H * 2.6:
            return p
        img = self.scaled(key, hp, flip)
        if anchor == "bottom":
            rect = img.get_rect(midbottom=(int(sx), int(sy)))
        else:
            rect = img.get_rect(center=(int(sx), int(sy)))
        if rect.right < 0 or rect.left > W or rect.bottom < 0 or rect.top > H:
            return p
        fade = clamp((FAR - (z - self.cam_z)) / (FAR * 0.4), 0, 1)
        if fade < 1:
            img.set_alpha(int(255 * fade))
            surf.blit(img, rect)
            img.set_alpha(255)
        else:
            surf.blit(img, rect)
        return p

    def wglow(self, surf, x, y, z, radius_m, color, mult=1.0, maxr=520):
        p = self.proj(x, y, z)
        if not p:
            return
        sx, sy, s = p
        r = min(radius_m * s, maxr)
        if r < 1.5:
            return
        f = clamp((FAR - (z - self.cam_z)) / (FAR * 0.4), 0, 1) * mult
        f = round(f * 4) / 4
        if f <= 0:
            return
        col = color if f >= 1 else (int(color[0] * f), int(color[1] * f), int(color[2] * f))
        img = self.glow_img(col, r)
        surf.blit(img, (int(sx - img.get_width() / 2), int(sy - img.get_height() / 2)),
                  special_flags=pygame.BLEND_RGB_ADD)

    def shadow(self, surf, x, z, w_m):
        self.blit_world(surf, "sombra", x, 0.0, z, w_m * 0.4, "center")

    def draw_sky(self, surf):
        w = self.sky.get_width()
        off = int(self.bg_off * 0.4 + self.cam_x * 10) % w
        surf.blit(self.sky, (-off, 0))
        surf.blit(self.sky, (w - off, 0))
        surf.blit(self.haze[self.stage_i], (0, HORIZON - 108))

    def draw_floor(self, surf):
        dz = self.fl_dz
        z = self.cam_z + dz
        off = (self.cam_x - self.warp_x_np(z)).astype(np.float32)
        X = self.fl_xd + off[:, None]
        ax = np.abs(X)
        res = np.empty(X.shape, np.uint32)
        gbuf = np.empty(X.shape, np.uint32)
        for dst, bands, mp, tile, xoff in ((res, self.b_road, self.road_p, self.road_tile, ROAD_W),
                                           (gbuf, self.b_grass, self.grass_p, self.grass_tile, 0.0)):
            for a, b, k in bands:
                tex, Tk = mp[k]
                tpm = Tk / tile
                u = ((X[a:b] + xoff) * tpm).astype(np.int32) & (Tk - 1)
                v = (z[a:b] * tpm).astype(np.int32) & (Tk - 1)
                dst[a:b] = tex[(v * Tk)[:, None] + u]
        nu = (X * 20).astype(np.int32) & 255
        nv = (z * 20).astype(np.int32) & 255
        nz = self.edge_noise[(nv * 256)[:, None] + nu]
        np.copyto(res, gbuf, where=(ROAD_W - ax + (nz - 0.5) * 1.8) < 0)
        pix = pygame.surfarray.pixels2d(self.floor_small)
        pix[:, :self.fl_r0] = self.fog_p[self.stage_i]
        pix[:, self.fl_r0:] = res.T
        del pix
        pygame.transform.smoothscale(self.floor_small, (W, H - HORIZON), self.floor_big)
        self.floor_big.blit(self.fog_over[self.stage_i], (0, 0))
        surf.blit(self.floor_big, (0, HORIZON))

    def draw_world(self, surf):
        self.draw_sky(surf)
        self.draw_floor(surf)
        cz = self.cam_z
        dr = []
        base = int(cz // SEG)
        for n in range(base, base + DRAW_SEGS):
            for o in self.scenery_for(n):
                dz = o[1] - cz
                if 0.6 < dz < FAR:
                    dr.append((dz, 0, o))
        for e in self.enemies:
            dr.append((e.z - cz, 1, e))
        for it in self.items:
            dr.append((it.z - cz, 2, it))
        for f in self.fireballs:
            dr.append((f.z - cz, 3, f))
        for s in self.shots:
            dr.append((s.z - cz, 4, s))
        for p in self.parts:
            dr.append((p.z - cz, 5, p))
        for a in self.ambient:
            dr.append((a[2] - cz, 6, a))
        if self.boss:
            dr.append((self.boss.z - cz, 7, self.boss))
        if self.state != "game_over":
            dr.append((self.pz - cz, 8, None))
        dr.sort(key=lambda d: -d[0])
        fns = (self.d_scen, self.d_enemy, self.d_item, self.d_fire, self.d_shot, self.d_part, self.d_amb,
               self.d_boss, self.d_knight)
        for dz, k, o in dr:
            if dz > 0.5:
                fns[k](surf, o)

    def d_scen(self, surf, o):
        x, z, key, hgt, flip = o
        self.blit_world(surf, key, x, 0, z, hgt, "bottom", flip)

    def d_enemy(self, surf, e):
        frozen = self.powers["gelo"] > 0
        hit = "_hit" if e.flash > 0 else ""
        if e.kind == "esqueleto":
            self.shadow(surf, e.x, e.z, 1.3)
            if self.has_esq:
                key = "esq%d" % (int(e.t * 5.0 / math.pi * 4) % 8 if not frozen else 0)
                self.blit_world(surf, key + hit, e.x, 0.0, e.z, e.h * 1.04, "bottom")
            else:
                key = "esqueleto" + ("_l" if int(e.t * 2.5) % 2 else "_r")
                self.blit_world(surf, key + hit, e.x, e.y, e.z, e.h, "bottom")
        elif e.kind == "morcego":
            self.shadow(surf, e.x, e.z, 1.2 * clamp(2.5 / max(e.y, 0.5), 0.4, 1.2))
            key = "morcego" if int((0 if frozen else self.time) * 8 + e.ph) % 2 == 0 else "morcego1"
            self.blit_world(surf, key + hit, e.x, e.y, e.z, e.h if key == "morcego" else e.h * 0.62, "center")
        else:
            self.shadow(surf, e.x, e.z, 1.1 * (1 - e.hop * 0.4))
            if e.hop < 0.12:
                key, h = "gosma_sq", e.h * 0.74
            elif math.cos(e.t * 2.8) * math.sin(e.t * 2.8) > 0:
                key, h = "gosma_st", e.h * 1.2
            else:
                key, h = "gosma", e.h
            self.blit_world(surf, key + hit, e.x, e.y, e.z, h, "bottom")
        if frozen:
            self.wglow(surf, e.x, e.cy, e.z - 0.3, e.r * 1.8, (30, 70, 140))

    def d_item(self, surf, it):
        c = ITEMS[it.kind][0]
        y = it.y + math.sin(it.t * 2.5) * 0.12
        self.shadow(surf, it.x, it.z, 0.7)
        self.wglow(surf, it.x, y, it.z, 1.3 + 0.15 * math.sin(it.t * 5), (40, 90, 170))
        self.wglow(surf, it.x, y, it.z, 0.6, (c[0] // 3, c[1] // 3, c[2] // 3))
        self.blit_world(surf, "cristal", it.x, y, it.z, 0.9, "center", int(it.t * 1.5) % 2 == 0)

    def d_fire(self, surf, f):
        c = f.color
        self.wglow(surf, f.x, f.y, f.z, 1.1, (c[0] // 2, c[1] // 2, c[2] // 2), maxr=120)
        self.wglow(surf, f.x, f.y, f.z, 0.35, (255, 255, 255), maxr=40)
        p = self.proj(f.x, f.y, f.z)
        if p:
            pygame.draw.circle(surf, lerp_col(c, (255, 255, 255), 0.5), (int(p[0]), int(p[1])),
                               max(2, min(14, int(0.16 * p[2]))))

    def d_shot(self, surf, s):
        p1 = self.proj(s.x, s.y, s.z)
        p0 = self.proj(s.x - s.vx * 0.04, s.y - s.vy * 0.04, s.z - s.vz * 0.04)
        if not p1:
            return
        col = (255, 220, 110) if self.powers["triplo"] > 0 else (130, 200, 255)
        if p0:
            w = min(9, max(3, int(0.14 * p1[2])))
            pygame.draw.line(surf, col, p0[:2], p1[:2], w)
            pygame.draw.line(surf, (255, 255, 255), p0[:2], p1[:2], max(1, w // 2))
        self.wglow(surf, s.x, s.y, s.z, 0.9, (col[0] // 3, col[1] // 3, col[2] // 3), maxr=70)
        pygame.draw.circle(surf, (255, 255, 255), (int(p1[0]), int(p1[1])), min(7, max(2, int(0.1 * p1[2]))))

    def d_part(self, surf, p):
        k = clamp(p.life / p.max, 0, 1)
        col = p.color if k > 0.5 else lerp_col((0, 0, 0), p.color, k * 2)
        col = (col[0] // 8 * 8, col[1] // 8 * 8, col[2] // 8 * 8)
        self.wglow(surf, p.x, p.y, p.z, p.size * (0.6 + k), col, maxr=40 if p.size < 0.2 else 400)

    def d_amb(self, surf, a):
        tw = 0.5 + 0.5 * math.sin(a[3] * 3)
        c = self.st["ambient"]
        k = (0.35 if self.stage_i == 0 else 0.7) * tw
        col = (int(c[0] * k) // 16 * 16, int(c[1] * k) // 16 * 16, int(c[2] * k) // 16 * 16)
        if sum(col) > 0:
            self.wglow(surf, a[0], a[1], a[2], 0.12, col, maxr=24)

    def d_boss(self, surf, b):
        self.shadow(surf, b.x, b.z, 3.6)
        key = "chefe" + ("_l" if int(b.t * 1.4) % 2 else "_r")
        if b.flash > 0:
            key += "_hit"
        self.blit_world(surf, key, b.x, b.y, b.z, 4.6, "bottom")
        pulse = 0.7 + 0.3 * math.sin(b.t * 4)
        self.wglow(surf, b.x, 4.05, b.z - 0.2, 0.55, (40, 140, 170), pulse, maxr=80)
        if self.powers["gelo"] > 0:
            self.wglow(surf, b.x, 2.2, b.z - 0.5, 2.6, (30, 70, 140))

    def d_knight(self, surf, _):
        if self.invul > 0 and self.state == "jogando" and int(self.time * 14) % 2:
            return
        x, z = self.px, self.pz
        self.shadow(surf, x, z, 1.4)
        if self.has_cav:
            key = "cav%d" % (int(self.walk / (2 * math.pi) * 8) % 8)
            y = 0.0
        else:
            key = "cavaleiro_l" if int(self.walk / math.pi) % 2 else "cavaleiro_r"
            y = abs(math.sin(self.walk)) * 0.05
        if self.recoil > 0:
            self.wglow(surf, x - 0.45, 0.95, z - 0.1, 0.5 + self.recoil * 0.7, (40, 90, 160), maxr=160)
        self.blit_world(surf, key, x, y, z, 1.6, "bottom")
        if self.recoil > 0.4:
            self.wglow(surf, x - 0.5, 0.9, z - 0.2, 0.25 + self.recoil * 0.3, (200, 230, 255), maxr=60)
        if self.powers["escudo"] > 0:
            self.wglow(surf, x, 0.9, z - 0.2, 1.3, (20, 70, 40), 0.8 + 0.2 * math.sin(self.time * 5))

    def draw_crosshair(self, surf):
        mx, my = self.aim()
        lock = self.pick_target(mx, my) is not None
        col = (255, 90, 80) if lock else (240, 245, 255)
        r = 14 if lock else 18
        a = self.time * 3 if lock else 0
        pygame.draw.circle(surf, (0, 0, 0), (mx + 1, my + 1), r, 2)
        pygame.draw.circle(surf, col, (mx, my), r, 2)
        for k in range(4):
            ang = a + k * math.pi / 2
            p0 = (mx + math.cos(ang) * (r + 4), my + math.sin(ang) * (r + 4))
            p1 = (mx + math.cos(ang) * (r + 12), my + math.sin(ang) * (r + 12))
            pygame.draw.line(surf, col, p0, p1, 2)

    def text(self, surf, msg, font, color, alpha=255, **pos):
        img = font.render(msg, True, color)
        sh = font.render(msg, True, (0, 0, 0))
        rect = img.get_rect(**pos)
        if alpha < 255:
            img.set_alpha(alpha)
            sh.set_alpha(int(alpha * 0.7))
        surf.blit(sh, rect.move(3, 3))
        surf.blit(img, rect)
        return rect

    def glow_text(self, surf, msg, font, color, glowc, **pos):
        img = font.render(msg, True, glowc)
        rect = img.get_rect(**pos)
        w, h = img.get_size()
        small = pygame.transform.smoothscale(img, (max(1, w // 10), max(1, h // 10)))
        blur = pygame.transform.smoothscale(small, (w + 40, h + 40))
        surf.blit(blur, rect.move(-20, -20), special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(blur, rect.move(-20, -20), special_flags=pygame.BLEND_RGB_ADD)
        self.text(surf, msg, font, color, **pos)

    def draw_hud(self, surf):
        for i in range(MAX_HP):
            surf.blit(self.heart_full if i < self.hp else self.heart_empty, (24 + i * 40, 20))
        self.text(surf, "VIDAS  x%d" % self.lives, self.f_small, (245, 235, 210), topleft=(26, 62))
        self.text(surf, "PONTOS %07d" % self.score, self.f_small, (255, 230, 150), topright=(W - 24, 20))
        self.text(surf, "RECORDE %07d" % max(self.hiscore, self.score), self.f_tiny, (225, 225, 235),
                  topright=(W - 24, 50))
        bw, bx, byy = 420, W // 2 - 210, 22
        bar = pygame.Surface((bw, 14), SRCALPHA)
        bar.fill((0, 0, 0, 150))
        surf.blit(bar, (bx, byy))
        if self.boss:
            k = max(0, self.boss.hp) / self.boss.maxhp
            pygame.draw.rect(surf, (200, 30, 40), (bx + 2, byy + 2, int((bw - 4) * k), 10))
            self.text(surf, "REI OSSUDO", self.f_tiny, (255, 200, 200), midtop=(W // 2, byy + 16))
        else:
            k = self.progress()
            pygame.draw.rect(surf, (210, 190, 140), (bx + 2, byy + 2, int((bw - 4) * k), 10))
            pygame.draw.circle(surf, (255, 255, 255), (bx + 2 + int((bw - 4) * k), byy + 7), 7)
            pygame.draw.circle(surf, (200, 40, 50), (bx + bw, byy + 7), 8)
            self.text(surf, "Fase %d  —  %s" % (self.stage_i + 1, self.st["name"]), self.f_tiny,
                      (240, 240, 245), midtop=(W // 2, byy + 16))
        y = H - 60
        for k in ("triplo", "rajada", "gelo", "escudo"):
            t = self.powers[k]
            if t > 0:
                surf.blit(self.scaled("item_" + k, 40), (22, y))
                tot = 6.0 if k == "gelo" else 15.0
                pygame.draw.rect(surf, (0, 0, 0), (68, y + 16, 104, 10))
                pygame.draw.rect(surf, ITEMS[k][0], (70, y + 18, int(100 * t / tot), 6))
                label = ITEMS[k][1] + (" x%d" % self.shield_hits if k == "escudo" else "")
                self.text(surf, label, self.f_tiny, (245, 245, 245), topleft=(180, y + 10))
                y -= 46
        for i, (txt, col, t) in enumerate(self.popups):
            a = int(255 * clamp(t / 0.6, 0, 1))
            self.text(surf, txt, self.f_med, col, alpha=a, center=(W // 2, H - 150 - i * 38 - (1.6 - t) * 40))

    def draw_message(self, surf):
        if not self.msg:
            return
        title, sub, t, tot = self.msg
        a = int(255 * clamp(min(t / 0.6, (tot - t) / 0.4 + 0.2), 0, 1))
        self.text(surf, title, self.f_big, (255, 244, 210), alpha=a, center=(W // 2, H // 2 - 150))
        if sub:
            self.text(surf, sub, self.f_med, (235, 235, 245), alpha=a, center=(W // 2, H // 2 - 100))

    def draw(self):
        surf = self.view
        self.draw_world(surf)
        g = self.st["grade"]
        if g:
            surf.fill(g, special_flags=pygame.BLEND_RGB_MULT)
        if self.stage_i == 2:   # noite: o brilho dos cristais volta por cima
            for it in self.items:
                self.wglow(surf, it.x, it.y, it.z, 1.0, (30, 60, 120))
        if self.powers["gelo"] > 0 and self.state == "jogando":
            surf.blit(self.edge_ice, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        if self.powers["escudo"] > 0 and self.state == "jogando" and math.sin(self.time * 4) > -0.4:
            surf.blit(self.edge_shield, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(self.vignette, (0, 0))
        if self.state in ("jogando", "pausa", "fase_concluida"):
            self.draw_hud(surf)
            if self.state == "jogando":
                self.draw_crosshair(surf)
        if self.red_flash > 0:
            o = pygame.Surface((W, H), SRCALPHA)
            o.fill((200, 0, 0, int(120 * self.red_flash / 0.5)))
            surf.blit(o, (0, 0))
        if self.white_flash > 0:
            o = pygame.Surface((W, H), SRCALPHA)
            o.fill((255, 250, 235, int(230 * min(1, self.white_flash / 0.5))))
            surf.blit(o, (0, 0))
        self.draw_message(surf)
        if self.state == "titulo":
            self.draw_title(surf)
        elif self.state == "pausa":
            self.text(surf, "PAUSA", self.f_big, (255, 255, 255), center=(W // 2, H // 2))
        elif self.state == "game_over":
            o = pygame.Surface((W, H), SRCALPHA)
            o.fill((20, 0, 0, int(min(170, self.over_t * 120))))
            surf.blit(o, (0, 0))
            self.glow_text(surf, "FIM DE JOGO", self.f_huge, (255, 205, 195), (160, 30, 20),
                           center=(W // 2, H // 2 - 40))
            self.text(surf, "Pontos: %d" % self.score, self.f_med, (255, 230, 160), center=(W // 2, H // 2 + 40))
            if self.over_t > 2:
                self.text(surf, "Clique para voltar ao título", self.f_small, (235, 235, 235),
                          center=(W // 2, H // 2 + 100))
        elif self.state == "vitoria":
            self.glow_text(surf, "VITÓRIA", self.f_huge, (255, 245, 210), (180, 130, 40), center=(W // 2, H // 2 + 40))
            self.text(surf, "Pontos: %d" % self.score, self.f_med, (255, 230, 160), center=(W // 2, H // 2 + 110))
            self.text(surf, "Clique para voltar ao título", self.f_small, (235, 235, 235),
                      center=(W // 2, H // 2 + 160))
        if self.show_fps:
            self.text(surf, "%d fps" % self.clock.get_fps(), self.f_tiny, (180, 255, 180), topleft=(10, H - 26))
        ox = oy = 0
        if self.shake > 0:
            m = self.shake * 24
            ox, oy = random.uniform(-m, m), random.uniform(-m, m)
        self.screen.fill((0, 0, 0))
        self.screen.blit(surf, (ox, oy))

    def draw_title(self, surf):
        o = pygame.Surface((W, H), SRCALPHA)
        o.fill((0, 0, 10, 80))
        surf.blit(o, (0, 0))
        self.glow_text(surf, "LÂMINA DA AURORA", self.f_huge, (255, 246, 225), (70, 110, 170), center=(W // 2, 150))
        self.text(surf, "a estrada das colunas", self.f_small, (235, 235, 245), center=(W // 2, 214))
        if int(self.time * 2) % 2 == 0:
            self.text(surf, "Clique ou Enter para começar", self.f_med, (255, 232, 150), center=(W // 2, 300))
        lines = ["A/D ou setas: andar para os lados     Mouse: mirar     Clique/Espaço/J: atacar",
                 "Passe por cima dos cristais azuis para ganhar poderes",
                 "P: pausa     F: tela cheia     Esc: sair"]
        for i, l in enumerate(lines):
            self.text(surf, l, self.f_tiny, (240, 240, 245), center=(W // 2, H - 110 + i * 26))

    # ------------------------------------------------------------------ loop
    def begin(self):
        self.reset_game()
        self.start_stage(0)
        self.state = "jogando"
        self.mouse_held = False
        pygame.mouse.set_visible(False)

    def to_title(self):
        self.mouse_held = False
        self.state = "titulo"
        pygame.mouse.set_visible(True)
        self.start_stage(0, silent=True)
        self.audio.music(0)

    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if self.state in ("jogando", "pausa"):
                        self.hiscore = max(self.hiscore, self.score)
                        self.to_title()
                    else:
                        return False
                elif ev.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                elif ev.key == pygame.K_F3:
                    self.show_fps = not self.show_fps
                elif ev.key == pygame.K_F12:
                    pygame.image.save(self.view, os.path.join(AQUI, "captura_%d.png" % int(self.time * 1000)))
                elif ev.key == pygame.K_p and self.state in ("jogando", "pausa"):
                    self.state = "pausa" if self.state == "jogando" else "jogando"
                    pygame.mouse.set_visible(self.state == "pausa")
                elif ev.key in (pygame.K_RETURN, pygame.K_SPACE) and self.state == "titulo":
                    self.begin()
                elif ev.key == pygame.K_RETURN and self.state in ("game_over", "vitoria"):
                    self.to_title()
            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                self.mouse_held = False
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self.state == "jogando":
                    self.mouse_held = True
                    if self.fire_cd > 0.05:
                        self.fire_cd = 0.0
                elif self.state == "titulo":
                    self.begin()
                elif self.state == "vitoria" or (self.state == "game_over" and self.over_t > 2):
                    self.to_title()
        return True

    def run(self):
        while True:
            dt = min(self.clock.tick(60) / 1000.0, 1 / 30) * GAME_SPEED
            if not self.handle_events():
                break
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()

    def run_test(self, frames, outdir, shots_at):
        import time
        os.makedirs(outdir, exist_ok=True)
        for _ in range(90):
            self.update(1 / 60)
        self.draw()
        pygame.image.save(self.screen, os.path.join(outdir, "titulo.png"))
        self.begin()
        t0 = time.time()
        for f in range(frames):
            pygame.event.pump()
            if self.state == "game_over":
                self.lives, self.hp, self.state = 3, MAX_HP, "jogando"
            self.update(1 / 60)
            if f in shots_at or f == frames - 1:
                self.draw()
                pygame.image.save(self.screen, os.path.join(outdir, "f%05d_fase%d.png" % (f, self.stage_i + 1)))
        print("frames=%d tempo=%.1fs estado=%s fase=%d pontos=%d vidas=%d hp=%d chefe=%s" % (
            frames, time.time() - t0, self.state, self.stage_i + 1, self.score, self.lives, self.hp, bool(self.boss)))
        t0 = time.time()
        for _ in range(120):
            self.update(1 / 60)
            self.draw()
        print("desenho+update: %.1f ms/quadro" % ((time.time() - t0) / 120 * 1000))


def main():
    if os.environ.get("LAMINA_TESTE"):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        g = Game(test=True)
        frames = int(os.environ.get("LAMINA_FRAMES", "1800"))
        shots = {int(x) for x in os.environ.get("LAMINA_SHOTS", "300,900").split(",")}
        g.run_test(frames, os.environ.get("LAMINA_OUT", "capturas"), shots)
        return
    Game().run()


if __name__ == "__main__":
    main()
