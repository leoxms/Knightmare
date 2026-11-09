# -*- coding: utf-8 -*-
"""
Lamina da Aurora 3D - prototipo em Panda3D (Python).

Cena 3D de verdade: estrada de terra com calcamento, grama, colunas jonicas
modeladas por codigo, arvores, ceu nublado, sombras e nevoa. O cavaleiro e um
modelo 3D (GLB). Os monstros ainda sao "cartoes" 2D ate ganharem modelos 3D.

Controles: A/D ou setas = desviar | Espaco ou clique = atacar | Esc = sair
"""
import math
import os
import random
import sys

from panda3d.core import loadPrcFileData

AQUI = os.path.dirname(os.path.abspath(__file__))
ARTE = os.path.join(AQUI, "arte")
MODELOS = os.path.join(AQUI, "modelos")
TEST = bool(os.environ.get("LAMINA_TESTE"))

cfg = """window-title Lamina da Aurora 3D
win-size 1280 720
sync-video true
framebuffer-multisample true
multisamples 4
audio-library-name null
textures-power-2 none
"""
if TEST:
    cfg += "window-type offscreen\n"
loadPrcFileData("", cfg)

import numpy as np                                     # noqa: E402
from PIL import Image                                  # noqa: E402
from direct.showbase.ShowBase import ShowBase          # noqa: E402
from direct.gui.OnscreenText import OnscreenText       # noqa: E402
from panda3d.core import (AmbientLight, CardMaker, DirectionalLight, Filename, Fog, Geom,  # noqa: E402
                          GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter,
                          NodePath, SamplerState, TextNode, Texture, TextureStage, TransparencyAttrib,
                          Vec3, Vec4)
import simplepbr                                       # noqa: E402

ROAD_W = 3.2
WALK_LIM = ROAD_W + 0.8
SPEED = float(os.environ.get("LAMINA_VELOCIDADE", "0.7")) * 4.2
STRAFE = 4.0
CAM_BACK, CAM_UP = 6.5, 3.4
VIEW = 140.0


def fn(path):
    return Filename.fromOsSpecific(path)


# ----------------------------------------------------------------------------
# texturas preparadas uma vez (cache em arte/)
# ----------------------------------------------------------------------------
def build_road_texture():
    """Estrada 8 m x 3 m com bordas irregulares (alfa) que emendam ao repetir."""
    out = os.path.join(ARTE, "estrada_borda.png")
    if os.path.exists(out):
        return out
    src = Image.open(os.path.join(ARTE, "estrada.png")).convert("RGB").resize((768, 768), Image.LANCZOS)
    Wp, Hp = 2048, 768
    tile = Image.new("RGB", (Wp, Hp))
    for x in range(0, Wp, 768):
        tile.paste(src, (x, 0))
    rng = np.random.default_rng(3)
    v = np.arange(Hp) / Hp

    def edge(seed):
        r = np.random.default_rng(seed)
        ph = r.uniform(0, 6.28, 5)
        return sum(a * np.sin(2 * np.pi * v * k + p) for a, k, p in zip((0.30, 0.18, 0.10, 0.06, 0.04), (1, 2, 5, 11, 23), ph))

    xm = (np.arange(Wp) / Wp - 0.5) * 8.0
    left = -(ROAD_W + edge(1))[:, None]
    right = (ROAD_W + edge(2))[:, None]
    d = np.minimum(xm[None, :] - left, right - xm[None, :])
    a = np.clip(d / 0.25 + 0.5, 0, 1)
    a *= np.clip(1 - (rng.random((Hp, Wp)) < 0.35 * (1 - np.clip(d / 0.35, 0, 1))), 0, 1)
    rgba = np.dstack([np.asarray(tile), (a * 255).astype(np.uint8)])
    Image.fromarray(rgba, "RGBA").save(out)
    return out


def build_marble_texture():
    """Marmore procedural: base creme com veios cinza e manchas de desgaste (emenda ao repetir)."""
    out = os.path.join(ARTE, "marmore4.png")
    if os.path.exists(out):
        return out
    rng = np.random.default_rng(11)
    W_, H_ = 256, 512

    def noise(cells_x, cells_y, seed):
        g = np.random.default_rng(seed).random((cells_y, cells_x))
        ys = np.arange(H_) * cells_y / H_
        xs = np.arange(W_) * cells_x / W_
        y0, x0 = ys.astype(int), xs.astype(int)
        fy, fx = ys - y0, xs - x0
        fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
        y1, x1 = (y0 + 1) % cells_y, (x0 + 1) % cells_x
        a_ = g[y0][:, x0] * (1 - fx) + g[y0][:, x1] * fx
        b_ = g[y1][:, x0] * (1 - fx) + g[y1][:, x1] * fx
        return a_ * (1 - fy)[:, None] + b_ * fy[:, None]

    n = sum(noise(4 * k, 8 * k, k) / k for k in (1, 2, 4, 8))
    yy, xx = np.mgrid[0:H_, 0:W_]
    veio = np.abs(np.sin((xx / W_ * 2 + yy / H_ * 3) * np.pi + n * 6.0)) ** 0.25
    mancha = noise(6, 12, 99)
    base = np.array([226, 214, 190], np.float32)
    col = base[None, None, :] * (0.80 + 0.20 * veio[..., None]) * (0.88 + 0.12 * mancha[..., None])
    col -= (1 - veio[..., None]) * np.array([30, 30, 26])
    col += (rng.random((H_, W_, 1)) - 0.5) * 10
    # desgaste: sujeira subindo da base e escorrimentos
    t = np.linspace(1, 0, H_)[:, None]
    suj = noise(10, 6, 77)
    escorre = noise(24, 3, 78) ** 3
    k = np.clip(0.38 * t ** 1.8 + 0.25 * escorre + 0.18 * (suj - 0.5), 0, 0.5)
    col = col * (1 - k[..., None]) + np.array([62, 58, 48]) * k[..., None]
    col *= (0.92 + 0.16 * noise(5, 9, 79))[..., None]
    Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).save(out)
    return out


