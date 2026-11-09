# -*- coding: utf-8 -*-
"""Recorta um personagem de fundo liso usando GrabCut (OpenCV). Uso: recorte_grabcut.py entrada saida altura"""
import sys
import cv2
import numpy as np
from PIL import Image

src, dst, alt = sys.argv[1], sys.argv[2], int(sys.argv[3])
img = cv2.imread(src)
h, w = img.shape[:2]
mask = np.zeros((h, w), np.uint8)
rect = (int(w * 0.08), int(h * 0.04), int(w * 0.84), int(h * 0.90))
bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
cv2.grabCut(img, mask, rect, bgd, fgd, 8, cv2.GC_INIT_WITH_RECT)
fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
# limpa: maior componente + componentes grandes (espada/escudo podem estar separados)
n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
if n > 1:
    big = stats[1:, cv2.CC_STAT_AREA].max()
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > big * 0.02]
    fg = np.isin(lab, keep).astype(np.uint8)
# remove sombra cinza neutra no chao (parte de baixo, pouca saturacao e mais escura que o fundo)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
alpha = cv2.GaussianBlur(fg.astype(np.float32), (0, 0), 1.2)
rgba = np.dstack([cv2.cvtColor(img, cv2.COLOR_BGR2RGB), (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])
im = Image.fromarray(rgba, "RGBA")
bbox = im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
im = im.crop(bbox)
if im.height > alt:
    im = im.resize((int(im.width * alt / im.height), alt), Image.LANCZOS)
im.save(dst)
print(dst, im.size)
