# -*- coding: utf-8 -*-
"""Colunas fieis a referencia (arte/bruto/referencia.png): fuste grosso com caneluras largas,
capitel de laje quadrada lascada sobre equino redondo, base com toro sobre bloco, e versoes
quebradas com corte inclinado. A cor/sujeira da pedra vem das colunas da propria referencia.
"""
import math
import os
import random

import numpy as np
from PIL import Image, ImageFilter
from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
                          GeomVertexWriter, NodePath, Vec3)

# recortes (x0, y0, x1, y1) do fuste de colunas na referencia 1182x658
RECORTES_FUSTE = [(1020, 240, 1075, 395), (140, 240, 200, 392), (1115, 345, 1170, 470), (40, 335, 100, 470)]


def build_stone_texture(arte_dir):
    """Textura de pedra a partir das colunas da referencia, sem o sombreamento da foto."""
    out = os.path.join(arte_dir, "pedra_coluna2.png")
    if os.path.exists(out):
        return out
    ref = Image.open(os.path.join(arte_dir, "bruto", "referencia.png")).convert("RGB")
    faixas = []
    for box in RECORTES_FUSTE:
        c = np.asarray(ref.crop(box).resize((64, 256), Image.LANCZOS)).astype(np.float32)
        lum = c.mean(-1)
        perfil = lum.mean(0, keepdims=True)                 # sombreamento cilindrico + caneluras
        perfil = np.maximum(perfil, 1.0)
        c = c / perfil[..., None] * lum.mean()              # achata a luz da foto
        faixas.append(c)
    tira = np.concatenate([faixas[0], faixas[1][:, ::-1], faixas[2], faixas[3][:, ::-1]], axis=1)  # 256 px
    tira = np.concatenate([tira, tira[:, ::-1]], axis=1)    # emenda horizontal (512 px)
    # normaliza para o bege-acinzentado da referencia
    alvo = np.array([176, 168, 150], np.float32)
    tira = tira / tira.reshape(-1, 3).mean(0) * alvo
    # sujeira: escurece e esverdeia a parte de baixo (musgo)
    t = np.linspace(0, 1, tira.shape[0])[:, None] ** 2.2    # 0 em cima, 1 embaixo
    musgo = np.array([70, 78, 52], np.float32)
    tira = tira * (1 - 0.45 * t[..., None]) + musgo * 0.45 * t[..., None]
    im = Image.fromarray(np.clip(tira, 0, 255).astype(np.uint8)).resize((512, 512), Image.LANCZOS)
    # borra so na horizontal: some a listra fina, ficam as manchas e escorrimentos verticais
    a = np.asarray(im).astype(np.float32)
    k = 17
    pad = np.concatenate([a[:, -k:], a, a[:, :k]], axis=1)
    cs = np.cumsum(pad, axis=1)
    a = (cs[:, 2 * k:] - cs[:, :-2 * k])[:, :512] / (2 * k)
    # manchas de liquen/oxidacao e granulado da pedra
    rng = np.random.default_rng(3)
    blot = np.asarray(Image.fromarray((rng.random((32, 32)) * 255).astype(np.uint8)).resize((512, 512), Image.BICUBIC)).astype(np.float32) / 255
    fine = np.asarray(Image.fromarray((rng.random((128, 128)) * 255).astype(np.uint8)).resize((512, 512), Image.BICUBIC)).astype(np.float32) / 255
    a *= (0.80 + 0.30 * blot)[..., None] * (0.92 + 0.12 * fine)[..., None]
    a += (rng.random(a.shape[:2]) - 0.5)[..., None] * 14
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(out)
    return out


class _Mesh:
    def __init__(self, name):
        self.vd = GeomVertexData(name, GeomVertexFormat.getV3n3t2(), Geom.UHStatic)
        self.vw = GeomVertexWriter(self.vd, "vertex")
        self.nw = GeomVertexWriter(self.vd, "normal")
        self.tw = GeomVertexWriter(self.vd, "texcoord")
        self.tris = GeomTriangles(Geom.UHStatic)
        self.n = 0
        self.name = name

    def v(self, p, n, uv):
        self.vw.addData3(*p)
        nn = Vec3(*n)
        if nn.length() > 1e-9:
            nn.normalize()
        self.nw.addData3(nn)
        self.tw.addData2(*uv)
        self.n += 1
        return self.n - 1

    def tri(self, a, b, c):
        self.tris.addVertices(a, b, c)

    def node(self):
        g = Geom(self.vd)
        g.addPrimitive(self.tris)
        gn = GeomNode(self.name)
        gn.addGeom(g)
        return NodePath(gn)


def _box(m, cx, cy, z0, sx, sy, sz, rnd=None, chip=0.0):
    """Bloco (laje do capitel ou plinto). chip > 0 lasca os cantos de cima ao acaso."""
    xs = (cx - sx / 2, cx + sx / 2)
    ys = (cy - sy / 2, cy + sy / 2)
    zs = (z0, z0 + sz)

    def corner(ix, iy, iz):
        x, y, z = xs[ix], ys[iy], zs[iz]
        if rnd and iz == 1 and chip > 0:
            z -= rnd.uniform(0, chip)
            x += rnd.uniform(-chip, chip) * 0.5
            y += rnd.uniform(-chip, chip) * 0.5
        return (x, y, z)

    P = {(ix, iy, iz): corner(ix, iy, iz) for ix in (0, 1) for iy in (0, 1) for iz in (0, 1)}
    faces = [((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1), (0, -1, 0)),
             ((1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1), (0, 1, 0)),
             ((0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1), (-1, 0, 0)),
             ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1), (1, 0, 0)),
             ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1), (0, 0, 1)),
             ((0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0), (0, 0, -1))]
    for a, b, c, d, n in faces:
        ia = m.v(P[a], n, (0, 0.02))
        ib = m.v(P[b], n, (0.35, 0.02))
        ic = m.v(P[c], n, (0.35, 0.14))
        idd = m.v(P[d], n, (0, 0.14))
        m.tri(ia, ib, ic)
        m.tri(ia, ic, idd)


