# -*- coding: utf-8 -*-
"""Recorta o fundo liso das imagens geradas por IA (arte/bruto) e grava sprites prontos em arte/.

Uso:  python ferramentas/prepara_arte.py
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
BRUTO = os.path.join(RAIZ, "arte", "bruto")
SAIDA = os.path.join(RAIZ, "arte")

# nome: (tolerancia, modo, altura_final, recorte_x opcional (fracao esq, dir))
SPRITES = {
    "cavaleiro": (0, "alfa", 640, None),          # ja veio sem fundo
    "cavaleiro_video": (26, "borda", 640, None),   # igual ao do video
    "esqueleto": (30, "global", 640, None),
    "morcego": (30, "borda", 420, None),
    "gosma": (28, "borda", 360, None),
    "chefe": (30, "borda", 900, None),
    "cristal": (40, "borda", 320, None),
    "coluna_quebrada": (30, "borda", 900, None),
    "carvalho": (40, "global", 900, None),
    "cipreste": (40, "global", 900, (0.36, 0.64)),
}


SOMBRA = {"cavaleiro_video", "esqueleto", "gosma", "morcego", "chefe", "cristal"}


def recorta(nome, tol, modo, altura, corte, sombra=False):
    im = Image.open(os.path.join(BRUTO, nome + ".png")).convert("RGBA")
    if corte:
        w, h = im.size
        im = im.crop((int(w * corte[0]), 0, int(w * corte[1]), h))
    a = np.asarray(im).astype(np.float32)
    rgb, alpha = a[..., :3], a[..., 3] / 255.0
    if modo != "alfa":
        h, w = alpha.shape
        # modelo do fundo: plano de cor ajustado aos pixels da borda que parecem fundo
        yy, xx = np.mgrid[0:h, 0:w]
        bmask = np.zeros((h, w), bool)
        bmask[:8] = bmask[-8:] = True
        bmask[:, :8] = bmask[:, -8:] = True
        bc = rgb[bmask]
        med = np.median(bc, axis=0)
        ok = np.sqrt(((bc - med) ** 2).sum(-1)) < 45
        A = np.column_stack([np.ones(ok.sum()), yy[bmask][ok] / h, xx[bmask][ok] / w])
        coef, *_ = np.linalg.lstsq(A, bc[ok], rcond=None)
        bgc = coef[0] + (yy / h)[..., None] * coef[1] + (xx / w)[..., None] * coef[2]
        dist = np.sqrt(((rgb - bgc) ** 2).sum(-1))
        bg = dist < tol
        if sombra:
            lum = rgb.mean(-1)
            sat = (rgb.max(-1) - rgb.min(-1)) / np.maximum(rgb.max(-1), 1)
            bg |= (sat < 0.10) & (lum < bgc.mean(-1) + 5) & (lum > bgc.mean(-1) * 0.35)
        if modo == "borda":
            lab, n = ndimage.label(bg)
            tocam = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
            bg = np.isin(lab, list(tocam))
        fg = ndimage.binary_opening(~bg, iterations=2)
        lab, n = ndimage.label(fg)
        if n > 1:
            sizes = ndimage.sum(fg, lab, range(1, n + 1))
            keep = [i + 1 for i, sz in enumerate(sizes) if sz >= sizes.max() * (0.002 if modo == "global" else 0.5 if nome == "cristal" else 0.05)]
            fg = np.isin(lab, keep)
        soft = np.clip((dist - tol * 0.6) / (tol * 0.8), 0, 1)
        alpha = np.where(fg, np.maximum(soft, ndimage.binary_erosion(fg, iterations=2)), 0.0)
        alpha = ndimage.gaussian_filter(alpha, 1.0)
        alpha = np.clip((alpha - 0.15) / 0.85, 0, 1)
        k = np.clip(alpha, 0.05, 1)[..., None]
        rgb = np.where(alpha[..., None] < 0.98, (rgb - (1 - k) * bgc) / k, rgb)
        rgb = np.clip(rgb, 0, 255)
    out = np.dstack([rgb, alpha * 255]).astype(np.uint8)
    img = Image.fromarray(out, "RGBA")
    bbox = img.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    if h > altura:
        img = img.resize((max(1, int(w * altura / h)), altura), Image.LANCZOS)
    img.save(os.path.join(SAIDA, nome + ".png"))
    return img.size


def textura(nome, lado):
    im = Image.open(os.path.join(BRUTO, nome + ".png")).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((lado, lado), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    # torna periodica: mistura com a copia deslocada de meia volta, com peso que some nas bordas
    sh = np.roll(np.roll(a, lado // 2, 0), lado // 2, 1)
    t = np.linspace(0, 1, lado)
    wgt = np.minimum(t, 1 - t) * 2
    m = np.minimum(wgt[:, None], wgt[None, :])
    m = np.clip(m * 2.2, 0, 1)[..., None]
    a = a * m + sh * (1 - m)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(os.path.join(SAIDA, nome + ".png"))


def main():
    os.makedirs(SAIDA, exist_ok=True)
    for nome, (tol, modo, alt, corte) in SPRITES.items():
        if os.path.exists(os.path.join(BRUTO, nome + ".png")):
            print(nome, recorta(nome, tol, modo, alt, corte, sombra=nome in SOMBRA))
        else:
            print("faltando:", nome)
    textura("estrada", 1024)
    textura("grama", 1024)
    ceu = Image.open(os.path.join(BRUTO, "ceu.png")).convert("RGB")
    ceu.resize((2560, int(2560 * ceu.height / ceu.width)), Image.LANCZOS).save(os.path.join(SAIDA, "ceu.png"))
    print("texturas ok")


if __name__ == "__main__":
    sys.exit(main())