def build_glow_texture():
    out = os.path.join(ARTE, "brilho.png")
    if os.path.exists(out):
        return out
    y, x = np.mgrid[0:128, 0:128]
    d = np.sqrt((x - 63.5) ** 2 + (y - 63.5) ** 2) / 64
    f = np.clip(1 - d, 0, 1) ** 2
    rgba = np.dstack([np.full_like(f, 255), np.full_like(f, 255), np.full_like(f, 255), f * 255]).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(out)
    return out


# ----------------------------------------------------------------------------
# geometria procedural
# ----------------------------------------------------------------------------
def lathe(name, profile, seg=40, flutes=0, flute_range=(0, 0), flute_depth=0.06, u_rep=2.0):
    """Superficie de revolucao. profile = [(raio, z), ...] de baixo para cima."""
    fmt = GeomVertexFormat.getV3n3t2()
    vd = GeomVertexData(name, fmt, Geom.UHStatic)
    vw, nw, tw = GeomVertexWriter(vd, "vertex"), GeomVertexWriter(vd, "normal"), GeomVertexWriter(vd, "texcoord")
    zmax = max(z for _, z in profile)
    for j, (r, z) in enumerate(profile):
        z0 = profile[max(0, j - 1)][1]
        z1 = profile[min(len(profile) - 1, j + 1)][1]
        r0 = profile[max(0, j - 1)][0]
        r1 = profile[min(len(profile) - 1, j + 1)][0]
        dz, dr = z1 - z0, r1 - r0
        for i in range(seg + 1):
            th = 2 * math.pi * i / seg
            rr = r
            if flutes and flute_range[0] <= z <= flute_range[1]:
                rr = r * (1 - flute_depth * abs(math.cos(flutes * th / 2)) ** 0.5)
            c, s = math.cos(th), math.sin(th)
            vw.addData3(rr * c, rr * s, z)
            n = Vec3(c * dz, s * dz, -dr)
            if n.length() < 1e-6:
                n = Vec3(0, 0, 1 if j == len(profile) - 1 else -1)
            n.normalize()
            nw.addData3(n)
            tw.addData2(i / seg * u_rep, z / zmax)
    tris = GeomTriangles(Geom.UHStatic)
    for j in range(len(profile) - 1):
        for i in range(seg):
            a = j * (seg + 1) + i
            b = a + seg + 1
            tris.addVertices(a, b, a + 1)
            tris.addVertices(a + 1, b, b + 1)
    g = Geom(vd)
    g.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(g)
    return NodePath(node)


def make_column(h=4.4, broken=False, seed=0, radius=0.36):
    """Coluna classica. broken=True: fuste partido com topo irregular (sem capitel)."""
    rnd = random.Random(seed)
    r0 = radius
    p = [(0.0, 0.0), (r0 + 0.22, 0.0), (r0 + 0.22, 0.16), (r0 + 0.14, 0.20), (r0 + 0.10, 0.27),
         (r0 + 0.04, 0.31), (r0 + 0.01, 0.36), (r0, 0.40)]
    top = h - 1.0 if not broken else h
    n = 14
    for k in range(n + 1):
        t = k / n
        z = 0.40 + t * (top - 0.40)
        p.append((r0 - 0.06 * t + 0.015 * math.sin(math.pi * t), z))   # entase
    if not broken:
        p += [(r0 - 0.03, h - 0.55), (r0 + 0.04, h - 0.45), (r0 + 0.14, h - 0.32), (r0 + 0.20, h - 0.26),
              (r0 + 0.26, h - 0.22), (r0 + 0.26, h - 0.05), (0.0, h)]
        return lathe("coluna", p, seg=48, flutes=20, flute_range=(0.4, h - 0.6), u_rep=3.0)
    col = lathe("coluna_quebrada", p, seg=48, flutes=20, flute_range=(0.4, h), u_rep=3.0)
    # tampa irregular: leque de triangulos com alturas aleatorias (pedra partida)
    fmt = GeomVertexFormat.getV3n3t2()
    vd = GeomVertexData("topo", fmt, Geom.UHStatic)
    vw, nw, tw = GeomVertexWriter(vd, "vertex"), GeomVertexWriter(vd, "normal"), GeomVertexWriter(vd, "texcoord")
    rr = r0 - 0.06
    vw.addData3(0, 0, h + rnd.uniform(-0.15, 0.10))
    nw.addData3(0, 0, 1)
    tw.addData2(0.5, 1)
    seg = 48
    for i in range(seg + 1):
        th = 2 * math.pi * i / seg
        zz = h + 0.18 * math.sin(th * 2 + seed) + rnd.uniform(-0.12, 0.12)
        vw.addData3(rr * math.cos(th), rr * math.sin(th), zz)
        nw.addData3(0, 0, 1)
        tw.addData2(0.5 + 0.5 * math.cos(th), 0.5 + 0.5 * math.sin(th))
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(seg):
        tris.addVertices(0, i + 1, i + 2)
    g = Geom(vd)
    g.addPrimitive(tris)
    gn = GeomNode("topo")
    gn.addGeom(g)
    topo = NodePath(gn)
    topo.reparentTo(col)
    topo.setColorScale(0.62, 0.58, 0.52, 1)
    return col