def _lathe(m, profile, seg, flutes, flute_rng, depth, cut=None, u_rep=2.0, v0=0.0, v1=1.0):
    """Superficie de revolucao. cut=(inclinacao, ruido, semente) corta o topo em diagonal."""
    rnd = random.Random(cut[2]) if cut else None
    zmin, zmax = profile[0][1], profile[-1][1]
    base = m.n
    rows = len(profile)
    noise = [rnd.uniform(-cut[1], cut[1]) for _ in range(seg + 1)] if cut else None
    if cut:
        noise[-1] = noise[0]
    for j, (r, z) in enumerate(profile):
        zp = profile[max(0, j - 1)]
        zn = profile[min(rows - 1, j + 1)]
        dz, dr = zn[1] - zp[1], zn[0] - zp[0]
        fl = flutes and flute_rng[0] <= z <= flute_rng[1]

        def rad(th):
            if not fl:
                return r
            return r * (1 - depth * (0.5 + 0.5 * math.cos(flutes * th)) ** 1.5)

        for i in range(seg + 1):
            th = 2 * math.pi * i / seg
            c, s = math.cos(th), math.sin(th)
            rr = rad(th)
            e = 1e-3
            drt = (rad(th + e) - rad(th - e)) / (2 * e)            # inclinacao da canelura
            # normal = tangente(theta) x tangente(z): considera o sulco
            tx, ty = drt * c - rr * s, drt * s + rr * c
            nx, ny = ty * dz, -tx * dz
            nz = -dr * rr
            zz = z
            if cut and j == rows - 1:
                zz = z + cut[0] * c * r + noise[i]
            m.v((rr * c, rr * s, zz), (nx, ny, nz), (i / seg * u_rep, v0 + (v1 - v0) * (z - zmin) / max(1e-6, zmax - zmin)))
    for j in range(rows - 1):
        for i in range(seg):
            a = base + j * (seg + 1) + i
            b = a + seg + 1
            m.tri(a, a + 1, b)
            m.tri(a + 1, b + 1, b)
    if cut:   # tampa do corte
        top0 = base + (rows - 1) * (seg + 1)
        r_top, z_top = profile[-1]
        center = m.v((0, 0, z_top), (0, 0, 1), (0.5, 0.95))
        ring = []
        for i in range(seg + 1):
            th = 2 * math.pi * i / seg
            c, s = math.cos(th), math.sin(th)
            rr = r_top * (1 - depth * (0.5 + 0.5 * math.cos(flutes * th)) ** 1.5)
            ring.append(m.v((rr * c, rr * s, z_top + cut[0] * c * r_top + noise[i]),
                            (-cut[0] * 0.3, 0, 1), (0.5 + 0.4 * c, 0.45 + 0.1 * s)))
        for i in range(seg):
            m.tri(center, ring[i], ring[i + 1])


def make_column(h=4.0, broken=False, seed=0, radius=0.44):
    rnd = random.Random(seed)
    m = _Mesh("coluna")
    r = radius
    # plinto quadrado + toro (base)
    _box(m, 0, 0, 0.0, r * 2.7, r * 2.7, 0.22, rnd, chip=0.03)
    base = [(r * 1.28, 0.22), (r * 1.30, 0.28), (r * 1.22, 0.36), (r * 1.08, 0.40), (r * 1.10, 0.46),
            (r * 1.02, 0.52), (r, 0.58)]
    _lathe(m, base, 40, 0, (0, 0), 0, v0=0.0, v1=0.06)
    shaft_top = h if broken else h - 0.62
    shaft = [(r * (1.0 - 0.10 * t + 0.02 * math.sin(math.pi * t)), 0.58 + t * (shaft_top - 0.58))
             for t in [k / 16 for k in range(17)]]
    cut = (rnd.uniform(0.30, 0.60) * rnd.choice((-1, 1)), 0.015, seed) if broken else None
    _lathe(m, shaft, 96, 18, (0.6, shaft_top + 1), 0.15, cut=cut, u_rep=2.0, v0=0.05, v1=0.98 * (shaft_top / 4.4) + 0.05)
    if not broken:
        rt = shaft[-1][0]
        # equino (anel que se abre) + laje quadrada lascada
        echinus = [(rt, h - 0.62), (rt * 1.02, h - 0.56), (rt * 1.08, h - 0.52), (rt * 1.20, h - 0.44),
                   (rt * 1.32, h - 0.36), (rt * 1.36, h - 0.32)]
        _lathe(m, echinus, 40, 0, (0, 0), 0, v0=0.90, v1=0.97)
        s_ = rt * 2.9 * rnd.uniform(0.95, 1.05)
        _box(m, 0, 0, h - 0.32, s_, s_, 0.30, rnd, chip=0.07)
    return m.node()
