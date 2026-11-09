# -*- coding: utf-8 -*-
"""Articula um modelo 3D sem esqueleto: separa a malha em tronco / coxas / canelas pelos
triangulos e cria juntas (quadril e joelho) que podem girar. Usado no cavaleiro 3D.
"""
import math

import numpy as np
from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexReader, NodePath, Point3


def _read(gn):
    geom = gn.getGeom(0)
    state = gn.getGeomState(0)
    vd = geom.getVertexData()
    r = GeomVertexReader(vd, "vertex")
    pts = []
    while not r.isAtEnd():
        v = r.getData3()
        pts.append((v.x, v.y, v.z))
    P = np.array(pts, np.float32)
    prim = geom.getPrimitive(0).decompose()
    n = prim.getNumPrimitives()
    idx = np.empty((n, 3), np.int64)
    for t in range(n):
        s = prim.getPrimitiveStart(t)
        idx[t] = (prim.getVertex(s), prim.getVertex(s + 1), prim.getVertex(s + 2))
    return vd, state, P, idx


def _geom_np(name, vd, state, tris):
    prim = GeomTriangles(Geom.UHStatic)
    for a, b, c in tris:
        prim.addVertices(int(a), int(b), int(c))
    g = Geom(vd)
    g.addPrimitive(prim)
    gn = GeomNode(name)
    gn.addGeom(g, state)
    return NodePath(gn)


class Boneco:
    """legs = {"E": (x0, x1), "D": (x0, x1)}  hip_z, knee_z em coordenadas do modelo."""

    def __init__(self, model_np, legs, hip_z, knee_z):
        model_np.flattenStrong()
        gnp = model_np.find("**/+GeomNode")
        vd, state, P, idx = _read(gnp.node())
        C = P[idx].mean(1)
        part = np.zeros(len(idx), np.int8)            # 0 tronco
        codes = {}
        for k, (side, (x0, x1)) in enumerate(sorted(legs.items())):
            in_leg = (C[:, 2] < hip_z) & (C[:, 0] >= x0) & (C[:, 0] < x1)
            thigh = 1 + 2 * k
            part[in_leg & (C[:, 2] >= knee_z)] = thigh
            part[in_leg & (C[:, 2] < knee_z)] = thigh + 1
            codes[side] = thigh
        self.root = NodePath("boneco")
        _geom_np("tronco", vd, state, idx[part == 0]).reparentTo(self.root)
        self.hips, self.knees = {}, {}
        for side, code in codes.items():
            sel = part == code
            selk = part == code + 1
            pts = P[idx[sel | selk].ravel()]
            cx = float(np.median(pts[:, 0])) if len(pts) else 0.0
            cy = float(np.median(pts[:, 1])) if len(pts) else 0.0
            ph = Point3(cx, cy, hip_z + 0.04)   # pivo acima do corte: a saia cobre a emenda
            pk = Point3(cx, cy, knee_z)
            hip = self.root.attachNewNode("quadril_" + side)
            hip.setPos(ph)
            g = _geom_np("coxa_" + side, vd, state, idx[sel])
            g.reparentTo(hip)
            g.setPos(-ph)
            knee = hip.attachNewNode("joelho_" + side)
            knee.setPos(pk - ph)
            g2 = _geom_np("canela_" + side, vd, state, idx[selk])
            g2.reparentTo(knee)
            g2.setPos(-pk)
            self.hips[side], self.knees[side] = hip, knee
        self.counts = {int(c): int((part == c).sum()) for c in np.unique(part)}

    def pose(self, phase, amp=1.0, front_is_minus_y=True):
        """Ciclo de caminhada. phase em radianos; amp 0 = parado."""
        sgn = 1 if front_is_minus_y else -1
        for side, off in (("E", 0.0), ("D", math.pi)):
            if side not in self.hips:
                continue
            ph = phase + off
            thigh = -19.0 * math.sin(ph) * amp           # negativo = perna para a frente (-Y)
            knee = 34.0 * max(0.0, math.cos(ph)) ** 1.4 * amp   # dobra o joelho na fase de balanco
            self.hips[side].setP(thigh * sgn)
            self.knees[side].setP(knee * sgn)
