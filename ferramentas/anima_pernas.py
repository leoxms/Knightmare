# -*- coding: utf-8 -*-
"""Gera um ciclo de caminhada (8 quadros) a partir de um sprite parado, recortando as pernas
e animando cada uma: a perna que da o passo sobe e encurta (joelho dobrando), a outra apoia,
e o corpo desce um pouco no apoio.

Uso: python ferramentas/anima_pernas.py nome quadril pernaE_x0 pernaE_x1 pernaD_x0 pernaD_x1 [prefixo]
     (frações da largura/altura do sprite em arte/<nome>.png)
"""
import math
import os
import sys

import numpy as np
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
ARTE = os.path.join(os.path.dirname(AQUI), "arte")


def main():
    nome = sys.argv[1]
    hip, l0, l1, r0, r1 = map(float, sys.argv[2:7])
    prefixo = sys.argv[7] if len(sys.argv) > 7 else nome + "_andar"
    limite_sat = float(sys.argv[8]) if len(sys.argv) > 8 else 0.28
    n_frames = 8
    im = Image.open(os.path.join(ARTE, nome + ".png")).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    h, w = a.shape[:2]
    rgb = a[..., :3]
    sat = (rgb.max(-1) - rgb.min(-1)) / np.maximum(rgb.max(-1), 1)
    neutro = sat < limite_sat                       # armadura/osso: pouca saturacao (exclui escudo e madeira)
    yy, xx = np.mgrid[0:h, 0:w]
    y_hip = int(h * hip)
    legs = []
    for x0, x1 in ((l0, l1), (r0, r1)):
        m = (yy >= y_hip) & (xx >= int(w * x0)) & (xx < int(w * x1)) & neutro & (a[..., 3] > 0)
        legs.append(m)
    corpo = a.copy()
    for m in legs:
        corpo[m, 3] = 0
    pad = int(h * 0.04)
    for k in range(n_frames):
        ph = 2 * math.pi * k / n_frames
        lift = (max(0.0, math.sin(ph)), max(0.0, -math.sin(ph)))
        bob = int(round(abs(math.cos(ph)) * h * 0.012))          # corpo desce no apoio
        sway = math.sin(ph) * w * 0.006
        canvas = np.zeros((h + pad, w, 4), np.float32)
        for i, m in enumerate(legs):
            piece = np.zeros_like(a)
            piece[m] = a[m]
            ys, xs = np.nonzero(m)
            if len(ys) == 0:
                continue
            top, bot = ys.min(), ys.max() + 1
            seg = Image.fromarray(piece[top:bot].astype(np.uint8), "RGBA")
            L = lift[i]
            nh = max(4, int((bot - top) * (1 - 0.17 * L)))       # encurta: joelho dobra, pe sobe
            seg = seg.resize((w, nh), Image.LANCZOS)
            sarr = np.asarray(seg).astype(np.float32)
            sarr[..., :3] *= (1 - 0.10 * L)                       # perna que sobe fica na sombra
            dx = int(round((-1 if i == 0 else 1) * L * w * 0.012 + sway))
            sarr = np.roll(sarr, dx, axis=1)
            y = top + pad - bob // 2
            region = canvas[y:y + nh]
            al = sarr[..., 3:4] / 255.0
            region[...] = region * (1 - al) + sarr * al
        c = np.roll(corpo, int(round(sway)), axis=1)
        y = pad - bob
        region = canvas[y:y + h]
        al = c[..., 3:4] / 255.0
        region[...] = region * (1 - al) + c * al
        out = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), "RGBA")
        out.save(os.path.join(ARTE, "%s_%d.png" % (prefixo, k)))
    print("ok:", prefixo, n_frames, "quadros")


if __name__ == "__main__":
    main()
