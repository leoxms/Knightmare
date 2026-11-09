# -*- coding: utf-8 -*-
"""
Lamina da Aurora - tiro em primeira pessoa (pseudo-3D) feito com pygame.

Jogo original: personagens, fases, arte e som sao todos gerados por codigo.

Controles
  A / D  ou  <- / ->   andar para os lados (desviar)
  Mouse                mirar
  Clique / Espaco      atirar (segure)
  P                    pausa
  F                    tela cheia
  Esc                  sair
"""
import math
import os
import random
import sys

import numpy as np
import pygame

# ----------------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------------
TITLE = "Lâmina da Aurora"
W, H = 1280, 720
HORIZON = 330          # linha do horizonte na tela
FOCAL = 560.0          # distancia focal da projecao (pixels)
SEG = 2.0              # comprimento de um segmento de estrada (m)
DRAW_SEGS = 125
FAR = SEG * DRAW_SEGS  # distancia de desenho (m)
ROAD_W = 5.5           # meia largura da estrada (m)
CAM_H = 1.7            # altura dos olhos (m)
FWD_SPEED = 7.5        # velocidade de avanco (m/s) - ritmo de caminhada
STRAFE_SPEED = 6.5
SHOT_SPEED = 38.0
SPAWN_DIST = 110.0     # distancia em que os monstros aparecem
STAGE_LEN = float(os.environ.get("LAMINA_FASE", "650"))
MAX_HP = 6