def build_tuft_texture():
    out = os.path.join(ARTE, "tufo.png")
    if os.path.exists(out):
        return out
    from PIL import ImageDraw
    rnd = random.Random(5)
    im = Image.new("RGBA", (256, 192), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for _ in range(110):
        x0 = rnd.uniform(20, 236)
        hgt = rnd.uniform(60, 185)
        lean = rnd.uniform(-40, 40)
        c = rnd.choice([(52, 78, 34), (64, 92, 40), (42, 64, 28), (78, 100, 46), (90, 98, 52)])
        w = rnd.uniform(2, 5)
        d.polygon([(x0 - w, 192), (x0 + w, 192), (x0 + lean, 192 - hgt)], fill=c + (255,))
    im.save(out)
    return out


def build_vignette_texture():
    out = os.path.join(ARTE, "vinheta.png")
    if os.path.exists(out):
        return out
    y, x = np.mgrid[0:360, 0:640]
    dd = np.sqrt(((x - 320) / 320.0) ** 2 + ((y - 180) / 180.0) ** 2)
    a = (np.clip((dd - 0.55) / 0.75, 0, 1) ** 1.7 * 200).astype(np.uint8)
    rgba = np.dstack([np.zeros_like(a), np.zeros_like(a), np.zeros_like(a), a])
    Image.fromarray(rgba, "RGBA").save(out)
    return out


# ----------------------------------------------------------------------------
class Jogo(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        self.disableMouse()
        self.pipeline = simplepbr.init(enable_shadows=True, enable_fog=True, msaa_samples=0 if TEST else 4,
                                       exposure=-0.6, max_lights=4)
        self.camLens.setFov(58)
        self.camLens.setNearFar(0.3, 400)
        self.setBackgroundColor(0.44, 0.47, 0.52, 1)
        self.keys = {}
        for k in ("a", "d", "w", "s", "arrow_left", "arrow_right", "arrow_up", "arrow_down", "space", "mouse1"):
            self.accept(k, self.keys.__setitem__, [k, True])
            self.accept(k + "-up", self.keys.__setitem__, [k, False])
        self.accept("escape", sys.exit)
        self.px, self.py, self.pvx = 0.0, 0.0, 0.0
        self.walk = 0.0
        self.t = 0.0
        self.fire_cd = 0.0
        self.score = 0
        self.hp = 6
        self.enemies, self.shots = [], []
        self.spawn_t = 1.5
        self.build_textures()
        self.build_lights()
        self.build_sky()
        self.build_ground()
        self.figura = None
        self.golpe_path = os.path.join(AQUI, "mixamo", "baixados", "golpe.glb")
        self.has_golpe = os.path.exists(self.golpe_path)
        self.next_golpe_y = 18.0
        # figura do Mixamo convertida para GLB (o leitor de FBX do Panda3D quebra a deformacao do corpo)
        fig = os.environ.get("LAMINA_FIGURA") or os.path.join(AQUI, "mixamo", "baixados", "andar.glb")
        if os.path.exists(fig) and os.environ.get("LAMINA_FIGURA", "1") != "0":
            self.build_figure(fig)
        else:
            self.build_knight()
        self.scenery = {}
        self.hud = OnscreenText(text="", pos=(-1.72, 0.92), scale=0.06, fg=(1, 0.95, 0.8, 1),
                                shadow=(0, 0, 0, 0.8), align=TextNode.ALeft, mayChange=True)
        self.taskMgr.add(self.update, "update")

    # ------------------------------------------------------------ recursos
    def tex(self, path, repeat=True):
        t = self.loader.loadTexture(fn(path))
        t.setMinfilter(SamplerState.FT_linear_mipmap_linear)
        t.setMagfilter(SamplerState.FT_linear)
        t.setAnisotropicDegree(8)
        if not repeat:
            t.setWrapU(SamplerState.WM_clamp)
            t.setWrapV(SamplerState.WM_clamp)
        return t

    def build_textures(self):
        terra = os.path.join(ARTE, "estrada_terra.png")
        self.road_len = 12.0 if os.path.exists(terra) else 3.0
        self.t_road = self.tex(terra if os.path.exists(terra) else build_road_texture())
        self.t_tuft = self.tex(build_tuft_texture(), False)
        self.t_vig = self.tex(build_vignette_texture(), False)
        self.t_grass = self.tex(os.path.join(ARTE, "grama.png"))
        self.t_marble = self.tex(build_marble_texture())
        self.t_glow = self.tex(build_glow_texture(), False)
        self.t_sky = self.tex(os.path.join(ARTE, "ceu.png"), False)
        self.sprites = {}
        for name in ("carvalho", "cipreste", "morcego", "gosma", "cristal", "chefe"):
            self.sprites[name] = self.tex(os.path.join(ARTE, name + ".png"), False)
        self.esq_frames = [self.tex(os.path.join(ARTE, "esq_andar_%d.png" % k), False) for k in range(8)]

    def build_lights(self):
        amb = AmbientLight("amb")
        amb.setColor(Vec4(0.30, 0.32, 0.36, 1))
        self.render.setLight(self.render.attachNewNode(amb))
        sun = DirectionalLight("sol")
        sun.setColor(Vec4(2.5, 2.35, 2.15, 1))
        sun.setShadowCaster(True, 2048, 2048)
        lens = sun.getLens()
        lens.setFilmSize(36, 36)
        lens.setNearFar(1, 80)
        self.sun = self.render.attachNewNode(sun)
        self.sun.setHpr(35, -55, 0)
        self.render.setLight(self.sun)
        fog = Fog("nevoa")
        fog.setColor(0.44, 0.47, 0.52)
        fog.setExpDensity(0.0042)
        self.render.setFog(fog)

    def build_sky(self):
        cm = CardMaker("ceu")
        cm.setFrame(-420, 420, -60, 300)
        sky = self.camera.attachNewNode(cm.generate())
        sky.setPos(0, 380, 0)
        sky.setTexture(self.t_sky)
        sky.setBin("background", 0)
        sky.setDepthWrite(False)
        sky.setLightOff(1)
        sky.setFogOff(1)
        sky.setShaderOff(1)
        sky.setP(14)
        sky.setColorScale(0.78, 0.80, 0.86, 1)
        self.sky = sky

    def build_ground(self):
        cm = CardMaker("grama")
        cm.setFrame(-150, 150, -60, VIEW + 60)
        self.grass = self.render.attachNewNode(cm.generate())
        self.grass.setP(-90)
        self.grass.setTexture(self.t_grass)
        self.grass.setColorScale(0.72, 0.82, 0.62, 1)
        self.grass.setTexScale(TextureStage.getDefault(), 300 / 5.0, (VIEW + 120) / 5.0)
        cm = CardMaker("estrada")
        cm.setFrame(-4, 4, -30, VIEW + 30)
        self.road = self.render.attachNewNode(cm.generate())
        self.road.setP(-90)
        self.road.setZ(0.02)
        self.road.setTexture(self.t_road)
        self.road.setTexScale(TextureStage.getDefault(), 1, (VIEW + 60) / self.road_len)
        self.road.setTransparency(TransparencyAttrib.MAlpha)
        self.road.setColorScale(0.70, 0.60, 0.50, 1)
        self.road.setDepthOffset(1)
        import colunas3d
        self.t_pedra = self.tex(colunas3d.build_stone_texture(ARTE))
        self.column_models = []
        # proporcoes da referencia: fuste grosso, alturas variadas, quebradas com corte inclinado
        for i, (hh, br) in enumerate(((3.9, False), (4.4, False), (3.5, False), (4.8, False),
                                      (2.2, True), (1.6, True), (2.7, True), (1.2, True))):
            cm_ = colunas3d.make_column(hh, broken=br, seed=i, radius=0.44 if not br else 0.42)
            cm_.setTexture(self.t_pedra)
            self.column_models.append((cm_, br))
        self.column_model = self.column_models[0][0]
        from direct.gui.OnscreenImage import OnscreenImage
        vig = OnscreenImage(image=self.t_vig, pos=(0, 0, 0), scale=(self.getAspectRatio(), 1, 1))
        vig.setTransparency(TransparencyAttrib.MAlpha)
        from panda3d.core import Material
        mat = Material("marmore")
        mat.setBaseColor((1, 1, 1, 1))
        mat.setRoughness(0.92)
        mat.setMetallic(0.0)
        for cm_, _ in self.column_models:
            cm_.setMaterial(mat, 1)

    def build_knight(self):
        from boneco3d import Boneco
        pivot = self.render.attachNewNode("cavaleiro")
        m = self.loader.loadModel(fn(os.path.join(MODELOS, "cavaleiro.glb")))
        for mat in m.findAllMaterials():
            mat.setMetallic(0.55)
            mat.setRoughness(0.38)
        # juntas de quadril e joelho (coordenadas do modelo: z de -0.5 a 0.5, frente para -Y)
        self.boneco = Boneco(m, {"E": (-0.17, -0.015), "D": (0.015, 0.135)}, hip_z=-0.17, knee_z=-0.33)
        body = self.boneco.root
        a, b = body.getTightBounds()
        s = 1.3 / (b - a).z
        holder = pivot.attachNewNode("corpo")
        holder.setH(180)            # o modelo olha para -Y; viramos de costas para a camera
        body.reparentTo(holder)
        body.setScale(s)
        body.setPos(-(a.x + b.x) / 2 * s, -(a.y + b.y) / 2 * s, -a.z * s)
        self.knight, self.knight_body = pivot, holder

    def build_figure(self, path):
        """Personagem do Mixamo (FBX com esqueleto e animacao de captura de movimento)."""
        from direct.actor.Actor import Actor
        m = self.loader.loadModel(fn(path))
        actor = Actor(m)
        self.fig_anims = actor.getAnimNames()
        ctrl = actor.getAnimControl(self.fig_anims[0])
        self.fig_frames = ctrl.getNumFrames()
        pivot = self.render.attachNewNode("figura")
        holder = pivot.attachNewNode("corpo")
        actor.reparentTo(holder)
        if path.lower().endswith(".fbx"):
            actor.setP(90)           # FBX do Mixamo e Y-up (o leitor glTF ja converte para Z-up)
        holder.setH(180)             # de costas para a camera, andando para +Y
        actor.pose(self.fig_anims[0], 0)
        a, b = actor.getTightBounds()
        self.fig_scale = 1.75 / max(1e-6, (b - a).z)
        actor.setScale(self.fig_scale)
        a, b = actor.getTightBounds()
        actor.setZ(-a.z)
        self.hips = actor.exposeJoint(None, "modelRoot", "mixamorig:Hips")
        actor.setColorScale(0.72, 0.82, 1.15, 1)    # heroi prateado-azulado (inimigos sao vermelhos)
        self.fig_actor, self.knight, self.knight_body = actor, pivot, holder
        self.boneco = None
        self.fig_root0 = None

    # ------------------------------------------------------------ cenario
    def card(self, tex, w, h, parent=None):
        cm = CardMaker("cartao")
        cm.setFrame(-w / 2, w / 2, 0, h)
        np_ = (parent or self.render).attachNewNode(cm.generate())
        np_.setTexture(tex)
        np_.setTransparency(TransparencyAttrib.MBinary)
        np_.setBillboardAxis()
        np_.setTwoSided(True)
        return np_

    def sprite_card(self, name, h):
        t = self.sprites[name]
        w = h * t.getXSize() / t.getYSize()
        return self.card(t, w, h)

    def tuft_clump(self, parent, x, y, h):
        cm = CardMaker("tufo")
        w = h * 1.33
        cm.setFrame(-w / 2, w / 2, 0, h)
        for ang in (0, 60, 120):
            c = parent.attachNewNode(cm.generate())
            c.setPos(x, y, 0)
            c.setH(ang)
            c.setTexture(self.t_tuft)
            c.setTransparency(TransparencyAttrib.MBinary)
            c.setTwoSided(True)

    def segment(self, n):
        """Trecho de 2 m: colunas desalinhadas e variadas (inteiras e quebradas), carvalhos
        perto da via, ciprestes atras e tufos de grama na beira."""
        rnd = random.Random(n * 7919)
        y = n * 2.0
        nodes = []
        for side in (-1, 1):
            if rnd.random() < 0.34:
                model, broken = rnd.choice(self.column_models + self.column_models[:4])
                c = model.copyTo(self.render)
                c.setPos(side * (ROAD_W + rnd.uniform(1.4, 3.6)), y + rnd.uniform(0, 2), 0)
                c.setH(rnd.uniform(0, 360))
                c.setR(rnd.uniform(-2.0, 2.0))
                c.setP(rnd.uniform(-1.5, 1.5))
                tom = rnd.uniform(0.85, 1.12)
                c.setColorScale(tom, tom * rnd.uniform(0.96, 1.0), tom * rnd.uniform(0.88, 0.97), 1)
                c.setScale(rnd.uniform(0.9, 1.1))
                nodes.append(c)
            if rnd.random() < 0.26:
                t = self.sprite_card("carvalho", rnd.uniform(7.5, 10.5))
                t.setPos(side * (ROAD_W + rnd.uniform(4.5, 8.0)), y + rnd.random() * 2, 0)
                t.setColorScale(0.78, 0.82, 0.76, 1)
                nodes.append(t)
            if rnd.random() < 0.12:
                t = self.sprite_card("cipreste", rnd.uniform(8.0, 11.0))
                t.setPos(side * (ROAD_W + rnd.uniform(7.0, 11.0)), y + rnd.random() * 2, 0)
                t.setColorScale(0.75, 0.80, 0.74, 1)
                nodes.append(t)
            if rnd.random() < 0.5:
                k = "carvalho" if rnd.random() < 0.65 else "cipreste"
                t = self.sprite_card(k, rnd.uniform(8, 12))
                t.setPos(side * (ROAD_W + rnd.uniform(12, 32)), y + rnd.random() * 2, 0)
                t.setColorScale(0.72, 0.76, 0.72, 1)
                nodes.append(t)
        tufos = self.render.attachNewNode("tufos")
        for _ in range(5):
            side = rnd.choice((-1, 1))
            self.tuft_clump(tufos, side * (ROAD_W + rnd.uniform(-0.2, 3.5)), y + rnd.uniform(0, 2),
                            rnd.uniform(0.25, 0.55))
        tufos.setColorScale(1.0, 1.08, 0.92, 1)
        tufos.flattenStrong()
        nodes.append(tufos)
        return nodes

    def update_scenery(self):
        base = int(self.py // 2.0) - 4
        want = set(range(base, base + int(VIEW / 2.0)))
        for n in list(self.scenery):
            if n not in want:
                for nd in self.scenery.pop(n):
                    nd.removeNode()
        for n in want:
            if n not in self.scenery:
                self.scenery[n] = self.segment(n)

    # ------------------------------------------------------------ inimigos
    def spawn_golpeador(self, y):
        """Inimigo com duas animacoes do Mixamo (mesmo esqueleto): caminhar e golpear."""
        from direct.actor.Actor import Actor
        andar = os.path.join(AQUI, "mixamo", "baixados", "andar.glb")
        actor = Actor(self.loader.loadModel(fn(self.golpe_path)),
                      {"golpe": fn(self.golpe_path), "andar": fn(andar)})
        nf = {k: actor.getAnimControl(k).getNumFrames() for k in ("golpe", "andar")}
        actor.reparentTo(self.render)
        actor.setScale(1.75 / 1.81)
        actor.setColorScale(1.0, 0.55, 0.5, 1)      # tom avermelhado: inimigo
        x = random.uniform(-ROAD_W + 0.9, ROAD_W - 0.9)
        actor.setPos(x, y, 0)
        hips = actor.exposeJoint(None, "modelRoot", "mixamorig:Hips")
        holder = self.render.attachNewNode("inimigo")
        actor.reparentTo(holder)
        holder.setPos(x, y, 0)
        actor.setPos(0, 0, 0)
        e = dict(kind="golpeador", node=holder, actor=actor, hips=hips, root0=None, x=x, y=y, z=0.0,
                 hp=4, r=0.6, t=0.0, nf=nf, state="andar", st_t=random.uniform(0, 1.0), hit_done=False,
                 v=random.uniform(1.0, 1.4))
        self.enemies.append(e)

    def update_golpeador(self, e, dt):
        dx, dy = self.px - e["x"], self.py - e["y"]
        dist = math.hypot(dx, dy)
        e["st_t"] += dt
        if e["state"] == "andar":
            if dist < 1.5:
                e["state"], e["st_t"], e["hit_done"] = "golpe", 0.0, False
            else:
                step = e["v"] * dt
                e["x"] += dx / dist * step
                e["y"] += dy / dist * step
        if e["state"] == "golpe":
            dur = e["nf"]["golpe"] / 30.0
            if not e["hit_done"] and e["st_t"] > dur * 0.48:      # momento em que a lamina desce
                e["hit_done"] = True
                if dist < 1.8:
                    self.hp = max(0, self.hp - 1)
                    self.hit_flash = 0.25
            if e["st_t"] >= dur:
                e["state"], e["st_t"] = ("golpe", 0.0) if dist < 1.6 else ("andar", 0.0)
                e["hit_done"] = False
        anim = e["state"]
        frame = (e["st_t"] * 30.0) % e["nf"][anim] if anim == "andar" else min(e["st_t"] * 30.0, e["nf"][anim] - 1)
        e["actor"].pose(anim, frame)
        # cancela o deslocamento do quadril da animacao (andar no lugar; quem move e o codigo)
        hp = e["hips"].getPos(e["node"])
        if e["root0"] is None:
            e["root0"] = hp
        e["actor"].setX(e["actor"].getX() - (hp.x - e["root0"].x))
        e["actor"].setY(e["actor"].getY() - (hp.y - e["root0"].y))
        e["node"].setPos(e["x"], e["y"], 0)
        e["node"].setH(math.degrees(math.atan2(dx, -dy)))       # sempre de frente para o cavaleiro
        if dist > 70:
            e["hp"] = 0

    def spawn(self):
        kind = random.choice(("esqueleto", "esqueleto", "morcego", "gosma"))
        x = random.uniform(-ROAD_W + 0.6, ROAD_W - 0.6)
        y = self.py + 70
        if kind == "esqueleto":
            nd = self.card(self.esq_frames[0], 1.9 * self.esq_frames[0].getXSize() / self.esq_frames[0].getYSize(), 1.9)
            e = dict(kind=kind, node=nd, x=x, y=y, z=0.0, v=random.uniform(0.8, 1.3), hp=3, r=0.6, t=0.0)
        elif kind == "morcego":
            nd = self.sprite_card("morcego", 1.0)
            e = dict(kind=kind, node=nd, x=x, y=y, z=2.4, v=random.uniform(2.0, 2.8), hp=1, r=0.7, t=0.0)
        else:
            nd = self.sprite_card("gosma", 0.8)
            e = dict(kind=kind, node=nd, x=x, y=y, z=0.0, v=1.2, hp=2, r=0.55, t=random.uniform(0, 3))
        self.enemies.append(e)

    def fire(self):
        h = math.radians(getattr(self, "face_h", 0.0))
        fx, fy = -math.sin(h), math.cos(h)                       # direcao para onde o cavaleiro olha
        target, best = None, 1e9
        for e in self.enemies:
            ex, ey = e["x"] - self.px, e["y"] - self.py
            d = math.hypot(ex, ey)
            if 0.3 < d < 35 and (ex * fx + ey * fy) / d > 0.8 and d < best:
                target, best = e, d
        sx, sy, sz = self.px + fx * 0.5, self.py + fy * 0.5, 0.9
        if target:
            dx, dy, dz = target["x"] - sx, target["y"] - sy, (target["z"] + 0.8) - sz
        else:
            dx, dy, dz = fx * 30.0, fy * 30.0, 0.0
        n = math.sqrt(dx * dx + dy * dy + dz * dz) or 1
        g = self.card(self.t_glow, 0.6, 0.6)
        g.setColorScale(0.25, 0.55, 1.0, 1)
        g.setTransparency(TransparencyAttrib.MAlpha)
        g.setAttrib(__import__("panda3d.core", fromlist=["ColorBlendAttrib"]).ColorBlendAttrib.make(
            __import__("panda3d.core", fromlist=["ColorBlendAttrib"]).ColorBlendAttrib.MAdd))
        g.setDepthWrite(False)
        g.setLightOff(1)
        g.setShaderOff(1)
        g.setFogOff(1)
        self.shots.append(dict(node=g, x=sx, y=sy, z=sz, vx=dx / n * 20, vy=dy / n * 20, vz=dz / n * 20, life=2.5))

    # ------------------------------------------------------------ loop
    def update(self, task):
        dt = min(globalClock.getDt(), 1 / 30) if not TEST else 1 / 60   # noqa: F821
        self.t += dt
        k = self.keys
        if TEST:
            calmo = bool(os.environ.get("LAMINA_SEM_TIRO"))
            ix, iy = (0.0 if calmo else math.sin(self.t * 0.7)), (1.0 if (self.t % 8) < 6 else 0.0)
            fire = not calmo
        else:
            ix = (1 if (k.get("d") or k.get("arrow_right")) else 0) - (1 if (k.get("a") or k.get("arrow_left")) else 0)
            iy = (1 if (k.get("w") or k.get("arrow_up")) else 0) - (1 if (k.get("s") or k.get("arrow_down")) else 0)
            fire = k.get("space") or k.get("mouse1")
        # movimento livre com as setas (velocidade suavizada)
        n = math.hypot(ix, iy)
        tx, ty = (ix / n * SPEED, iy / n * SPEED) if n > 0 else (0.0, 0.0)
        self.pvx += (tx - self.pvx) * min(1, dt * 9)
        self.pvy = getattr(self, "pvy", 0.0)
        self.pvy += (ty - self.pvy) * min(1, dt * 9)
        nx = max(-WALK_LIM, min(WALK_LIM, self.px + self.pvx * dt))
        ny = self.py + self.pvy * dt
        for e in self.enemies:                                    # nao atravessa os inimigos
            if e["kind"] == "golpeador" and e["hp"] > 0 and math.hypot(nx - e["x"], ny - e["y"]) < 0.85:
                if math.hypot(nx - e["x"], ny - e["y"]) < math.hypot(self.px - e["x"], self.py - e["y"]):
                    nx, ny = self.px, self.py
        self.px, self.py = nx, ny
        speed = math.hypot(self.pvx, self.pvy)
        self.moving = speed > 0.25
        # vira o corpo para onde esta andando
        self.face_h = getattr(self, "face_h", 0.0)
        if self.moving:
            want = math.degrees(math.atan2(-self.pvx, self.pvy))
            diff = (want - self.face_h + 180) % 360 - 180
            self.face_h += diff * min(1, dt * 10)
        self.walk += dt * speed * 2.1
        if self.boneco is not None:
            self.boneco.pose(self.walk, amp=min(1.0, speed / SPEED))
            self.knight.setPos(self.px, self.py, abs(math.cos(self.walk)) * 0.035 * min(1.0, speed / SPEED))
            self.knight.setH(self.face_h)
        else:
            # animacao do Mixamo: avanca so quando anda; parado, volta a postura de pe
            self.fig_t = getattr(self, "fig_t", 0.0)
            if self.moving:
                self.fig_t += dt * (speed / 2.9)
                frame = (self.fig_t * 30.0) % self.fig_frames
            else:
                self.fig_t = 0.0
                frame = 0
            for an in self.fig_anims:
                self.fig_actor.pose(an, frame)
            hp = self.hips.getPos(self.knight_body)
            if self.fig_root0 is None:
                self.fig_root0 = hp
            self.fig_actor.setX(self.fig_actor.getX() - (hp.x - self.fig_root0.x))
            self.fig_actor.setY(self.fig_actor.getY() - (hp.y - self.fig_root0.y))
            self.knight.setPos(self.px, self.py, 0)
            self.knight.setH(self.face_h)
        # camera atras, seguindo suave
        self.cam_x = getattr(self, "cam_x", self.px)
        self.cam_y = getattr(self, "cam_y", self.py)
        self.cam_x += (self.px * 0.7 - self.cam_x) * min(1, dt * 4)
        self.cam_y += (self.py - self.cam_y) * min(1, dt * 4)
        self.camera.setPos(self.cam_x, self.cam_y - CAM_BACK, CAM_UP)
        self.camera.lookAt(self.cam_x + (self.px - self.cam_x) * 0.3, self.cam_y + 8, 0.6)
        self.sun.setPos(self.px, self.py + 8, 0)
        self.grass.setY(math.floor(self.py / 5.0) * 5.0)
        self.road.setY(math.floor(self.py / self.road_len) * self.road_len)
        self.update_scenery()
        # inimigos
        if self.has_golpe:
            vivos = sum(1 for e in self.enemies if e["kind"] == "golpeador")
            while self.next_golpe_y < self.py + 45 and vivos < 5:
                self.spawn_golpeador(self.next_golpe_y)
                self.next_golpe_y += random.uniform(10, 16)
                vivos += 1
        else:
            self.spawn_t -= dt
            if self.spawn_t <= 0:
                self.spawn()
                self.spawn_t = random.uniform(1.4, 2.6)
        for e in self.enemies:
            e["t"] += dt
            if e["kind"] == "golpeador":
                self.update_golpeador(e, dt)
                continue
            if e["kind"] == "esqueleto":
                e["y"] -= e["v"] * dt
                e["x"] += max(-1, min(1, self.px - e["x"])) * 0.5 * dt
                e["node"].setTexture(self.esq_frames[int(e["t"] * 6) % 8], 1)
            elif e["kind"] == "morcego":
                e["y"] -= e["v"] * dt
                e["x"] += math.sin(e["t"] * 1.6) * 1.2 * dt
                e["z"] = 2.2 + math.sin(e["t"] * 6) * 0.15 - (1.0 if e["y"] - self.py < 10 else 0)
                sc = 1.0 if int(e["t"] * 8) % 2 == 0 else 0.65
                e["node"].setSz(sc)
            else:
                hop = abs(math.sin(e["t"] * 2.8))
                e["z"] = hop * 0.8
                if hop > 0.12:
                    e["y"] -= e["v"] * 1.8 * dt
                e["node"].setScale(1.0 + (0.2 if hop < 0.12 else -0.1), 1, 1.0 - (0.25 if hop < 0.12 else -0.15))
            e["node"].setPos(e["x"], e["y"], e["z"])
            if e["y"] - self.py < 0.5:
                if abs(e["x"] - self.px) < e["r"] + 0.4 and e["y"] - self.py > -0.6:
                    self.hp = max(0, self.hp - 1)
                if e["y"] - self.py < -1.5:
                    e["hp"] = 0
        # tiros
        self.fire_cd -= dt
        if fire and self.fire_cd <= 0:
            self.fire()
            self.fire_cd = 0.3
        for s in self.shots:
            s["x"] += s["vx"] * dt
            s["y"] += s["vy"] * dt
            s["z"] += s["vz"] * dt
            s["life"] -= dt
            s["node"].setPos(s["x"], s["y"], s["z"] - 0.3)
            for e in self.enemies:
                if e["hp"] > 0 and (e["x"] - s["x"]) ** 2 + (e["y"] - s["y"]) ** 2 + (e["z"] + 0.8 - s["z"]) ** 2 < (e["r"] + 0.3) ** 2:
                    e["hp"] -= 1
                    s["life"] = 0
                    if e["hp"] <= 0:
                        self.score += 100
                    break
        for lst in (self.shots, self.enemies):
            for o in [o for o in lst if o.get("life", 1) <= 0 or o.get("hp", 1) <= 0]:
                if "actor" in o:
                    o["actor"].cleanup()
                o["node"].removeNode()
                lst.remove(o)
        self.hit_flash = max(0.0, getattr(self, "hit_flash", 0.0) - dt)
        if self.figura is None and hasattr(self, "fig_actor"):
            f = self.hit_flash / 0.25
            self.fig_actor.setColorScale(0.80 + 0.9 * f, 0.88 - 0.5 * f, 1.10 - 0.6 * f, 1)
        self.hud.setText("PONTOS %06d     VIDA %s" % (self.score, "#" * self.hp))
        return task.cont


def main():
    app = Jogo()
    if TEST:
        out = os.environ.get("LAMINA_OUT", os.path.join(AQUI, "capturas3d"))
        os.makedirs(out, exist_ok=True)
        import time
        t0 = time.time()
        frames = int(os.environ.get("LAMINA_FRAMES", "600"))
        shots = {int(x) for x in os.environ.get("LAMINA_SHOTS", "200,400").split(",")}
        for f in range(frames):
            app.taskMgr.step()
            if f in shots:
                app.win.saveScreenshot(fn(os.path.join(out, "q%05d.png" % f)))
        print("quadros=%d tempo=%.1fs pontos=%d" % (frames, time.time() - t0, app.score))
        return
    app.run()


if __name__ == "__main__":
    main()
