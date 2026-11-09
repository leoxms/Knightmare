# -*- coding: utf-8 -*-
"""Gera arte/estrada_terra.png: estrada de terra batida com manchas de calcamento no meio e
bordas irregulares que se misturam a grama (trecho de 8 m x 12 m que emenda ao repetir).

Uso: python ferramentas/estrada_terra.py [limiar_manchas]
"""
import os
import sys

import numpy as np
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
ARTE = os.path.join(os.path.dirname(AQUI), "arte")
ROAD_W = 3.2
PX = 128
Wp, Hp = 8 * PX, 12 * PX


def tile_to(img, size):
    t = img.convert("RGB").resize((size, size), Image.LANCZOS)
    out = Image.new("RGB", (Wp, Hp))
    for y in range(0, Hp, size):
        for x in range(0, Wp, size):
            out.paste(t, (x, y))
    return np.asarray(out).astype(np.float32)


def pnoise(cx, cy, seed):
    g = np.random.default_rng(seed).random((cy, cx))
    ys = np.arange(Hp) * cy / Hp
    xs = np.arange(Wp) * cx / Wp
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = ys - y0, xs - x0
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    y1, x1 = (y0 + 1) % cy, (x0 + 1) % cx
    a = g[y0][:, x0] * (1 - fx) + g[y0][:, x1] * fx
    b = g[y1][:, x0] * (1 - fx) + g[y1][:, x1] * fx
    return a * (1 - fy)[:, None] + b * fy[:, None]


def main():
    limiar = float(sys.argv[1]) if len(sys.argv) > 1 else 0.86
    terra = tile_to(Image.open(os.path.join(ARTE, "bruto", "terra.png")), 3 * PX)
    pedra = tile_to(Image.open(os.path.join(ARTE, "estrada.png")), 3 * PX)
    grama = tile_to(Image.open(os.path.join(ARTE, "grama.png")), 4 * PX)
    xm = (np.arange(Wp) / PX - 4.0)[None, :]
    n1 = pnoise(4, 6, 1) * 0.6 + pnoise(16, 24, 2) * 0.3 + pnoise(48, 72, 3) * 0.1
    # manchas de calcamento: blocos irregulares no centro, separados por terra
    n2 = pnoise(3, 4, 4) * 0.55 + pnoise(8, 10, 5) * 0.30 + pnoise(24, 36, 6) * 0.15
    centro = np.exp(-(xm / 1.5) ** 2)
    m_pedra = np.clip((n2 * 1.0 + centro * 0.45 - limiar) / 0.05, 0, 1)
    col = terra * (0.82 + 0.34 * n1[..., None])
    # calcamento meio afundado: bordas da mancha somem sob a terra
    col = col * (1 - m_pedra[..., None]) + pedra * 0.9 * m_pedra[..., None]
    borda_d = ROAD_W + (pnoise(1, 4, 7) - 0.5) * 1.2 + (pnoise(1, 24, 8) - 0.5) * 0.5
    borda_e = ROAD_W + (pnoise(1, 4, 9) - 0.5) * 1.2 + (pnoise(1, 24, 10) - 0.5) * 0.5
    d = np.where(xm >= 0, borda_d - xm, borda_e + xm)
    fino = pnoise(64, 96, 11)
    m_grama = np.clip((-d + (fino - 0.5) * 0.9) / 0.35 + 0.5, 0, 1)
    col = col * (1 - m_grama[..., None]) + grama * 0.75 * m_grama[..., None]
    col *= (1 - 0.18 * np.clip(1 - np.abs(d) / 0.6, 0, 1))[..., None]
    alpha = np.clip((d + 1.6) / 0.5, 0, 1)
    rgba = np.dstack([np.clip(col, 0, 255), alpha * 255]).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(os.path.join(ARTE, "estrada_terra.png"))
    print("ok, calcamento em %.0f%% da faixa" % (100 * (m_pedra > 0.5).mean()))


if __name__ == "__main__":
    main()