STAGES = [
    dict(name="Via dos Ciprestes",
         sky=((10, 14, 40), (70, 70, 110)), fog=(64, 66, 102),
         grass=((30, 72, 44), (25, 62, 38)), rumble=((96, 84, 62), (66, 56, 44)),
         road=((96, 88, 74), (88, 80, 67)), lane=(160, 150, 118),
         mount=((48, 50, 92), (32, 34, 66)), scenery="floresta",
         ambient=(190, 255, 110), golem=(96, 112, 88), boss_tint=(90, 230, 120),
         enemies={"morcego": 5, "espectro": 2, "golem": 1}, boss_hp=70,
         curve=(22, 9), hill=3.0, moon=True, root=110.0, bpm=92),
    dict(name="Cavernas de Cristal",
         sky=((6, 4, 16), (34, 28, 64)), fog=(34, 30, 64),
         grass=((42, 38, 64), (36, 32, 56)), rumble=((96, 74, 150), (62, 50, 104)),
         road=((62, 58, 84), (56, 52, 77)), lane=(130, 190, 235),
         mount=((30, 24, 58), (20, 16, 42)), scenery="caverna",
         ambient=(120, 200, 255), golem=(98, 100, 136), boss_tint=(80, 170, 255),
         enemies={"morcego": 4, "espectro": 3, "golem": 2}, boss_hp=90,
         curve=(30, 12), hill=4.0, moon=False, root=98.0, bpm=80),
    dict(name="Cidadela Rubra",
         sky=((36, 6, 12), (170, 70, 46)), fog=(118, 52, 42),
         grass=((62, 32, 30), (54, 28, 26)), rumble=((142, 132, 122), (92, 86, 80)),
         road=((84, 76, 74), (77, 70, 68)), lane=(205, 165, 95),
         mount=((76, 22, 22), (48, 12, 14)), scenery="cidadela",
         ambient=(255, 150, 60), golem=(124, 92, 82), boss_tint=(255, 90, 50),
         enemies={"morcego": 3, "espectro": 3, "golem": 3}, boss_hp=120,
         curve=(26, 14), hill=4.5, moon=True, root=82.4, bpm=112),
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

SRCALPHA = pygame.SRCALPHA


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp_col(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def seg_dist2(ax, ay, az, bx, by, bz, px, py, pz):
    dx, dy, dz = bx - ax, by - ay, bz - az
    L = dx * dx + dy * dy + dz * dz
    t = 0.0 if L == 0 else clamp(((px - ax) * dx + (py - ay) * dy + (pz - az) * dz) / L, 0.0, 1.0)
    cx, cy, cz = ax + dx * t, ay + dy * t, az + dz * t
    return (px - cx) ** 2 + (py - cy) ** 2 + (pz - cz) ** 2


def wchoice(weights):
    tot = sum(weights.values())
    r = random.uniform(0, tot)
    for k, w in weights.items():
        r -= w
        if r <= 0:
            return k
    return k


class Ent:
    def __init__(self, **kw):
        self.dead = False
        self.__dict__.update(kw)


# ----------------------------------------------------------------------------
# Arte procedural
# ----------------------------------------------------------------------------
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
    a = (np.clip((d - 0.6) / 0.8, 0, 1) ** 1.5 * 210).astype(np.uint8)
    s = pygame.Surface((W, H), SRCALPHA)
    s.fill((0, 0, 0, 255))
    pa = pygame.surfarray.pixels_alpha(s)
    pa[:] = a.T
    del pa
    return s


def make_edge_glow(color):
    """Brilho nas bordas da tela (escudo / gelo), para BLEND_ADD."""
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


def thick_line(surf, color, p0, p1, w):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L * w / 2, dx / L * w / 2
    pygame.draw.polygon(surf, color, [(p0[0] + nx, p0[1] + ny), (p1[0] + nx, p1[1] + ny),
                                      (p1[0] - nx, p1[1] - ny), (p0[0] - nx, p0[1] - ny)])


def art_bat(frame):
    s = pygame.Surface((300, 180), SRCALPHA)
    cx, cy = 150, 90
    wing, dark = (72, 36, 98), (34, 14, 50)
    if frame == 0:
        L = [(cx - 15, cy - 10), (cx - 60, cy - 62), (cx - 110, cy - 78), (cx - 146, cy - 42),
             (cx - 116, cy - 32), (cx - 96, cy - 6), (cx - 66, cy - 16), (cx - 46, cy + 10), (cx - 20, cy + 16)]
    else:
        L = [(cx - 15, cy - 10), (cx - 60, cy - 16), (cx - 110, cy + 4), (cx - 146, cy + 52),
             (cx - 116, cy + 42), (cx - 96, cy + 62), (cx - 66, cy + 42), (cx - 46, cy + 46), (cx - 20, cy + 16)]
    R = [(2 * cx - x, y) for x, y in L]
    for poly in (L, R):
        pygame.draw.polygon(s, wing, poly)
        pygame.draw.polygon(s, dark, poly, 3)
        sh = poly[0]
        for j in (2, 4, 6):
            pygame.draw.line(s, dark, sh, poly[j], 3)
    pygame.draw.ellipse(s, (52, 26, 68), (cx - 22, cy - 28, 44, 66))
    pygame.draw.ellipse(s, (78, 46, 92), (cx - 12, cy - 8, 24, 38))
    for sx in (-1, 1):
        pygame.draw.polygon(s, (52, 26, 68), [(cx + sx * 16, cy - 38), (cx + sx * 11, cy - 70), (cx + sx * 2, cy - 44)])
    pygame.draw.circle(s, (56, 28, 72), (cx, cy - 32), 20)
    for sx in (-1, 1):
        pygame.draw.circle(s, (255, 60, 60), (cx + sx * 8, cy - 34), 6)
        pygame.draw.circle(s, (255, 220, 200), (cx + sx * 8 - 2, cy - 36), 2)
        pygame.draw.polygon(s, (240, 240, 240), [(cx + sx * 6, cy - 20), (cx + sx * 3, cy - 20), (cx + sx * 4, cy - 12)])
    return s


def art_wisp(frame, tint=(140, 255, 210)):
    s = pygame.Surface((220, 270), SRCALPHA)
    cx, cy = 110, 100
    sway = 18 if frame == 0 else -18
    tail = [(cx - 50, cy + 10), (cx - 30, cy + 80), (cx + sway - 10, cy + 130),
            (cx + sway, cy + 165), (cx + sway + 12, cy + 120), (cx + 34, cy + 70), (cx + 50, cy + 10)]
    pygame.draw.polygon(s, tint + (110,), tail)
    for r, a in ((100, 20), (84, 40), (68, 70), (54, 130), (42, 200), (30, 245)):
        c = lerp_col(tint, (255, 255, 255), 1 - r / 110)
        pygame.draw.circle(s, c + (a,), (cx, cy), r)
    pygame.draw.ellipse(s, (16, 8, 36, 255), (cx - 22, cy - 14, 15, 24))
    pygame.draw.ellipse(s, (16, 8, 36, 255), (cx + 7, cy - 14, 15, 24))
    pygame.draw.ellipse(s, (16, 8, 36, 255), (cx - 9, cy + 16, 18, 12 if frame == 0 else 7))
    return s


def art_golem(tint):
    s = pygame.Surface((240, 320), SRCALPHA)
    st = tint
    dk = lerp_col(tint, (0, 0, 0), 0.45)
    hi = lerp_col(tint, (255, 255, 255), 0.25)
    for r in ((58, 220, 48, 98), (134, 220, 48, 98)):
        pygame.draw.rect(s, dk, r, border_radius=12)
        pygame.draw.rect(s, st, (r[0] + 4, r[1], r[2] - 8, r[3] - 8), border_radius=10)
    pygame.draw.rect(s, dk, (36, 86, 168, 156), border_radius=34)
    pygame.draw.rect(s, st, (42, 90, 156, 144), border_radius=30)
    pygame.draw.rect(s, hi, (52, 96, 70, 40), border_radius=18)
    for r in ((2, 100, 48, 140), (190, 100, 48, 140)):
        pygame.draw.rect(s, dk, r, border_radius=20)
        pygame.draw.rect(s, st, (r[0] + 4, r[1] + 4, r[2] - 8, r[3] - 12), border_radius=18)
    pygame.draw.circle(s, dk, (26, 246), 28)
    pygame.draw.circle(s, st, (26, 242), 24)
    pygame.draw.circle(s, dk, (214, 246), 28)
    pygame.draw.circle(s, st, (214, 242), 24)
    pygame.draw.rect(s, dk, (82, 34, 76, 68), border_radius=18)
    pygame.draw.rect(s, st, (86, 38, 68, 60), border_radius=16)
    for pts in (((70, 150), (95, 180), (88, 210)), ((170, 120), (150, 150), (160, 175)), ((110, 50), (118, 70))):
        pygame.draw.lines(s, dk, False, pts, 3)
    for ex in (98, 128):
        pygame.draw.rect(s, (255, 160, 50), (ex, 60, 15, 9), border_radius=3)
        pygame.draw.rect(s, (255, 240, 180), (ex + 3, 62, 6, 4))
    pygame.draw.circle(s, (255, 140, 40), (120, 165), 22, 4)
    pygame.draw.line(s, (255, 140, 40), (120, 145), (120, 185), 3)
    pygame.draw.line(s, (255, 140, 40), (102, 165), (138, 165), 3)
    return s


def art_block(font):
    s = pygame.Surface((200, 200), SRCALPHA)
    pygame.draw.rect(s, (120, 80, 30), (0, 0, 200, 200), border_radius=16)
    pygame.draw.rect(s, (200, 150, 60), (10, 10, 180, 180), border_radius=12)
    pygame.draw.polygon(s, (240, 200, 110), [(10, 10), (190, 10), (174, 26), (26, 26), (26, 174), (10, 190)])
    pygame.draw.polygon(s, (150, 104, 40), [(190, 10), (190, 190), (10, 190), (26, 174), (174, 174), (174, 26)])
    pygame.draw.rect(s, (210, 160, 70), (26, 26, 148, 148))
    for p in ((18, 18), (182, 18), (18, 182), (182, 182)):
        pygame.draw.circle(s, (100, 66, 24), p, 5)
    q = font.render("?", True, (255, 230, 150))
    q2 = font.render("?", True, (96, 52, 14))
    r = q.get_rect(center=(100, 104))
    s.blit(q2, r.move(5, 5))
    s.blit(q, r)
    return s


def art_orb(color, icon):
    s = pygame.Surface((160, 160), SRCALPHA)
    c = (80, 80)
    for r, a in ((78, 40), (70, 90), (62, 170), (56, 230)):
        pygame.draw.circle(s, lerp_col(color, (0, 0, 0), 0.35 if r < 60 else 0) + (a,), c, r)
    pygame.draw.circle(s, lerp_col(color, (255, 255, 255), 0.5) + (255,), c, 56, 4)
    pygame.draw.ellipse(s, (255, 255, 255, 110), (44, 34, 40, 22))
    wc = (255, 255, 255)
    if icon == "coracao":
        pygame.draw.polygon(s, wc, heart_points(80, 84, 64))
    elif icon == "bomba":
        pygame.draw.circle(s, (30, 30, 36), (76, 90), 26)
        pygame.draw.circle(s, (90, 90, 100), (68, 82), 7)
        pygame.draw.line(s, (220, 200, 160), (92, 68), (106, 50), 5)
        pygame.draw.circle(s, (255, 240, 120), (108, 47), 8)
    elif icon == "gelo":
        for k in range(3):
            a = k * math.pi / 3
            dx, dy = math.cos(a) * 34, math.sin(a) * 34
            pygame.draw.line(s, wc, (80 - dx, 80 - dy), (80 + dx, 80 + dy), 5)
            for sg in (-1, 1):
                bx, by = 80 + sg * dx * 0.6, 80 + sg * dy * 0.6
                for t in (-0.6, 0.6):
                    b = a + (math.pi if sg < 0 else 0) + t + math.pi
                    pygame.draw.line(s, wc, (bx, by), (bx + math.cos(b) * 12, by + math.sin(b) * 12), 4)
    elif icon == "triplo":
        for a in (-0.5, 0, 0.5):
            ex, ey = 80 + math.sin(a) * 36, 80 - math.cos(a) * 36
            pygame.draw.line(s, wc, (80, 112), (ex, ey), 5)
            pygame.draw.circle(s, wc, (int(ex), int(ey)), 8)
    elif icon == "rajada":
        pygame.draw.polygon(s, wc, [(90, 34), (56, 88), (78, 88), (66, 128), (106, 70), (82, 70)])
    elif icon == "escudo":
        pygame.draw.polygon(s, wc, [(80, 38), (114, 50), (110, 92), (80, 122), (50, 92), (46, 50)])
        pygame.draw.polygon(s, color, [(80, 52), (100, 60), (98, 90), (80, 108), (62, 90), (60, 60)])
    elif icon == "tesouro":
        pygame.draw.polygon(s, wc, [(56, 66), (80, 40), (104, 66), (80, 118)])
        pygame.draw.polygon(s, color, [(66, 66), (80, 50), (94, 66), (80, 100)])
    return s


def art_tree(variant):
    s = pygame.Surface((320, 520), SRCALPHA)
    pygame.draw.rect(s, (60, 40, 28), (146, 360, 30, 160))
    pygame.draw.rect(s, (82, 56, 38), (146, 360, 10, 160))
    if variant == 0:
        for i in range(5):
            y = 40 + i * 66
            w = 52 + i * 26
            pygame.draw.polygon(s, (18, 52, 34), [(160, y - 30), (160 - w, y + 80), (160 + w, y + 80)])
            pygame.draw.polygon(s, (30, 78, 46), [(160, y - 30), (160 - w, y + 80), (160 - w * 0.2, y + 80)])
    else:
        for (x, y, r, c) in ((160, 200, 110, (22, 58, 36)), (100, 260, 80, (26, 66, 40)), (220, 250, 85, (20, 54, 34)),
                             (160, 130, 80, (30, 76, 46)), (120, 170, 60, (40, 92, 54)), (200, 300, 70, (24, 60, 38))):
            pygame.draw.circle(s, c, (x, y), r)
    return s


def art_crystal(variant):
    s = pygame.Surface((260, 420), SRCALPHA)
    rnd = random.Random(variant * 17 + 3)
    shards = [(130, 380, 40, 0)] + [(rnd.randint(40, 220), rnd.randint(140, 300), rnd.randint(18, 32),
                                      rnd.randint(-40, 40)) for _ in range(4)]
    shards.sort(key=lambda t: t[1])
    cols = [((110, 80, 210), (70, 50, 150)), ((80, 170, 235), (50, 110, 170))]
    for bx, h, w, lean in shards:
        c, d = cols[variant % 2] if rnd.random() < 0.7 else cols[1 - variant % 2]
        top = (bx + lean, 420 - h - 30)
        poly = [(bx - w, 420), (bx - w * 0.6 + lean, 420 - h), top, (bx + w * 0.6 + lean, 420 - h), (bx + w, 420)]
        pygame.draw.polygon(s, c, poly)
        pygame.draw.polygon(s, d, [top, (bx + w * 0.6 + lean, 420 - h), (bx + w, 420), (bx + lean * 0.3, 420)])
        pygame.draw.line(s, (230, 230, 255), (bx - w * 0.6 + lean, 420 - h), top, 3)
    return s


def art_pillar():
    s = pygame.Surface((180, 600), SRCALPHA)
    stn, dk = (122, 114, 108), (74, 68, 64)
    pygame.draw.rect(s, dk, (16, 540, 148, 60))
    pygame.draw.rect(s, stn, (22, 544, 136, 52))
    pygame.draw.rect(s, stn, (40, 90, 100, 452))
    pygame.draw.rect(s, (142, 134, 126), (40, 90, 26, 452))
    for y in range(110, 540, 36):
        pygame.draw.line(s, dk, (40, y), (140, y), 2)
        off = 50 if (y // 36) % 2 else 80
        pygame.draw.line(s, dk, (40 + off, y), (40 + off, y + 36), 2)
    pygame.draw.rect(s, dk, (16, 56, 148, 40))
    pygame.draw.rect(s, stn, (22, 60, 136, 32))
    for x in (16, 64, 112):
        pygame.draw.rect(s, stn, (x, 24, 36, 36))
    pygame.draw.polygon(s, (150, 22, 28), [(56, 100), (124, 100), (124, 300), (90, 272), (56, 300)])
    pygame.draw.polygon(s, (110, 14, 20), [(110, 100), (124, 100), (124, 300), (110, 288)])
    pygame.draw.circle(s, (220, 180, 70), (90, 170), 18, 4)
    pygame.draw.circle(s, (220, 180, 70), (90, 170), 6)
    return s


def art_rock(tint):
    s = pygame.Surface((200, 140), SRCALPHA)
    dk = lerp_col(tint, (0, 0, 0), 0.4)
    hi = lerp_col(tint, (255, 255, 255), 0.2)
    pygame.draw.ellipse(s, dk, (0, 30, 200, 110))
    pygame.draw.ellipse(s, tint, (10, 30, 170, 96))
    pygame.draw.ellipse(s, hi, (30, 38, 80, 40))
    pygame.draw.ellipse(s, dk, (110, 60, 70, 60))
    return s


def art_shadow():
    s = pygame.Surface((200, 80), SRCALPHA)
    for i in range(10):
        a = 14 + i * 9
        pygame.draw.ellipse(s, (0, 0, 0, a), (i * 8, i * 3, 200 - i * 16, 80 - i * 6))
    return s


def art_boss(tint):
    s = pygame.Surface((520, 520), SRCALPHA)
    c = (260, 260)
    pts = []
    for i in range(48):
        a = i / 48 * 2 * math.pi
        r = 252 if i % 2 == 0 else 196
        pts.append((c[0] + math.cos(a) * r, c[1] + math.sin(a) * r))
    pygame.draw.polygon(s, (34, 16, 34), pts)
    pygame.draw.polygon(s, lerp_col(tint, (0, 0, 0), 0.5), pts, 5)
    pygame.draw.circle(s, (86, 30, 52), c, 188)
    pygame.draw.circle(s, (120, 44, 70), c, 188, 10)
    pygame.draw.circle(s, (232, 222, 212), c, 160)
    rnd = random.Random(7)
    for _ in range(22):
        a = rnd.uniform(0, 2 * math.pi)
        p = (c[0] + math.cos(a) * 158, c[1] + math.sin(a) * 158)
        q = (c[0] + math.cos(a + rnd.uniform(-0.2, 0.2)) * 110, c[1] + math.sin(a + rnd.uniform(-0.2, 0.2)) * 110)
        pygame.draw.line(s, (190, 60, 70), p, q, 3)
    sh = pygame.Surface((520, 520), SRCALPHA)
    pygame.draw.circle(sh, (60, 20, 40, 90), (c[0], c[1] + 36), 160)
    pygame.draw.circle(sh, (0, 0, 0, 0), (c[0], c[1] - 24), 150)
    s.blit(sh, (0, 0))
    return s


def art_wand():
    s = pygame.Surface((480, 420), SRCALPHA)
    thick_line(s, (58, 36, 24), (340, 372), (92, 80), 24)
    thick_line(s, (108, 74, 50), (334, 362), (96, 84), 6)
    for t in (0.12, 0.55):
        x = 92 + (340 - 92) * t
        y = 80 + (372 - 80) * t
        pygame.draw.circle(s, (170, 140, 80), (int(x), int(y)), 15)
        pygame.draw.circle(s, (120, 96, 50), (int(x), int(y)), 15, 3)
    for dx in (-26, 0, 26):
        pygame.draw.line(s, (200, 160, 60), (100, 92), (88 + dx, 52), 6)
    pygame.draw.polygon(s, (120, 230, 255), [(88, 6), (120, 58), (92, 114), (60, 60)])
    pygame.draw.polygon(s, (70, 170, 230), [(88, 6), (92, 114), (60, 60)])
    pygame.draw.line(s, (240, 255, 255), (90, 18), (104, 58), 4)
    steel, dk, hi = (126, 134, 150), (68, 74, 90), (196, 204, 220)
    pygame.draw.polygon(s, steel, [(480, 420), (356, 420), (300, 336), (334, 274), (424, 264), (480, 306)])
    for a, b in (((470, 316), (360, 300)), ((476, 360), (336, 342)), ((470, 404), (350, 386))):
        pygame.draw.line(s, dk, a, b, 4)
        pygame.draw.line(s, hi, (a[0], a[1] - 4), (b[0], b[1] - 4), 2)
    fist = [(250, 304), (300, 262), (362, 278), (374, 332), (334, 380), (268, 366)]
    pygame.draw.polygon(s, steel, fist)
    pygame.draw.polygon(s, dk, fist, 4)
    for i in range(4):
        x = 268 + i * 22
        y = 300 - i * 10
        pygame.draw.circle(s, (166, 174, 192), (x, y), 15)
        pygame.draw.circle(s, dk, (x, y), 15, 3)
        pygame.draw.line(s, dk, (x - 8, y + 16), (x + 12, y + 50), 3)
    pygame.draw.polygon(s, (150, 158, 176), [(300, 262), (262, 246), (246, 262), (288, 292)])
    pygame.draw.polygon(s, dk, [(300, 262), (262, 246), (246, 262), (288, 292)], 3)
    for p in ((440, 290), (404, 330), (430, 380)):
        pygame.draw.circle(s, (210, 214, 224), p, 5)
    return s


# ----------------------------------------------------------------------------
# Texturas (numpy) e sombreamento
# ----------------------------------------------------------------------------
def tile_noise(size, cells, rnd):
    """Ruido de valor periodico (emenda sem costura), valores 0..1."""
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


def tex_via_romana(size=512, n_stones=70, seed=3):
    """Pavimento de basalto poligonal (via romana), periodico. Retorna (size,size,3) float32."""
    rnd = np.random.default_rng(seed)
    pts = rnd.random((n_stones, 2)) * size
    offs = np.array([(dx, dy) for dx in (-size, 0, size) for dy in (-size, 0, size)], dtype=float)
    allp = (pts[None, :, :] + offs[:, None, :]).reshape(-1, 2)
    cell_id = np.tile(np.arange(n_stones), 9)
    Y, X = np.mgrid[0:size, 0:size].astype(np.float32)
    q = np.column_stack([X.ravel(), Y.ravel()])
    try:
        from scipy.spatial import cKDTree
        dd, ii = cKDTree(allp).query(q, k=2)
    except ImportError:  # sem scipy: forca bruta em blocos
        dd = np.empty((len(q), 2))
        ii = np.empty((len(q), 2), int)
        for a in range(0, len(q), 8192):
            d = ((q[a:a + 8192, None, :] - allp[None]) ** 2).sum(-1)
            p = np.argsort(d, axis=1)[:, :2]
            ii[a:a + 8192] = p
            dd[a:a + 8192] = np.sqrt(np.take_along_axis(d, p, 1))
    d1 = dd[:, 0].reshape(size, size).astype(np.float32)
    d2 = dd[:, 1].reshape(size, size).astype(np.float32)
    idn = cell_id[ii[:, 0]].reshape(size, size)
    edge = d2 - d1
    base = rnd.uniform(0.75, 1.15, n_stones)
    warm = rnd.uniform(-0.08, 0.08, n_stones)
    b = base[idn]
    w = warm[idn]
    r = np.random.default_rng(seed + 1)
    rr = random.Random(seed)
    grain = fbm(size, rr, ((16, 0.4), (64, 0.35), (128, 0.25)))
    speck = r.random((size, size)) * 0.18
    bevel = np.clip(edge / 9.0, 0, 1) ** 0.6
    col = np.empty((size, size, 3), np.float32)
    stone = (b * (0.78 + 0.35 * grain) + speck - 0.09)
    col[..., 0] = stone * (104 + 40 * w)
    col[..., 1] = stone * (102 + 10 * w)
    col[..., 2] = stone * (100 - 30 * w)
    col *= (0.45 + 0.55 * bevel)[..., None]
    gap = edge < 2.2
    col[gap] = np.array([34, 30, 26], np.float32) * (0.8 + 0.4 * grain[gap])[:, None]
    # leve desgaste no centro de cada pedra (polimento)
    col *= (1.0 + 0.10 * np.clip(1 - d1 / 30, 0, 1))[..., None]
    return np.clip(col, 0, 255)


def tex_meio_fio(length=256, width=64, seed=5):
    """Blocos retangulares de calcario do meio-fio (v ao longo da via, u na largura)."""
    rr = random.Random(seed)
    g = fbm(length, rr, ((8, 0.5), (32, 0.3), (64, 0.2)))[:, :width]
    v = np.arange(length)[:, None]
    u = np.arange(width)[None, :]
    blk = (v // 64)
    base = np.array([rr.uniform(0.85, 1.1) for _ in range(length // 64 + 1)])[blk]
    col = np.empty((length, width, 3), np.float32)
    k = base * (0.8 + 0.35 * g)
    col[..., 0] = 196 * k
    col[..., 1] = 184 * k
    col[..., 2] = 160 * k
    joint = ((v % 64) < 3) | (u < 3) | (u > width - 4)
    col[np.broadcast_to(joint, (length, width))] *= 0.45
    top = np.clip(1.15 - u / width * 0.5, 0.7, 1.2)
    col *= np.broadcast_to(top, (length, width))[..., None]
    return np.clip(col, 0, 255)


def tex_terreno(kind, c1, c2, size=256, seed=9):
    rr = random.Random(seed)
    n = fbm(size, rr)
    n2 = fbm(size, rr, ((32, 0.5), (64, 0.3), (128, 0.2)))
    t = np.clip((n - 0.35) * 2.2, 0, 1)
    col = np.empty((size, size, 3), np.float32)
    for i in range(3):
        col[..., i] = c1[i] * (1 - t) + c2[i] * t
    col *= (0.75 + 0.5 * n2)[..., None]
    if kind == "grama":
        blades = np.random.default_rng(seed).random((size, size)) < 0.06
        col[blades] *= 1.35
    elif kind == "cascalho":
        pebbles = np.random.default_rng(seed).random((size, size)) < 0.12
        col[pebbles] = col[pebbles] * 0.6 + 70
    return np.clip(col, 0, 255)


def mips(tex, levels=5):
    out = [tex.astype(np.float32)]
    for _ in range(levels - 1):
        t = out[-1]
        h, w = t.shape[0] // 2 * 2, t.shape[1] // 2 * 2
        t = t[:h, :w]
        out.append((t[0::2, 0::2] + t[1::2, 0::2] + t[0::2, 1::2] + t[1::2, 1::2]) / 4)
    return out


def shade(surf, strength=0.35, noise=0.10, seed=1, light_dir=(-0.6, -1.0)):
    """Da volume a um sprite plano: luz de cima/esquerda, sombra nas bordas e ruido de material."""
    w, h = surf.get_size()
    a = pygame.surfarray.array_alpha(surf).astype(np.float32) / 255.0
    rgb = pygame.surfarray.array3d(surf).astype(np.float32)
    x = np.linspace(-1, 1, w)[:, None]
    y = np.linspace(-1, 1, h)[None, :]
    lit = 1.0 + strength * 0.5 * (-x - y)   # luz vinda de cima/esquerda
    # oclusao: escurece perto das bordas do alfa
    k = 9
    pad = np.pad(a, k, mode="constant")
    cs = pad.cumsum(0).cumsum(1)
    box = (cs[2 * k:, 2 * k:] - cs[:-2 * k, 2 * k:] - cs[2 * k:, :-2 * k] + cs[:-2 * k, :-2 * k]) / (2 * k) ** 2
    box = box[:w, :h]
    occ = 0.6 + 0.4 * np.clip(box, 0, 1) ** 2
    rr = np.random.default_rng(seed)
    nz = 1.0 + (rr.random((w, h)) - 0.5) * 2 * noise
    rr2 = random.Random(seed)
    big = fbm(max(w, h), rr2, ((8, 0.6), (24, 0.4)))[:w, :h]
    big = 0.92 + 0.16 * big
    rgb *= (lit * occ * nz * big)[..., None]
    out = surf.copy()
    pygame.surfarray.blit_array(out, np.clip(rgb, 0, 255).astype(np.uint8))
    pa = pygame.surfarray.pixels_alpha(out)
    pa[:] = (a * 255).astype(np.uint8)
    del pa
    return out


MARBLE = (226, 220, 204)
MARBLE_DK = (150, 144, 132)


def art_cypress(variant):
    s = pygame.Surface((180, 640), SRCALPHA)
    pygame.draw.rect(s, (70, 48, 32), (82, 560, 16, 80))
    rnd = random.Random(variant + 40)
    pts_l, pts_r = [], []
    for i in range(41):
        t = i / 40
        y = 20 + t * 560
        wdt = 72 * math.sin(math.pi * min(1, t * 1.15)) ** 0.8 * (0.6 + 0.4 * t)
        j = rnd.uniform(-5, 5)
        pts_l.append((90 - wdt + j, y))
        pts_r.append((90 + wdt + j, y))
    pygame.draw.polygon(s, (22, 50, 30), pts_l + pts_r[::-1])
    for _ in range(140):
        t = rnd.random()
        y = 30 + t * 540
        wdt = 60 * math.sin(math.pi * min(1, t * 1.15)) ** 0.8 * (0.6 + 0.4 * t)
        x = 90 + rnd.uniform(-wdt, wdt * 0.4)
        c = rnd.choice(((34, 72, 42), (28, 62, 36), (44, 86, 50)))
        pygame.draw.ellipse(s, c, (x - 9, y - 14, 18, 28))
    return shade(s, 0.4, 0.12, variant + 1)


def art_olive():
    s = pygame.Surface((360, 400), SRCALPHA)
    br = (84, 66, 50)
    thick_line(s, br, (180, 400), (170, 260), 34)
    thick_line(s, br, (172, 270), (110, 190), 18)
    thick_line(s, br, (174, 268), (240, 180), 20)
    thick_line(s, br, (170, 300), (200, 220), 14)
    rnd = random.Random(77)
    for _ in range(120):
        x = rnd.gauss(180, 80)
        y = rnd.gauss(160, 55)
        c = rnd.choice(((104, 122, 86), (88, 108, 74), (126, 140, 104), (74, 92, 64)))
        pygame.draw.ellipse(s, c, (x - 20, y - 12, 40, 24))
    return shade(s, 0.35, 0.10, 78)


def art_column(broken=False, seed=0):
    s = pygame.Surface((200, 640), SRCALPHA)
    rnd = random.Random(seed)
    # base (estilobato)
    pygame.draw.rect(s, MARBLE_DK, (6, 600, 188, 40))
    pygame.draw.rect(s, MARBLE, (10, 600, 180, 32))
    top = 90 if not broken else rnd.randint(250, 380)
    # fuste canelado com entase
    for x in range(0, 120):
        u = x / 119
        flute = 0.82 + 0.18 * abs(math.cos(u * math.pi * 10))
        light = 1.15 - 0.55 * u
        k = flute * light
        col = (min(255, int(MARBLE[0] * k)), min(255, int(MARBLE[1] * k)), min(255, int(MARBLE[2] * k)))
        pygame.draw.line(s, col, (40 + x, top + 6), (40 + x, 600))
    if broken:
        jag = [(40, top + 6)]
        for i in range(1, 8):
            jag.append((40 + i * 17, top + rnd.randint(-30, 20)))
        jag.append((160, top + 6))
        pygame.draw.polygon(s, (0, 0, 0, 0), jag + [(160, top - 60), (40, top - 60)])
        pygame.draw.lines(s, MARBLE_DK, False, jag, 4)
        for _ in range(4):
            x = rnd.randint(50, 150)
            pygame.draw.line(s, MARBLE_DK, (x, top + 20), (x + rnd.randint(-15, 15), top + rnd.randint(60, 140)), 2)
    else:
        pygame.draw.ellipse(s, MARBLE, (22, 60, 156, 44))       # equino
        pygame.draw.ellipse(s, MARBLE_DK, (22, 60, 156, 44), 3)
        pygame.draw.rect(s, MARBLE_DK, (8, 30, 184, 38))         # abaco
        pygame.draw.rect(s, MARBLE, (12, 30, 176, 32))
        pygame.draw.rect(s, MARBLE_DK, (36, 96, 128, 10))
    return shade(s, 0.3, 0.08, seed + 5)


def art_statue(seed=0):
    s = pygame.Surface((260, 640), SRCALPHA)
    pygame.draw.rect(s, MARBLE_DK, (30, 420, 200, 220))      # pedestal
    pygame.draw.rect(s, MARBLE, (36, 426, 188, 208))
    pygame.draw.rect(s, MARBLE_DK, (20, 410, 220, 22))
    pygame.draw.rect(s, MARBLE_DK, (20, 620, 220, 20))
    pygame.draw.rect(s, MARBLE_DK, (70, 480, 120, 60), 3)    # placa
    c, d = (210, 204, 190), (156, 150, 138)
    pygame.draw.polygon(s, c, [(96, 410), (164, 410), (156, 250), (104, 250)])   # tunica
    for x in range(108, 160, 10):
        pygame.draw.line(s, d, (x, 262), (x - 6 + (x % 3), 405), 2)               # dobras
    pygame.draw.polygon(s, c, [(104, 250), (156, 250), (150, 170), (110, 170)])  # torso
    pygame.draw.circle(s, c, (130, 146), 22)                                      # cabeca
    pygame.draw.polygon(s, d, [(110, 136), (130, 112), (150, 136), (146, 128), (114, 128)])  # elmo
    pygame.draw.polygon(s, c, [(150, 176), (196, 120), (204, 128), (158, 190)])  # braco erguido
    pygame.draw.line(s, d, (200, 40), (196, 330), 6)                              # lanca
    pygame.draw.polygon(s, d, [(200, 20), (208, 50), (192, 50)])
    pygame.draw.ellipse(s, c, (56, 190, 64, 110))                                 # escudo
    pygame.draw.ellipse(s, d, (56, 190, 64, 110), 4)
    pygame.draw.circle(s, d, (88, 245), 10)
    return shade(s, 0.35, 0.08, seed + 11)


def art_brazier():
    s = pygame.Surface((200, 300), SRCALPHA)
    bz, dk = (176, 120, 60), (100, 64, 30)
    for a, b in (((100, 120), (30, 300)), ((100, 120), (170, 300)), ((100, 120), (100, 300))):
        thick_line(s, dk, a, b, 10)
    pygame.draw.ellipse(s, dk, (20, 70, 160, 70))
    pygame.draw.polygon(s, bz, [(24, 96), (176, 96), (150, 150), (50, 150)])
    pygame.draw.ellipse(s, (210, 160, 90), (20, 80, 160, 34))
    pygame.draw.ellipse(s, (60, 30, 20), (32, 84, 136, 24))
    for x in range(50, 160, 22):
        pygame.draw.line(s, dk, (x, 104), (x + 4, 146), 3)
    return shade(s, 0.35, 0.08, 31)


def art_milestone():
    s = pygame.Surface((120, 260), SRCALPHA)
    pygame.draw.rect(s, MARBLE_DK, (10, 230, 100, 30))
    pygame.draw.rect(s, MARBLE, (24, 40, 72, 196), border_radius=30)
    for i, y in enumerate((90, 120, 150)):
        pygame.draw.line(s, MARBLE_DK, (36, y), (84, y), 4)
    return shade(s, 0.35, 0.1, 51)


def make_sky(top, bottom, stars, seed):
    s = pygame.Surface((W, HORIZON + 160))
    hh = s.get_height()
    for y in range(hh):
        t = (y / hh) ** 1.2
        pygame.draw.line(s, lerp_col(top, bottom, t), (0, y), (W, y))
    if stars:
        rnd = random.Random(seed)
        for _ in range(220):
            x, y = rnd.randint(0, W), rnd.randint(0, int(HORIZON * 0.8))
            b = rnd.randint(110, 255)
            s.set_at((x, y), (b, b, min(255, b + 20)))
            if rnd.random() < 0.08:
                pygame.draw.circle(s, (b, b, b), (x, y), 1)
    return s.convert()


def make_mountains(width, base, amp, color, seed, jag=1.0, flip=False):
    rnd = random.Random(seed)
    hh = H
    s = pygame.Surface((width, hh), SRCALPHA)
    ph = [rnd.uniform(0, 6.28) for _ in range(5)]
    pts = [(0, hh)]
    for x in range(0, width + 1, 6):
        t = x / width * 2 * math.pi
        v = (0.5 + 0.25 * math.sin(t * 2 + ph[0]) + 0.15 * math.sin(t * 5 + ph[1])
             + 0.08 * jag * math.sin(t * 13 + ph[2]) + 0.05 * jag * math.sin(t * 29 + ph[3])
             + 0.03 * jag * math.sin(t * 61 + ph[4]))
        pts.append((x, base - amp * v))
    pts.append((width, hh))
    pygame.draw.polygon(s, color, pts)
    if flip:
        s = pygame.transform.flip(s, False, True)
    return s.convert_alpha()


# ----------------------------------------------------------------------------
# Audio sintetizado
# ----------------------------------------------------------------------------
class Audio:
    def __init__(self):
        self.ok = False
        self.snd = {}
        self.musics = {}
        self.music_ch = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 512)
            self.sr, _, self.ch = pygame.mixer.get_init()
            pygame.mixer.set_num_channels(24)
            self.ok = True
            self.build()
        except Exception as e:  # sem placa de som: segue mudo
            print("audio desativado:", e)
            self.ok = False

    def to_sound(self, mono, vol=0.8):
        peak = float(np.max(np.abs(mono))) or 1.0
        mono = np.clip(mono / peak, -1, 1)          # normaliza: todo som sai com volume cheio
        a = (mono * 32767 * vol).astype(np.int16)
        if self.ch == 2:
            a = np.column_stack([a, a])
        return pygame.sndarray.make_sound(np.ascontiguousarray(a))

    def build(self):
        sr = self.sr

        def tt(d):
            return np.arange(int(sr * d)) / sr

        def sweep(f0, f1, d, wave="sine"):
            t = tt(d)
            f = np.linspace(f0, f1, len(t))
            ph = 2 * np.pi * np.cumsum(f) / sr
            if wave == "square":
                return np.sign(np.sin(ph)) * 0.6
            if wave == "saw":
                return 2 * ((ph / (2 * np.pi)) % 1) - 1
            return np.sin(ph)

        def env(n, attack=0.004, decay=6.0):
            t = np.arange(n) / sr
            e = np.exp(-t * decay)
            a = int(sr * attack)
            if a > 0:
                e[:a] *= np.linspace(0, 1, a)
            return e

        def noise(d, k=1):
            x = np.random.uniform(-1, 1, int(sr * d))
            if k > 1:
                x = np.convolve(x, np.ones(k) / k, mode="same")
            return x

        x = sweep(1500, 360, 0.16, "square")
        self.snd["tiro"] = self.to_sound(x * env(len(x), decay=22) * 0.28)
        x = noise(0.12, 4) * 0.6 + sweep(420, 140, 0.12) * 0.4
        self.snd["acerto"] = self.to_sound(x * env(len(x), decay=30) * 0.7)
        x = noise(0.8, 18) * 1.6 + sweep(120, 36, 0.8) * 0.6
        self.snd["explosao"] = self.to_sound(x * env(len(x), decay=5) * 0.8)
        x = noise(1.4, 26) * 2.0 + sweep(90, 30, 1.4) * 0.8
        self.snd["bomba"] = self.to_sound(x * env(len(x), decay=2.6) * 0.9)
        parts = []
        for f in (660, 880, 1320):
            y = np.sin(2 * np.pi * f * tt(0.09))
            parts.append(y * env(len(y), decay=14))
        x = np.concatenate(parts)
        self.snd["item"] = self.to_sound(x * 0.5)
        x = sweep(300, 70, 0.4, "saw")
        self.snd["dano"] = self.to_sound(x * env(len(x), decay=7) * 0.5)
        x = sweep(800, 1500, 0.22)
        self.snd["escudo"] = self.to_sound(x * env(len(x), decay=9) * 0.5)
        x = sweep(880, 640, 0.07, "square")
        self.snd["bloco"] = self.to_sound(x * env(len(x), decay=40) * 0.3)
        x = np.convolve(sweep(70, 44, 1.8, "saw"), np.ones(8) / 8, mode="same")
        self.snd["chefe"] = self.to_sound(x * env(len(x), attack=0.25, decay=1.4) * 0.9)
        x = sweep(500, 200, 0.18, "square")
        self.snd["inimigo_tiro"] = self.to_sound(x * env(len(x), decay=16) * 0.16)

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
            pad = np.zeros(L)
            for iv in tri:
                f = root * 2 * 2 ** ((r + iv) / 12)
                pad += np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.004 * t)
            out[start:start + L] += pad * e * 0.05
            fb = root * 2 ** (r / 12) / 2 if r > 6 else root * 2 ** (r / 12)
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
                tri_w = 2 * np.abs(2 * ((f * t2) % 1) - 1) - 1
                out[s0:s0 + Ln] += tri_w * np.exp(-t2 * 6) * 0.045
        return self.to_sound(out, 0.9)

    def music(self, stage):
        if not self.ok:
            return
        if stage not in self.musics:
            st = STAGES[stage]
            self.musics[stage] = self.make_music(st["root"], st["bpm"])
        if self.music_ch:
            self.music_ch.stop()
        self.music_ch = self.musics[stage].play(loops=-1)
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
        flags = 0 if test else pygame.SCALED
        self.screen = pygame.display.set_mode((W, H), flags)
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
        self.build_art()
        self.cache = {}
        self.base_mips = {}
        self.glow_cache = {}
        self.glow_base = {}
        self.hiscore = 0
        self.show_fps = False
        self.aim_pos = (W // 2, HORIZON + 40)
        self.firing = False
        self.reset_game()
        self.start_stage(0, silent=True)
        self.state = "titulo"
        self.audio.music(0)

    # ------------------------------------------------------------- arte
    def build_art(self):
        b = {}
        b["bat0"], b["bat1"] = art_bat(0), art_bat(1)
        b["wisp0"], b["wisp1"] = art_wisp(0), art_wisp(1)
        b["fogo0"], b["fogo1"] = art_wisp(0, (255, 150, 60)), art_wisp(1, (255, 150, 60))
        b["block"] = art_block(pygame.font.SysFont("georgia", 150, bold=True))
        hit = b["block"].copy()
        hit.fill((90, 90, 90), special_flags=pygame.BLEND_RGB_ADD)
        b["block_hit"] = hit
        for k, (c, _, _) in ITEMS.items():
            b["item_" + k] = art_orb(c, k)
        b["tree0"], b["tree1"] = art_tree(0), art_tree(1)
        b["crystal0"], b["crystal1"] = art_crystal(0), art_crystal(1)
        b["pillar"] = shade(art_pillar(), 0.3, 0.08, 3)
        b["sombra"] = art_shadow()
        b["cipreste0"], b["cipreste1"] = art_cypress(0), art_cypress(1)
        b["oliveira"] = art_olive()
        b["coluna"] = art_column(False, 1)
        b["coluna_q0"], b["coluna_q1"] = art_column(True, 2), art_column(True, 3)
        b["estatua"] = art_statue(4)
        b["braseiro"] = art_brazier()
        b["marco"] = art_milestone()
        b["block"] = shade(b["block"], 0.3, 0.08, 6)
        b["block_hit"] = shade(b["block_hit"], 0.2, 0.05, 6)
        b["tree0"], b["tree1"] = shade(b["tree0"], 0.4, 0.12, 7), shade(b["tree1"], 0.4, 0.12, 8)
        b["crystal0"], b["crystal1"] = shade(b["crystal0"], 0.3, 0.05, 9), shade(b["crystal1"], 0.3, 0.05, 10)
        b["bat0"], b["bat1"] = shade(b["bat0"], 0.4, 0.08, 12), shade(b["bat1"], 0.4, 0.08, 12)
        for i, st in enumerate(STAGES):
            b["golem%d" % i] = shade(art_golem(st["golem"]), 0.45, 0.14, 20 + i)
            b["rock%d" % i] = shade(art_rock(lerp_col(st["golem"], st["grass"][0], 0.3)), 0.4, 0.14, 30 + i)
            b["boss%d" % i] = shade(art_boss(st["boss_tint"]), 0.35, 0.06, 40 + i)
        self.base = {k: v.convert_alpha() for k, v in b.items()}
        # texturas do chao (projecao de piso)
        road = tex_via_romana()
        curb = tex_meio_fio()
        self.floor = []
        terr = [("grama", (52, 84, 40), (96, 98, 60), (1.0, 1.0, 1.0)),
                ("cascalho", (44, 40, 58), (70, 64, 86), (0.72, 0.74, 0.92)),
                ("cascalho", (104, 66, 50), (146, 104, 72), (1.06, 0.92, 0.86))]
        for i, (kind, c1, c2, tint) in enumerate(terr):
            t = np.array(tint, np.float32)
            self.floor.append(dict(road=mips(road * t), curb=(curb * t).astype(np.float32),
                                   ground=mips(tex_terreno(kind, c1, c2, seed=60 + i))))
        self.floor_small = pygame.Surface((W // 2, (H - HORIZON) // 2)).convert()
        self.floor_big = pygame.Surface((W, H - HORIZON)).convert()
        self.wand = art_wand().convert_alpha()
        self.vignette = make_vignette().convert_alpha()
        self.edge_shield = make_edge_glow((40, 150, 90))
        self.edge_ice = make_edge_glow((40, 90, 160))
        self.heart_full = pygame.Surface((38, 36), SRCALPHA)
        pygame.draw.polygon(self.heart_full, (120, 10, 30), heart_points(19, 19, 36))
        pygame.draw.polygon(self.heart_full, (235, 45, 75), heart_points(19, 18, 31))
        pygame.draw.circle(self.heart_full, (255, 170, 180), (12, 12), 4)
        self.heart_empty = pygame.Surface((38, 36), SRCALPHA)
        pygame.draw.polygon(self.heart_empty, (90, 30, 45), heart_points(19, 18, 33), 3)
        self.bg = []
        for i, st in enumerate(STAGES):
            fog = st["fog"]
            d = dict(sky=make_sky(st["sky"][0], fog, st["moon"] or i == 1, i))
            d["m1"] = make_mountains(W * 2, HORIZON + 6, 150, lerp_col(st["mount"][0], fog, 0.45), i * 3 + 1)
            d["m2"] = make_mountains(W * 2, HORIZON + 14, 90, lerp_col(st["mount"][1], fog, 0.2), i * 3 + 2, jag=1.6)
            if i == 1:
                d["c1"] = make_mountains(W * 2, H - 120, 260, lerp_col(st["mount"][0], fog, 0.3), 51, jag=3.0, flip=True)
                d["c2"] = make_mountains(W * 2, H - 60, 200, (14, 10, 30), 52, jag=3.5, flip=True)
            self.bg.append(d)

    def scaled(self, key, h, flip=False):
        # tamanhos quantizados em passos de ~3,5%: reaproveita o cache enquanto o objeto se aproxima
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

    # ------------------------------------------------------- projecao
    def cx(self, z):
        A, B = self.st["curve"]
        return A * math.sin(z / 110.0) + B * math.sin(z / 47.0 + 1.3)

    def dcx(self, z):
        A, B = self.st["curve"]
        return A / 110.0 * math.cos(z / 110.0) + B / 47.0 * math.cos(z / 47.0 + 1.3)

    def d2cx(self, z):
        A, B = self.st["curve"]
        return -A / 12100.0 * math.sin(z / 110.0) - B / 2209.0 * math.sin(z / 47.0 + 1.3)

    def cy(self, z):
        return self.st["hill"] * math.sin(z / 71.0) + 0.4 * self.st["hill"] * math.sin(z / 29.0 + 2.0)

    def dcy(self, z):
        h = self.st["hill"]
        return h / 71.0 * math.cos(z / 71.0) + 0.4 * h / 29.0 * math.cos(z / 29.0 + 2.0)

    def warp_x(self, z):
        c = self.cam_z
        return self.cx(z) - self._cxc - self._dcxc * (z - c)

    def warp_y(self, z):
        return 0.0   # estrada plana: o chao e texturizado por projecao de piso

    def warp_x_np(self, z):
        A, B = self.st["curve"]
        c = self.cam_z
        cx = A * np.sin(z / 110.0) + B * np.sin(z / 47.0 + 1.3)
        return cx - self._cxc - self._dcxc * (z - c)

    def proj(self, x, y, z):
        dz = z - self.cam_z
        if dz < 0.2:
            return None
        s = FOCAL / dz
        sx = W / 2 + (x + self.warp_x(z) - self.cam_x) * s
        sy = HORIZON - (y + self.warp_y(z) - self.cam_y) * s
        return sx, sy, s

    def update_camera_terms(self):
        c = self.cam_z
        self._cxc, self._dcxc = self.cx(c), self.dcx(c)
        self._cyc, self._dcyc = self.cy(c), self.dcy(c)

    # ------------------------------------------------------ estado de jogo
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
        self.cam_y = CAM_H
        self.px = 0.0
        self.pvx = 0.0
        self.walk = 0.0
        self.bg_off = 0.0
        self.enemies, self.shots, self.fireballs = [], [], []
        self.items, self.blocks, self.parts = [], [], []
        self.boss = None
        self.boss_spawned = False
        self.spawn_t = 3.0
        self.next_block_z = 70.0
        self.fire_cd = 0.0
        self.recoil = 0.0
        self.invul = 2.0
        self.shake = 0.0
        self.red_flash = 0.0
        self.white_flash = 0.0
        self.msg = None
        self.popups = []
        self.scen_cache = {}
        self.seg_clip = {}
        self.target_lock = False
        self.time = 0.0
        self.ambient = [self.new_ambient(random.uniform(2, FAR * 0.4)) for _ in range(60)]
        self.update_camera_terms()
        if not silent:
            self.message("Fase %d" % (i + 1), self.st["name"], 3.5)
            self.audio.music(i)

    def message(self, title, sub="", dur=2.5):
        self.msg = [title, sub, dur, dur]

    def popup(self, text, color):
        self.popups.append([text, color, 1.6])

    def progress(self):
        return clamp(self.cam_z / STAGE_LEN, 0, 1)

    # ----------------------------------------------------------- cenario
    def scenery_for(self, n):
        objs = self.scen_cache.get(n)
        if objs is not None:
            return objs
        rnd = random.Random(n * 7919 + self.stage_i * 104729)
        objs = []
        kind = self.st["scenery"]
        z0 = n * SEG
        rock = "rock%d" % self.stage_i
        if kind == "floresta":
            table = [("cipreste0", 8.5, 0.30), ("cipreste1", 7.5, 0.22), ("oliveira", 4.5, 0.2),
                     ("coluna_q0", 4.2, 0.09), ("coluna_q1", 3.6, 0.07), ("estatua", 5.5, 0.04), (rock, 1.1, 0.08)]
        elif kind == "caverna":
            table = [("crystal0", 4.8, 0.4), ("crystal1", 3.2, 0.3), ("coluna_q0", 4.0, 0.12),
                     ("coluna_q1", 3.4, 0.08), (rock, 1.2, 0.1)]
        else:
            table = [("estatua", 5.5, 0.25), ("coluna_q0", 4.2, 0.2), ("cipreste0", 8.0, 0.25), (rock, 1.3, 0.3)]
        if kind == "cidadela":
            if n % 6 == 0:
                for side in (-1, 1):
                    objs.append((side * (ROAD_W + 1.5), z0, "coluna", 7.0, False, None))
            elif n % 6 == 3:
                for side in (-1, 1):
                    objs.append((side * (ROAD_W + 1.2), z0, "braseiro", 1.6, False, "fogo"))
        if kind == "floresta" and n % 25 == 0:
            objs.append((ROAD_W + 0.9, z0, "marco", 1.3, False, None))
        for side in (-1, 1):
            if rnd.random() < (0.5 if kind != "cidadela" else 0.2):
                k = rnd.choices([t[0] for t in table], [t[2] for t in table])[0]
                hgt = [t[1] for t in table if t[0] == k][0] * rnd.uniform(0.8, 1.25)
                x = side * (ROAD_W + 1.6 + rnd.random() * 7)
                extra = "cristal" if k.startswith("crystal") else None
                objs.append((x, z0 + rnd.random() * SEG, k, hgt, rnd.random() < 0.5, extra))
        if rnd.random() < 0.35:
            k = rnd.choices([t[0] for t in table], [t[2] for t in table])[0]
            hgt = [t[1] for t in table if t[0] == k][0] * rnd.uniform(1.0, 1.6)
            side = rnd.choice((-1, 1))
            objs.append((side * (ROAD_W + 10 + rnd.random() * 18), z0, k, hgt, rnd.random() < 0.5,
                         "cristal" if k.startswith("crystal") else None))
        self.scen_cache[n] = objs
        return objs

    def new_ambient(self, dz=None):
        if dz is None:
            dz = random.uniform(FAR * 0.25, FAR * 0.45)
        return [self.px + random.uniform(-16, 16), random.uniform(0.3, 4.5), self.cam_z + dz,
                random.uniform(0, 6.28), random.uniform(-0.4, 0.4)]

    # --------------------------------------------------------- entidades
    def make_enemy(self, kind, x, z):
        if kind == "morcego":
            by = random.uniform(1.3, 3.0)
            return Ent(kind=kind, x=x, bx=x, y=by, by=by, cy=by, z=z, hp=1, r=1.0, v=random.uniform(3.5, 5.0),
                       t=0.0, ph=random.uniform(0, 6.28), amp=random.uniform(0.8, 2.2), vzw=0.0, flash=0.0,
                       score=100, h=1.3, cd=0.0)
        if kind == "espectro":
            by = random.uniform(1.8, 3.2)
            return Ent(kind=kind, x=x, bx=x, y=by, by=by, cy=by, z=z, hp=3, r=0.95, v=2.5, t=0.0,
                       ph=random.uniform(0, 6.28), hold=random.uniform(18, 28), hold_t=random.uniform(3.5, 5.5),
                       vzw=0.0, flash=0.0, score=250, h=2.0, cd=random.uniform(0.8, 1.6))
        return Ent(kind="golem", x=x, bx=x, y=0.0, cy=1.6, z=z, hp=6 + self.stage_i, r=1.3, v=1.2, t=0.0,
                   ph=0.0, vzw=0.0, flash=0.0, score=400, h=3.4, cd=random.uniform(1.5, 2.5))

    def spawn(self, dt):
        if self.boss_spawned:
            return
        p = self.progress()
        if self.next_block_z - self.cam_z < SPAWN_DIST * 1.1 and p < 0.96:
            self.blocks.append(Ent(x=random.uniform(-ROAD_W + 1.3, ROAD_W - 1.3), y=1.8, cy=1.8,
                                   z=self.next_block_z, hp=4 + self.stage_i, r=0.95, flash=0.0, vzw=0.0,
                                   t=random.uniform(0, 6)))
            self.next_block_z += random.uniform(35, 55)
        self.spawn_t -= dt
        if self.spawn_t > 0 or p > 0.97:
            return
        self.spawn_t = max(1.4, 3.6 - 0.4 * self.stage_i - 1.0 * p) * random.uniform(0.8, 1.2)
        kind = wchoice(self.st["enemies"])
        z = self.cam_z + SPAWN_DIST
        if kind == "morcego":
            pat = random.choice(("linha", "v", "fila"))
            n = random.randint(3, 5)
            for i in range(n):
                off = i - (n - 1) / 2
                if pat == "linha":
                    x, zz = off * 2.2, z
                elif pat == "v":
                    x, zz = off * 2.0, z + abs(off) * 5
                else:
                    x, zz = random.uniform(-3, 3), z + i * 7
                self.enemies.append(self.make_enemy(kind, x, zz))
        elif kind == "espectro":
            for i in range(random.randint(1, 2)):
                self.enemies.append(self.make_enemy(kind, random.uniform(-3.5, 3.5), z + i * 10))
        else:
            self.enemies.append(self.make_enemy(kind, random.uniform(-3.5, 3.5), z))

    def enemy_fire(self, x, y, z, speed=11.0, kind="fogo", aim_dx=0.0, aim_dy=0.0):
        dz = z - self.cam_z
        if dz < 4:
            return
        T = dz / (speed + FWD_SPEED)
        tx = self.px + aim_dx
        ty = self.cam_y - 0.3 + aim_dy
        self.fireballs.append(Ent(x=x, y=y, cy=y, z=z, vx=(tx - x) / T, vy=(ty - y) / T, vz=-speed, kind=kind,
                                  r=0.55, vzw=-speed, t=0.0))

    def spawn_boss(self):
        self.boss_spawned = True
        hp = self.st["boss_hp"]
        self.boss = Ent(x=0.0, y=3.2, cy=3.2, z=self.cam_z + 100, dist=100.0, hp=hp, maxhp=hp, t=0.0, cd=3.0,
                        summon=8.0, flash=0.0, r=2.5, dying=False, dying_t=0.0, vzw=FWD_SPEED, pattern=0)
        self.message("O Guardião desperta!", "Acerte o olho ancestral", 3.0)
        self.audio.play("chefe")

    # ---------------------------------------------------------- tiros
    def aim(self):
        if not self.test:
            self.aim_pos = pygame.mouse.get_pos()
        return self.aim_pos

    def targets(self):
        t = [e for e in self.enemies if not e.dead] + [b for b in self.blocks if not b.dead]
        t += [f for f in self.fireballs if not f.dead]
        if self.boss and not self.boss.dying:
            t.append(self.boss)
        return t

    def pick_target(self, mx, my):
        best, bd = None, 1e9
        for o in self.targets():
            dz = o.z - self.cam_z
            if dz < 3 or dz > FAR * 0.85:
                continue
            p = self.proj(o.x, o.cy, o.z)
            if not p:
                continue
            rad = max(26, o.r * p[2])
            d = math.hypot(p[0] - mx, p[1] - my)
            if d < rad * 1.25 + 18 and d < bd:
                best, bd = o, d
        return best

    def fire(self):
        mx, my = self.aim()
        # o projetil nasce exatamente no cristal do cajado
        tipx, tipy = getattr(self, "tip_screen", (W - 382, H - 340))
        d0 = 1.2
        sx0 = self.cam_x + (tipx - W / 2) * d0 / FOCAL
        sy0 = self.cam_y + (HORIZON - tipy) * d0 / FOCAL
        sz0 = self.cam_z + d0
        tgt = self.pick_target(mx, my)
        if tgt is not None:
            vz = tgt.vzw
            t = max(0.01, (tgt.z - sz0) / (SHOT_SPEED - vz))
            tx, ty, tz = tgt.x, tgt.cy, tgt.z + vz * t
        else:
            d = 40.0
            tz = self.cam_z + d
            tx = self.cam_x + (mx - W / 2) / FOCAL * d - self.warp_x(tz)
            ty = self.cam_y + (HORIZON - my) / FOCAL * d - self.warp_y(tz)
        angles = (-0.07, 0.0, 0.07) if self.powers["triplo"] > 0 else (0.0,)
        for a in angles:
            dx, dy, dz = tx - sx0, ty - sy0, tz - sz0
            ca, sa = math.cos(a), math.sin(a)
            dx, dz = dx * ca + dz * sa, -dx * sa + dz * ca
            n = math.sqrt(dx * dx + dy * dy + dz * dz) or 1
            self.shots.append(Ent(x=sx0, y=sy0, z=sz0, vx=dx / n * SHOT_SPEED, vy=dy / n * SHOT_SPEED,
                                  vz=dz / n * SHOT_SPEED, life=3.5, dmg=1, t=0.0))
        self.recoil = 1.0
        self.muzzle = 0.12
        self.audio.play("tiro", 0.45)

    # ------------------------------------------------------------ efeitos
    def explode(self, x, y, z, color, n=26, power=6.0, size=0.22):
        if len(self.parts) > 650:
            n = n // 3
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            b = random.uniform(-1, 1)
            sp = power * random.uniform(0.3, 1.0)
            r = math.sqrt(1 - b * b)
            self.parts.append(Ent(x=x, y=y, z=z, vx=math.cos(a) * r * sp, vy=b * sp + 2, vz=math.sin(a) * r * sp,
                                  life=random.uniform(0.4, 1.0), max=1.0, color=color, size=size, grav=True))
        self.parts.append(Ent(x=x, y=y, z=z, vx=0, vy=0, vz=0, life=0.3, max=0.3, color=(255, 230, 190),
                              size=size * 9, grav=False))

    def sparks(self, x, y, z, color, n=6):
        for _ in range(n):
            self.parts.append(Ent(x=x, y=y, z=z, vx=random.uniform(-4, 4), vy=random.uniform(-1, 5),
                                  vz=random.uniform(-4, 4), life=random.uniform(0.15, 0.35), max=0.35, color=color,
                                  size=0.12, grav=True))

    def hurt(self):
        if self.invul > 0 or self.state != "jogando":
            return
        if self.powers["escudo"] > 0:
            self.shield_hits -= 1
            self.invul = 0.6
            self.audio.play("escudo")
            self.popup("Escudo!", (140, 255, 180))
            if self.shield_hits <= 0:
                self.powers["escudo"] = 0
            return
        self.hp -= 1
        self.invul = 1.4
        self.shake = 0.45
        self.red_flash = 0.55
        self.audio.play("dano")
        if self.hp <= 0:
            self.lives -= 1
            if self.lives <= 0:
                self.state = "game_over"
                self.over_t = 0.0
                self.hiscore = max(self.hiscore, self.score)
                self.audio.play("explosao")
                return
            self.hp = MAX_HP
            self.invul = 3.0
            for f in self.fireballs:
                f.dead = True
            self.message("Você caiu!", "Vidas restantes: %d" % self.lives, 2.5)

    def kill_enemy(self, e):
        e.dead = True
        self.score += e.score
        col = {"morcego": (190, 90, 255), "espectro": (120, 255, 200), "golem": (255, 150, 50)}[e.kind]
        self.explode(e.x, e.cy, e.z, col, n=30 if e.kind != "golem" else 50, power=7 if e.kind != "golem" else 9)
        self.audio.play("explosao", 0.6)

    def damage(self, o, dmg):
        if o is self.boss:
            o.hp -= dmg
            o.flash = 0.07
            self.sparks(o.x + random.uniform(-1, 1), o.cy + random.uniform(-1, 1), o.z - 2.0, (255, 220, 160), 5)
            self.audio.play("acerto", 0.45)
            if o.hp <= 0 and not o.dying:
                o.dying = True
                o.dying_t = 0.0
                self.score += 5000 * (self.stage_i + 1)
                for e in self.enemies:
                    e.dead = True
                for f in self.fireballs:
                    f.dead = True
            return
        if o in self.blocks:
            o.hp -= 1
            o.flash = 0.08
            self.audio.play("bloco", 0.7)
            self.sparks(o.x, o.cy, o.z - 0.7, (255, 210, 110), 5)
            if o.hp <= 0:
                o.dead = True
                self.score += 50
                kind = random.choices(list(ITEMS), [v[2] for v in ITEMS.values()])[0]
                self.items.append(Ent(kind=kind, x=o.x, y=1.3, cy=1.3, z=o.z, t=0.0))
                self.explode(o.x, o.cy, o.z, (255, 200, 90), n=22, power=5)
                self.audio.play("explosao", 0.4)
            return
        if o in self.fireballs:
            o.dead = True
            self.score += 10
            self.explode(o.x, o.y, o.z, (255, 150, 60), n=10, power=4, size=0.15)
            return
        o.hp -= dmg
        o.flash = 0.08
        self.audio.play("acerto", 0.5)
        self.sparks(o.x, o.cy, o.z - 0.6, (255, 255, 220), 4)
        if o.hp <= 0:
            self.kill_enemy(o)

    def collect(self, it):
        it.dead = True
        c, name, _ = ITEMS[it.kind]
        self.popup("+ " + name, c)
        self.audio.play("item")
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
                if not e.dead and e.z - self.cam_z < FAR * 0.9:
                    self.kill_enemy(e)
            for f in self.fireballs:
                f.dead = True
            if self.boss and not self.boss.dying:
                self.damage(self.boss, 10)

    # ------------------------------------------------------------ update
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
        self.recoil = max(0.0, self.recoil - dt * 6)
        self.muzzle = max(0.0, getattr(self, "muzzle", 0) - dt)

        if self.state == "titulo":
            self.advance(dt, FWD_SPEED * 0.7, auto=True)
            self.update_parts(dt)
            return
        if self.state in ("pausa",):
            return
        if self.state == "game_over":
            self.over_t += dt
            self.advance(dt, FWD_SPEED * 0.3, auto=True)
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
            self.px += (math.sin(self.time * 0.4) * 1.5 - self.px) * dt
            self.cam_x = self.px
        self.cam_z += speed * dt
        self.walk += dt * speed * 0.9
        self.cam_y = CAM_H   # o balanco do passo fica so na mao/cajado
        self.bg_off -= self.d2cx(self.cam_z) * speed * dt * 9000
        self.bg_off += self.pvx * dt * 6
        self.update_camera_terms()
        base = int(self.cam_z // SEG)
        for n in [k for k in self.scen_cache if k < base - 1]:
            del self.scen_cache[n]
        for a in self.ambient:
            a[3] += dt
            if self.st["scenery"] == "cidadela":
                a[1] += dt * 0.8
            else:
                a[1] += math.sin(a[3] * 1.3) * dt * 0.4
                a[0] += a[4] * dt
            if a[2] < self.cam_z + 1 or a[1] > 7:
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
                p.vy *= -0.4
        self.parts = [p for p in self.parts if p.life > 0 and p.z > self.cam_z + 0.3]

    def update_play(self, dt):
        if self.test:
            self.autopilot()
            mv = self._auto_mv
        else:
            keys = pygame.key.get_pressed()
            mv = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
            self.firing = (getattr(self, "mouse_held", False) or pygame.mouse.get_pressed()[0]
                           or keys[pygame.K_SPACE] or keys[pygame.K_LCTRL] or keys[pygame.K_j])
        self.pvx += (mv * STRAFE_SPEED - self.pvx) * min(1.0, dt * 12)
        self.px = clamp(self.px + self.pvx * dt, -ROAD_W + 0.7, ROAD_W - 0.7)
        self.cam_x = self.px
        self.advance(dt, FWD_SPEED)
        for k in self.powers:
            self.powers[k] = max(0.0, self.powers[k] - dt)
        self.invul = max(0.0, self.invul - dt)
        frozen = self.powers["gelo"] > 0

        self.fire_cd -= dt
        if self.firing and self.fire_cd <= 0:
            self.fire()
            self.fire_cd = 0.075 if self.powers["rajada"] > 0 else 0.17

        self.spawn(dt)
        if not self.boss_spawned and self.progress() >= 1.0:
            self.spawn_boss()

        cz = self.cam_z
        for e in self.enemies:
            if e.dead:
                continue
            e.flash = max(0.0, e.flash - dt)
            if not frozen:
                self.update_enemy(e, dt)
            if e.z - cz < 0.8:
                if abs(e.x - self.px) < e.r + 0.4 and (e.kind == "golem" or abs(e.y - self.cam_y) < 1.6):
                    self.hurt()
                    self.explode(e.x, e.cy, cz + 2, (255, 120, 120), n=12)
                e.dead = True
        for b in self.blocks:
            b.flash = max(0.0, b.flash - dt)
            b.t += dt
            if b.z - cz < 0.5:
                b.dead = True
        for it in self.items:
            it.t += dt
            dz = it.z - cz
            if dz < 1.3 and abs(it.x - self.px) < 1.5:
                self.collect(it)
            elif dz < -0.5:
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
            if f.z - cz < 0.6:
                if abs(f.x - self.px) < 0.8 and abs(f.y - (self.cam_y - 0.3)) < 1.2:
                    self.hurt()
                    self.explode(f.x, f.y, cz + 1.5, (255, 140, 60), n=12, power=3, size=0.12)
                f.dead = True
        if self.boss:
            self.update_boss(dt, frozen)
        self.update_shots(dt)
        self.update_parts(dt)
        self.enemies = [e for e in self.enemies if not e.dead]
        self.blocks = [b for b in self.blocks if not b.dead]
        self.items = [i for i in self.items if not i.dead]
        self.fireballs = [f for f in self.fireballs if not f.dead]

    def update_enemy(self, e, dt):
        e.t += dt
        dz = e.z - self.cam_z
        lim = ROAD_W + 1.0
        if e.kind == "morcego":
            e.z -= e.v * dt
            e.vzw = -e.v
            e.x = clamp(e.bx + math.sin(e.t * 1.6 + e.ph) * e.amp, -lim, lim)
            e.y = e.by + math.sin(e.t * 5 + e.ph) * 0.35
            e.cy = e.y
        elif e.kind == "espectro":
            if e.t < e.hold_t and dz <= e.hold:
                e.z = self.cam_z + e.hold
                e.vzw = FWD_SPEED
            else:
                spd = e.v if e.t < e.hold_t else 5.0
                e.z -= spd * dt
                e.vzw = -spd
            e.x = clamp(e.bx + math.sin(e.t * 1.3 + e.ph) * 2.6, -lim, lim)
            e.y = e.by + math.sin(e.t * 2.1 + e.ph) * 0.5
            e.cy = e.y
            e.cd -= dt
            if e.cd <= 0 and 8 < dz < 90:
                self.enemy_fire(e.x, e.y, e.z - 0.5, speed=5 + self.stage_i)
                self.audio.play("inimigo_tiro", 0.35)
                e.cd = random.uniform(2.2, 3.2) - 0.2 * self.stage_i
        else:
            e.z -= e.v * dt
            e.vzw = -e.v
            e.x = clamp(e.x + clamp(self.px - e.x, -1, 1) * 0.7 * dt, -lim, lim)
            e.cd -= dt
            if e.cd <= 0 and 12 < dz < 70:
                self.enemy_fire(e.x + 1.0, 2.8, e.z - 0.8, speed=5, kind="pedra")
                e.cd = random.uniform(2.2, 3.2)

    def update_boss(self, dt, frozen):
        b = self.boss
        b.t += dt
        b.flash = max(0.0, b.flash - dt)
        if b.dist > 20:
            b.dist = max(20.0, b.dist - 10 * dt)
            b.vzw = FWD_SPEED - 10
        else:
            b.vzw = FWD_SPEED
        b.z = self.cam_z + b.dist + math.sin(b.t * 0.5) * 2
        b.x = math.sin(b.t * 0.6) * 3.0
        b.y = 3.2 + math.sin(b.t * 1.4) * 0.6
        b.cy = b.y
        if b.dying:
            b.dying_t += dt
            if random.random() < dt * 14:
                self.explode(b.x + random.uniform(-2.5, 2.5), b.y + random.uniform(-2.5, 2.5), b.z - 1,
                             random.choice([(255, 150, 60), self.st["boss_tint"], (255, 240, 200)]), n=24, power=8)
                if random.random() < 0.3:
                    self.audio.play("explosao", 0.6)
                self.shake = 0.2
            if b.dying_t > 2.8:
                self.explode(b.x, b.y, b.z, (255, 255, 230), n=120, power=16, size=0.4)
                self.white_flash = 0.8
                self.audio.play("bomba")
                self.boss = None
                self.stage_clear()
            return
        if frozen or b.dist > 26:
            return
        phase = 0 if b.hp > b.maxhp * 0.66 else 1 if b.hp > b.maxhp * 0.33 else 2
        b.cd -= dt
        if b.cd <= 0:
            b.pattern = (b.pattern + 1) % 3
            if b.pattern != 1:
                n = 5 + 2 * phase
                for i in range(n):
                    self.enemy_fire(b.x, b.y - 0.5, b.z - 2, speed=5 + phase, aim_dx=(i - (n - 1) / 2) * 2.2)
            else:
                k = 8 + 2 * phase
                rot = random.uniform(0, 6.28)
                for i in range(k):
                    a = rot + i / k * 2 * math.pi
                    self.enemy_fire(b.x, b.y, b.z - 2, speed=4.5 + phase, aim_dx=math.cos(a) * 3.4,
                                    aim_dy=math.sin(a) * 1.2 + 0.4)
            self.audio.play("inimigo_tiro")
            b.cd = 2.1 - 0.45 * phase
        b.summon -= dt
        if b.summon <= 0:
            for i in range(3):
                e = self.make_enemy("morcego", b.x + (i - 1) * 2.0, b.z - 3)
                self.enemies.append(e)
            b.summon = random.uniform(7, 10) - phase * 1.5

    def update_shots(self, dt):
        tg = self.targets()
        cz = self.cam_z
        for s in self.shots:
            ox, oy, oz = s.x, s.y, s.z
            s.x += s.vx * dt
            s.y += s.vy * dt
            s.z += s.vz * dt
            s.life -= dt
            s.t += dt
            if len(self.parts) < 500 and s.z - self.cam_z > 2.5 and int(s.t * 60) % 2 == 0:   # rastro
                col = (255, 200, 90) if self.powers["triplo"] > 0 else (120, 200, 255)
                self.parts.append(Ent(x=s.x + random.uniform(-0.05, 0.05), y=s.y + random.uniform(-0.05, 0.05),
                                      z=s.z, vx=random.uniform(-0.3, 0.3), vy=random.uniform(-0.2, 0.4), vz=0,
                                      life=0.25, max=0.25, color=(col[0] // 2, col[1] // 2, col[2] // 2), size=0.14, grav=False))
            if s.y < 0:
                s.dead = True
                self.sparks(s.x, 0.05, s.z, (180, 230, 255), 5)
                continue
            for o in tg:
                if o.dead or abs(o.z - s.z) > 5:
                    continue
                if seg_dist2(ox, oy, oz - 0.7, s.x, s.y, s.z, o.x, o.cy, o.z) < o.r * o.r:
                    self.damage(o, s.dmg)
                    s.dead = True
                    break
        self.shots = [s for s in self.shots if not s.dead and s.life > 0 and s.z - cz < FAR]

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
        """Piloto automatico usado no modo de teste."""
        self.firing = True
        best = None
        for o in self.targets():
            dz = o.z - self.cam_z
            if 4 < dz < 120:
                if best is None or dz < best.z - self.cam_z:
                    best = o
        if best is not None:
            p = self.proj(best.x, best.cy, best.z)
            if p:
                self.aim_pos = (int(p[0]), int(p[1]))
        tx = 0.0
        for it in self.items:
            if 0 < it.z - self.cam_z < 40:
                tx = it.x
        for f in self.fireballs:
            if 0 < f.z - self.cam_z < 12 and abs(f.x - self.px) < 1.2:
                tx = self.px + (2.5 if f.x <= self.px else -2.5)
        self._auto_mv = clamp((tx - self.px) * 2, -1, 1)

    # -------------------------------------------------------------- desenho
    def blit_world(self, surf, key, x, y, z, height_m, anchor="bottom", flip=False):
        p = self.proj(x, y, z)
        if not p:
            return None
        sx, sy, s = p
        hp = int(height_m * s)
        if hp < 2 or hp > H * 2.4:
            return p
        img = self.scaled(key, hp, flip)
        if anchor == "bottom":
            rect = img.get_rect(midbottom=(int(sx), int(sy)))
        else:
            rect = img.get_rect(center=(int(sx), int(sy)))
        if rect.right < 0 or rect.left > W or rect.bottom < 0 or rect.top > H:
            return p
        dz = z - self.cam_z
        fade = clamp((FAR - dz) / (FAR * 0.35), 0, 1)
        clip = self.seg_clip.get(int(z // SEG), H)
        surf.set_clip((0, 0, W, int(clip) + 1))
        if fade < 1:
            img.set_alpha(int(255 * fade))
            surf.blit(img, rect)
            img.set_alpha(255)
        else:
            surf.blit(img, rect)
        surf.set_clip(None)
        return p

    def wglow(self, surf, x, y, z, radius_m, color, mult=1.0, maxr=520):
        p = self.proj(x, y, z)
        if not p:
            return
        sx, sy, s = p
        r = radius_m * s
        if r < 1.5:
            return
        r = min(r, maxr)
        dz = z - self.cam_z
        f = clamp((FAR - dz) / (FAR * 0.4), 0, 1) * mult
        f = round(f * 4) / 4
        if f <= 0:
            return
        col = (int(color[0] * f), int(color[1] * f), int(color[2] * f)) if f < 1 else color
        img = self.glow_img(col, r)
        surf.blit(img, (int(sx - img.get_width() / 2), int(sy - img.get_height() / 2)),
                  special_flags=pygame.BLEND_RGB_ADD)

    def setup_floor(self):
        """Pre-calcula tudo o que nao muda de um quadro para outro na projecao do piso."""
        rh, rw = (H - HORIZON) // 2, W // 2
        fy = np.arange(rh) * 2 + 1.0
        xs = ((np.arange(rw) * 2 + 1) - W / 2) / FOCAL
        dz = CAM_H * FOCAL / fy
        r0 = int(np.searchsorted(-dz, -FAR * 1.05))
        self.fl_r0 = r0
        self.fl_dz = dz[r0:].astype(np.float32)
        self.fl_xd = (xs[None, :] * self.fl_dz[:, None]).astype(np.float32)
        masks = self.floor_small.get_shifts()

        def pack(t):
            t = np.clip(t, 0, 255).astype(np.uint32)
            return ((t[..., 0] << masks[0]) | (t[..., 1] << masks[1]) | (t[..., 2] << masks[2])).ravel()

        def bands(T0, tile, n):
            tpp = (T0 / tile) * self.fl_dz * 2 / FOCAL
            lvl = np.clip(np.floor(np.log2(np.maximum(tpp, 1.0))), 0, n - 1).astype(int)
            out = []
            for k in range(n):
                rows = np.nonzero(lvl == k)[0]
                if len(rows):
                    out.append((rows[0], rows[-1] + 1, k))
            return out

        for F in self.floor:
            F["road_p"] = [(pack(t), t.shape[0]) for t in F["road"]]
            F["ground_p"] = [(pack(t), t.shape[0]) for t in F["ground"]]
            F["curb_p"] = pack(F["curb"])
            F["curb_shape"] = F["curb"].shape[:2]
        self.fl_bands_road = bands(self.floor[0]["road"][0].shape[0], 4.0, len(self.floor[0]["road"]))
        self.fl_bands_ground = bands(self.floor[0]["ground"][0].shape[0], 6.0, len(self.floor[0]["ground"]))
        # nevoa: sobreposicao com alfa por linha (a distancia de cada linha e fixa)
        self.fog_over = []
        yb = np.arange(H - HORIZON) + 0.5
        f = np.clip((CAM_H * FOCAL / yb) / FAR, 0, 1) ** 1.1
        alpha = (f * 255).astype(np.uint8)
        for i, st in enumerate(STAGES):
            o = pygame.Surface((W, H - HORIZON), SRCALPHA)
            o.fill(st["fog"] + (255,))
            pa = pygame.surfarray.pixels_alpha(o)
            pa[:] = alpha[None, :]
            del pa
            self.fog_over.append(o.convert_alpha())
            self.floor[i]["fog_p"] = pack(np.array(st["fog"], np.float32)[None, None, :])[0]

    def draw_floor(self, surf):
        """Projecao de piso: cada pixel do chao vira uma coordenada (x, z) no mundo
        e busca a cor nas texturas da via romana, do meio-fio e do terreno."""
        if not hasattr(self, "fl_dz"):
            self.setup_floor()
        F = self.floor[self.stage_i]
        dz = self.fl_dz
        z = self.cam_z + dz
        off = (self.cam_x - self.warp_x_np(z)).astype(np.float32)
        X = self.fl_xd + off[:, None]
        ax = np.abs(X)
        res = np.empty(X.shape, np.uint32)
        gbuf = np.empty(X.shape, np.uint32)
        for dst, bands, mp, tile, xoff in ((res, self.fl_bands_road, F["road_p"], 4.0, ROAD_W),
                                           (gbuf, self.fl_bands_ground, F["ground_p"], 6.0, 0.0)):
            for a, b, k in bands:
                tex, Tk = mp[k]
                tpm = Tk / tile
                u = ((X[a:b] + xoff) * tpm).astype(np.int32) & (Tk - 1)
                v = (z[a:b] * tpm).astype(np.int32) & (Tk - 1)
                dst[a:b] = tex[(v * Tk)[:, None] + u]
        off_road = ax >= ROAD_W
        np.copyto(res, gbuf, where=off_road)
        ch, cw = F["curb_shape"]
        m = off_road & (ax < ROAD_W + 0.55)
        cu = np.minimum(((ax - ROAD_W) * ((cw - 1) / 0.55)).astype(np.int32), cw - 1)
        cv = (z * 128).astype(np.int32) % ch
        idx = (cv * cw)[:, None] + cu
        np.copyto(res, F["curb_p"][np.clip(idx, 0, ch * cw - 1)], where=m)
        pix = pygame.surfarray.pixels2d(self.floor_small)
        pix[:, :self.fl_r0] = F["fog_p"]
        pix[:, self.fl_r0:] = res.T
        del pix
        pygame.transform.smoothscale(self.floor_small, (W, H - HORIZON), self.floor_big)
        self.floor_big.blit(self.fog_over[self.stage_i], (0, 0))
        surf.blit(self.floor_big, (0, HORIZON))
        self.seg_clip = {}

    def draw_road(self, surf):
        st = self.st
        base = int(self.cam_z // SEG)
        maxy = float(H)
        clip = {}
        fog = st["fog"]
        for i in range(DRAW_SEGS):
            n = base + i
            z1 = max(n * SEG, self.cam_z + 0.3)
            z2 = (n + 1) * SEG
            clip[n] = maxy
            if z2 <= z1:
                continue
            x1, y1, s1 = self.proj(0, 0, z1)
            x2, y2, s2 = self.proj(0, 0, z2)
            if y2 >= maxy or y2 >= y1:
                continue
            f = min(1.0, (z1 - self.cam_z) / FAR) ** 1.1
            alt = (n // 3) % 2
            gc = lerp_col(st["grass"][alt], fog, f)
            rc = lerp_col(st["rumble"][alt], fog, f)
            roc = lerp_col(st["road"][alt], fog, f)
            surf.set_clip((0, 0, W, int(maxy) + 1))
            y1i, y2i = int(y1) + 1, int(y2)
            pygame.draw.rect(surf, gc, (0, y2i, W, y1i - y2i + 1))
            a, b = (ROAD_W + 0.7) * s1, (ROAD_W + 0.7) * s2
            pygame.draw.polygon(surf, rc, [(x1 - a, y1), (x2 - b, y2), (x2 + b, y2), (x1 + a, y1)])
            a, b = ROAD_W * s1, ROAD_W * s2
            pygame.draw.polygon(surf, roc, [(x1 - a, y1), (x2 - b, y2), (x2 + b, y2), (x1 + a, y1)])
            if n % 4 < 2:
                lc = lerp_col(st["lane"], fog, f)
                for off in (-ROAD_W / 3, ROAD_W / 3):
                    pygame.draw.polygon(surf, lc, [(x1 + (off - 0.08) * s1, y1), (x2 + (off - 0.08) * s2, y2),
                                                   (x2 + (off + 0.08) * s2, y2), (x1 + (off + 0.08) * s1, y1)])
            maxy = y2
        surf.set_clip(None)
        self.seg_clip = clip

    def draw_background(self, surf):
        bg = self.bg[self.stage_i]
        st = self.st
        surf.blit(bg["sky"], (0, 0))
        if st["moon"]:
            mx = int(W * 0.72 - (self.bg_off * 0.15) % (W * 2) + W * 0.0)
            mx = (mx + W) % (W * 2) - W // 2
            col = (200, 200, 230) if self.stage_i == 0 else (255, 150, 90)
            g = self.glow_img((90, 90, 120) if self.stage_i == 0 else (140, 60, 30), 180)
            surf.blit(g, (mx - 180, 130 - 180), special_flags=pygame.BLEND_RGB_ADD)
            pygame.draw.circle(surf, col, (mx, 130), 46)
            pygame.draw.circle(surf, lerp_col(col, (0, 0, 0), 0.12), (mx + 12, 122), 12)
            pygame.draw.circle(surf, lerp_col(col, (0, 0, 0), 0.1), (mx - 16, 142), 8)
        for key, fac in (("m1", 0.3), ("m2", 0.6)):
            layer = bg[key]
            w = layer.get_width()
            off = int(self.bg_off * fac) % w
            surf.blit(layer, (-off, 0))
            surf.blit(layer, (w - off, 0))
        pygame.draw.rect(surf, st["fog"], (0, HORIZON + 14, W, H))
        if "c1" in bg:
            for key, fac in (("c1", 0.35), ("c2", 0.7)):
                layer = bg[key]
                w = layer.get_width()
                off = int(self.bg_off * fac) % w
                yy = -40 if key == "c1" else -70
                surf.blit(layer, (-off, yy))
                surf.blit(layer, (w - off, yy))

    def draw_world(self, surf):
        self.draw_background(surf)
        self.draw_floor(surf)
        cz = self.cam_z
        dr = []
        base = int(cz // SEG)
        for n in range(base + 1, base + DRAW_SEGS):
            for o in self.scenery_for(n):
                dz = o[1] - cz
                if 0.5 < dz < FAR:
                    dr.append((dz, 0, o))
        for e in self.enemies:
            dr.append((e.z - cz, 1, e))
        for b in self.blocks:
            dr.append((b.z - cz, 2, b))
        for it in self.items:
            dr.append((it.z - cz, 3, it))
        for f in self.fireballs:
            dr.append((f.z - cz, 4, f))
        for s in self.shots:
            dr.append((s.z - cz, 5, s))
        for p in self.parts:
            dr.append((p.z - cz, 6, p))
        for a in self.ambient:
            dr.append((a[2] - cz, 7, a))
        if self.boss:
            dr.append((self.boss.z - cz, 8, self.boss))
        dr.sort(key=lambda d: -d[0])
        fns = (self.d_scen, self.d_enemy, self.d_block, self.d_item, self.d_fire, self.d_shot, self.d_part,
               self.d_amb, self.d_boss)
        for dz, k, o in dr:
            if dz > 0.25:
                fns[k](surf, o)

    def d_scen(self, surf, o):
        x, z, key, hgt, flip, extra = o
        self.blit_world(surf, key, x, 0, z, hgt, "bottom", flip)
        if extra == "fogo":
            fl = 0.85 + 0.15 * math.sin(self.time * 17 + z) + 0.1 * math.sin(self.time * 7.3 + z * 3)
            self.wglow(surf, x, 1.6, z, 3.0 * fl, (150, 70, 20))
            self.wglow(surf, x, 1.75, z, 0.9 * fl, (255, 170, 70))
            self.wglow(surf, x, 1.65, z, 0.35 * fl, (255, 240, 200))
        elif extra == "cristal":
            pul = 0.7 + 0.3 * math.sin(self.time * 2 + z)
            self.wglow(surf, x, hgt * 0.4, z, hgt * 0.8, (40, 50, 110), pul)

    def d_shadow(self, surf, x, z, r):
        self.blit_world(surf, "sombra", x, 0, z, r * 0.8, "center")

    def d_enemy(self, surf, e):
        frozen = self.powers["gelo"] > 0
        if e.kind == "morcego":
            self.d_shadow(surf, e.x, e.z, 1.0)
            key = "bat%d" % (int((self.time if not frozen else 0) * 9 + e.ph) % 2)
            p = self.blit_world(surf, key, e.x, e.y, e.z, e.h, "center")
        elif e.kind == "espectro":
            self.d_shadow(surf, e.x, e.z, 0.9)
            self.wglow(surf, e.x, e.y, e.z, 2.2, (30, 90, 70))
            key = "wisp%d" % (int(self.time * 6 + e.ph) % 2)
            p = self.blit_world(surf, key, e.x, e.y - 0.25, e.z, e.h, "center")
        else:
            self.d_shadow(surf, e.x, e.z, 1.8)
            p = self.blit_world(surf, "golem%d" % self.stage_i, e.x, 0, e.z, e.h, "bottom")
            self.wglow(surf, e.x, 2.9, e.z - 0.2, 0.9, (110, 60, 10))
        if e.flash > 0:
            self.wglow(surf, e.x, e.cy, e.z - 0.3, e.r * 1.6, (160, 160, 160))
        if frozen:
            self.wglow(surf, e.x, e.cy, e.z - 0.3, e.r * 1.8, (30, 70, 140))

    def d_block(self, surf, b):
        self.d_shadow(surf, b.x, b.z, 1.0)
        y = b.y + math.sin(b.t * 2) * 0.12
        b.cy = y
        self.wglow(surf, b.x, y, b.z, 1.6, (70, 50, 10))
        self.blit_world(surf, "block_hit" if b.flash > 0 else "block", b.x, y, b.z, 1.5, "center")

    def d_item(self, surf, it):
        c = ITEMS[it.kind][0]
        y = it.y + math.sin(it.t * 3) * 0.15
        self.d_shadow(surf, it.x, it.z, 0.6)
        self.wglow(surf, it.x, y, it.z, 1.4 + 0.2 * math.sin(it.t * 6), c, 0.6)
        self.blit_world(surf, "item_" + it.kind, it.x, y, it.z, 0.95, "center")

    def d_fire(self, surf, f):
        if f.kind == "pedra":
            self.blit_world(surf, "rock%d" % self.stage_i, f.x, f.y - 0.3, f.z, 0.8, "center", int(f.t * 8) % 2 == 0)
            self.wglow(surf, f.x, f.y, f.z, 0.8, (90, 50, 20))
        else:
            self.wglow(surf, f.x, f.y, f.z, 1.5, (170, 70, 20))
            self.blit_world(surf, "fogo%d" % (int(f.t * 10) % 2), f.x, f.y, f.z, 0.9, "center")
            self.wglow(surf, f.x, f.y, f.z, 0.35, (255, 230, 180))

    def d_shot(self, surf, s):
        p1 = self.proj(s.x, s.y, s.z)
        p0 = self.proj(s.x - s.vx * 0.025, s.y - s.vy * 0.025, s.z - s.vz * 0.025)
        if not p1:
            return
        col = (255, 220, 110) if self.powers["triplo"] > 0 else (140, 220, 255)
        if p0:
            w = min(10, max(3, int(0.16 * p1[2])))
            pygame.draw.line(surf, col, p0[:2], p1[:2], w)
            pygame.draw.line(surf, (255, 255, 255), p0[:2], p1[:2], max(1, w // 2))
        self.wglow(surf, s.x, s.y, s.z, 1.1, (col[0] // 3, col[1] // 3, col[2] // 3), maxr=60)
        self.wglow(surf, s.x, s.y, s.z, 0.35, (200, 200, 200), maxr=22)
        r = min(8, max(3, int(0.13 * p1[2])))
        pygame.draw.circle(surf, (255, 255, 255), (int(p1[0]), int(p1[1])), r)

    def d_part(self, surf, p):
        k = clamp(p.life / p.max, 0, 1)
        col = p.color if k > 0.5 else lerp_col((0, 0, 0), p.color, k * 2)
        col = (col[0] // 8 * 8, col[1] // 8 * 8, col[2] // 8 * 8)
        self.wglow(surf, p.x, p.y, p.z, p.size * (0.6 + k), col, maxr=34 if p.size < 0.2 else 520)

    def d_amb(self, surf, a):
        tw = 0.5 + 0.5 * math.sin(a[3] * 3)
        c = self.st["ambient"]
        col = (int(c[0] * tw) // 16 * 16, int(c[1] * tw) // 16 * 16, int(c[2] * tw) // 16 * 16)
        if col[0] + col[1] + col[2] > 0:
            self.wglow(surf, a[0], a[1], a[2], 0.18, col)

    def d_boss(self, surf, b):
        self.d_shadow(surf, b.x, b.z, 3.2)
        tint = self.st["boss_tint"]
        self.wglow(surf, b.x, b.y, b.z + 0.5, 7.0, lerp_col(tint, (0, 0, 0), 0.6))
        p = self.blit_world(surf, "boss%d" % self.stage_i, b.x, b.y, b.z, 6.0, "center")
        if not p:
            return
        sx, sy, s = p
        R = 6.0 * s / 2 * (160 / 260)
        look = clamp((self.px - b.x) / 6, -1, 1)
        ix, iy = sx + look * R * 0.28, sy + R * 0.1
        rot = 0.2 * math.sin(b.t * 3)
        pygame.draw.circle(surf, lerp_col(tint, (0, 0, 0), 0.4), (int(ix), int(iy)), int(R * 0.46))
        pygame.draw.circle(surf, tint, (int(ix), int(iy)), int(R * 0.40))
        pygame.draw.circle(surf, lerp_col(tint, (255, 255, 255), 0.4), (int(ix), int(iy)), int(R * 0.40), max(1, int(R * 0.04)))
        pw = R * (0.10 + 0.05 * abs(math.sin(b.t * 1.7))) * (1.6 if b.dying else 1)
        pygame.draw.ellipse(surf, (10, 4, 10), (ix - pw, iy - R * 0.3, pw * 2, R * 0.6))
        pygame.draw.circle(surf, (255, 255, 255), (int(ix - R * 0.16), int(iy - R * 0.18 + rot)), max(1, int(R * 0.07)))
        if b.flash > 0:
            self.wglow(surf, b.x, b.y, b.z - 1, 3.0, (140, 140, 140))
        if self.powers["gelo"] > 0:
            self.wglow(surf, b.x, b.y, b.z - 1, 3.4, (30, 70, 140))

    def draw_viewmodel(self, surf):
        bx = math.sin(self.walk) * 12 + self.pvx * -2.5
        by = abs(math.cos(self.walk)) * 10 + self.recoil * 30
        x, y = W - 470 + bx, H - 400 + by
        surf.blit(self.wand, (x, y))
        tip = (x + 88, y + 60)
        self.tip_screen = tip
        if getattr(self, "muzzle", 0) > 0:
            g = self.glow_img((255, 255, 255), 90 + self.muzzle * 400)
            surf.blit(g, (tip[0] - g.get_width() // 2, tip[1] - g.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)
        if self.powers["rajada"] > 0:
            col = (150, 140, 60)
        elif self.powers["triplo"] > 0:
            col = (150, 110, 30)
        else:
            col = (50, 110, 150)
        r = 46 + 8 * math.sin(self.time * 5) + self.recoil * 70
        g = self.glow_img(col, r)
        surf.blit(g, (tip[0] - g.get_width() // 2, tip[1] - g.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)
        if self.recoil > 0.5:
            g = self.glow_img((200, 230, 255), 26 + self.recoil * 30)
            surf.blit(g, (tip[0] - g.get_width() // 2, tip[1] - g.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)

    def draw_crosshair(self, surf):
        mx, my = self.aim()
        lock = self.pick_target(mx, my) is not None
        col = (255, 90, 80) if lock else (230, 240, 255)
        r = 14 if lock else 18
        a = self.time * 3 if lock else 0
        pygame.draw.circle(surf, col, (mx, my), r, 2)
        for k in range(4):
            ang = a + k * math.pi / 2
            p0 = (mx + math.cos(ang) * (r + 4), my + math.sin(ang) * (r + 4))
            p1 = (mx + math.cos(ang) * (r + 12), my + math.sin(ang) * (r + 12))
            pygame.draw.line(surf, col, p0, p1, 2)
        pygame.draw.circle(surf, col, (mx, my), 2)

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
        self.text(surf, "VIDAS  x%d" % self.lives, self.f_small, (235, 225, 200), topleft=(26, 62))
        self.text(surf, "PONTOS %07d" % self.score, self.f_small, (255, 230, 150), topright=(W - 24, 20))
        self.text(surf, "RECORDE %07d" % max(self.hiscore, self.score), self.f_tiny, (200, 200, 220),
                  topright=(W - 24, 50))
        bw, bx, byy = 420, W // 2 - 210, 22
        bar = pygame.Surface((bw, 14), SRCALPHA)
        bar.fill((0, 0, 0, 140))
        surf.blit(bar, (bx, byy))
        if self.boss:
            k = max(0, self.boss.hp) / self.boss.maxhp
            pygame.draw.rect(surf, (200, 30, 40), (bx + 2, byy + 2, int((bw - 4) * k), 10))
            pygame.draw.rect(surf, (255, 120, 120), (bx + 2, byy + 2, int((bw - 4) * k), 3))
            self.text(surf, "GUARDIÃO", self.f_tiny, (255, 180, 180), midtop=(W // 2, byy + 16))
        else:
            k = self.progress()
            pygame.draw.rect(surf, self.st["lane"], (bx + 2, byy + 2, int((bw - 4) * k), 10))
            pygame.draw.circle(surf, (255, 255, 255), (bx + 2 + int((bw - 4) * k), byy + 7), 7)
            pygame.draw.circle(surf, (200, 40, 50), (bx + bw, byy + 7), 8)
            self.text(surf, "Fase %d  —  %s" % (self.stage_i + 1, self.st["name"]), self.f_tiny,
                      (225, 225, 240), midtop=(W // 2, byy + 16))
        y = H - 60
        for k in ("triplo", "rajada", "gelo", "escudo"):
            t = self.powers[k]
            if t > 0:
                icon = self.scaled("item_" + k, 40)
                surf.blit(icon, (22, y))
                tot = 6.0 if k == "gelo" else 15.0
                pygame.draw.rect(surf, (0, 0, 0), (68, y + 16, 104, 10))
                pygame.draw.rect(surf, ITEMS[k][0], (70, y + 18, int(100 * t / tot), 6))
                label = ITEMS[k][1] + (" x%d" % self.shield_hits if k == "escudo" else "")
                self.text(surf, label, self.f_tiny, (240, 240, 240), topleft=(180, y + 10))
                y -= 46
        for i, (txt, col, t) in enumerate(self.popups):
            a = int(255 * clamp(t / 0.6, 0, 1))
            self.text(surf, txt, self.f_med, col, alpha=a, center=(W // 2, H - 170 - i * 38 - (1.6 - t) * 40))

    def draw_message(self, surf):
        if not self.msg:
            return
        title, sub, t, tot = self.msg
        a = int(255 * clamp(min(t / 0.6, (tot - t) / 0.4 + 0.2), 0, 1))
        self.text(surf, title, self.f_big, (255, 240, 200), alpha=a, center=(W // 2, H // 2 - 110))
        if sub:
            self.text(surf, sub, self.f_med, (220, 220, 240), alpha=a, center=(W // 2, H // 2 - 60))

    def draw(self):
        surf = self.view
        self.draw_world(surf)
        if self.powers["gelo"] > 0 and self.state == "jogando":
            surf.blit(self.edge_ice, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        if self.powers["escudo"] > 0 and self.state == "jogando":
            k = 0.5 + 0.5 * math.sin(self.time * 4)
            if k > 0.3:
                surf.blit(self.edge_shield, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(self.vignette, (0, 0))
        if self.state in ("jogando", "pausa", "fase_concluida"):
            if not (self.invul > 0 and int(self.time * 16) % 2 and self.state == "jogando"):
                self.draw_viewmodel(surf)
            else:
                self.draw_viewmodel(surf)
            self.draw_hud(surf)
            if self.state == "jogando":
                self.draw_crosshair(surf)
        if self.red_flash > 0:
            o = pygame.Surface((W, H), SRCALPHA)
            o.fill((200, 0, 0, int(140 * self.red_flash / 0.55)))
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
            self.text(surf, "P para continuar", self.f_small, (220, 220, 220), center=(W // 2, H // 2 + 50))
        elif self.state == "game_over":
            o = pygame.Surface((W, H), SRCALPHA)
            o.fill((20, 0, 0, int(min(170, self.over_t * 120))))
            surf.blit(o, (0, 0))
            self.glow_text(surf, "FIM DE JOGO", self.f_huge, (255, 200, 190), (160, 30, 20), center=(W // 2, H // 2 - 40))
            self.text(surf, "Pontos: %d" % self.score, self.f_med, (255, 230, 160), center=(W // 2, H // 2 + 40))
            if self.over_t > 2:
                self.text(surf, "Clique para voltar ao título", self.f_small, (230, 230, 230),
                          center=(W // 2, H // 2 + 100))
        elif self.state == "vitoria":
            self.glow_text(surf, "VITÓRIA", self.f_huge, (255, 245, 210), (180, 130, 40), center=(W // 2, H // 2 + 40))
            self.text(surf, "Pontos: %d" % self.score, self.f_med, (255, 230, 160), center=(W // 2, H // 2 + 110))
            self.text(surf, "Clique para voltar ao título", self.f_small, (230, 230, 230),
                      center=(W // 2, H // 2 + 160))
        if self.show_fps:
            self.text(surf, "%d fps" % self.clock.get_fps(), self.f_tiny, (180, 255, 180), topleft=(10, H - 26))
        ox = oy = 0
        if self.shake > 0:
            m = self.shake * 30
            ox, oy = random.uniform(-m, m), random.uniform(-m, m)
        self.screen.fill((0, 0, 0))
        self.screen.blit(surf, (ox, oy))

    def draw_title(self, surf):
        o = pygame.Surface((W, H), SRCALPHA)
        o.fill((0, 0, 10, 90))
        surf.blit(o, (0, 0))
        self.glow_text(surf, "LÂMINA DA AURORA", self.f_huge, (255, 244, 220), (60, 120, 200), center=(W // 2, 200))
        self.text(surf, "uma jornada em primeira pessoa", self.f_small, (200, 215, 240), center=(W // 2, 266))
        if int(self.time * 2) % 2 == 0:
            self.text(surf, "Clique ou Enter para começar", self.f_med, (255, 230, 150), center=(W // 2, 420))
        lines = ["A/D ou setas: desviar     Mouse: mirar     Clique/Espaço: atirar",
                 "Atire nos blocos ? para liberar poderes e passe por cima deles para pegar",
                 "P: pausa     F: tela cheia     Esc: sair"]
        for i, l in enumerate(lines):
            self.text(surf, l, self.f_tiny, (215, 215, 230), center=(W // 2, 520 + i * 28))
        if self.hiscore:
            self.text(surf, "Recorde: %d" % self.hiscore, self.f_small, (255, 220, 140), center=(W // 2, 640))

    # ------------------------------------------------------------- loop
    def begin(self):
        self.reset_game()
        self.start_stage(0)
        self.state = "jogando"
        pygame.mouse.set_visible(False)

    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if self.state in ("jogando", "pausa"):
                        self.state = "titulo"
                        self.hiscore = max(self.hiscore, self.score)
                        pygame.mouse.set_visible(True)
                        self.start_stage(0, silent=True)
                        self.audio.music(0)
                    else:
                        return False
                elif ev.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                elif ev.key == pygame.K_F3:
                    self.show_fps = not self.show_fps
                elif ev.key == pygame.K_F12:
                    pygame.image.save(self.view, "captura_%d.png" % int(self.time * 1000))
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

    def to_title(self):
        self.mouse_held = False
        self.state = "titulo"
        pygame.mouse.set_visible(True)
        self.start_stage(0, silent=True)
        self.audio.music(0)

    def run(self):
        while True:
            dt = min(self.clock.tick(60) / 1000.0, 1 / 30)
            if not self.handle_events():
                break
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()

    def run_test(self, frames, outdir, shots_at):
        """Roda sem janela com piloto automatico e salva capturas."""
        os.makedirs(outdir, exist_ok=True)
        self.draw()
        pygame.image.save(self.screen, os.path.join(outdir, "titulo.png"))
        self.begin()
        import time
        t0 = time.time()
        for f in range(frames):
            pygame.event.pump()
            if self.state == "game_over":
                self.lives = 3
                self.hp = MAX_HP
                self.state = "jogando"
            self.update(1 / 60)
            if f in shots_at or f == frames - 1:
                self.draw()
                pygame.image.save(self.screen, os.path.join(outdir, "f%05d_fase%d.png" % (f, self.stage_i + 1)))
        el = time.time() - t0
        print("frames=%d tempo=%.1fs  estado=%s fase=%d pontos=%d vidas=%d hp=%d boss=%s" % (
            frames, el, self.state, self.stage_i + 1, self.score, self.lives, self.hp, bool(self.boss)))
        # medir custo de desenho
        t0 = time.time()
        for _ in range(60):
            self.update(1 / 60)
            self.draw()
        print("desenho+update: %.1f ms/quadro" % ((time.time() - t0) / 60 * 1000))


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
