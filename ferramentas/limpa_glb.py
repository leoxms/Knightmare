# -*- coding: utf-8 -*-
"""Prepara um GLB vindo do FBX2glTF (Mixamo) para o leitor do Panda3D (panda3d-gltf):

- remove animacoes vazias;
- junta todas as skins numa so: o panda3d-gltf guarda uma skin por raiz, e o Mixamo exporta
  uma skin por malha com a mesma raiz. Os indices de osso (JOINTS_0) das outras malhas sao
  remapeados para a skin principal dentro do proprio binario.

Uso: python limpa_glb.py entrada.glb saida.glb
"""
import json
import struct
import sys

import numpy as np

COMP = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32}


def main(src, dst):
    d = open(src, "rb").read()
    L = struct.unpack("<I", d[12:16])[0]
    j = json.loads(d[20:20 + L])
    bin_hdr = 20 + L
    blen = struct.unpack("<I", d[bin_hdr:bin_hdr + 4])[0]
    binbuf = bytearray(d[bin_hdr + 8:bin_hdr + 8 + blen])

    skins = j.get("skins", [])
    used = sorted({n["skin"] for n in j["nodes"] if "skin" in n})
    if used:
        main_skin = max(used, key=lambda s: len(skins[s]["joints"]))
        base_joints = list(skins[main_skin]["joints"])
        # garante que todos os ossos de todas as skins estejam na principal
        extra = [jn for s in used for jn in skins[s]["joints"] if jn not in base_joints]
        if extra:
            raise SystemExit("skins com ossos diferentes; nao sei juntar: %s" % extra[:5])
        for n in j["nodes"]:
            s = n.get("skin")
            if s is None or s == main_skin:
                continue
            remap = np.array([base_joints.index(jn) for jn in skins[s]["joints"]])
            mesh = j["meshes"][n["mesh"]]
            done = set()
            for prim in mesh["primitives"]:
                acc_id = prim["attributes"].get("JOINTS_0")
                if acc_id is None or acc_id in done:
                    continue
                done.add(acc_id)
                acc = j["accessors"][acc_id]
                bv = j["bufferViews"][acc["bufferView"]]
                dt = COMP[acc["componentType"]]
                isz = np.dtype(dt).itemsize
                stride = bv.get("byteStride", 4 * isz)
                start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
                for k in range(acc["count"]):
                    off = start + k * stride
                    v = np.frombuffer(bytes(binbuf[off:off + 4 * isz]), dt).astype(np.int64)
                    nv = remap[np.clip(v, 0, len(remap) - 1)].astype(dt)
                    binbuf[off:off + 4 * isz] = nv.tobytes()
            n["skin"] = main_skin
        new_index = {main_skin: 0}
        j["skins"] = [skins[main_skin]]
        for n in j["nodes"]:
            if "skin" in n:
                n["skin"] = new_index[n["skin"]]
    j["animations"] = [a for a in j.get("animations", []) if a.get("channels")]

    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    binbuf += b"\0" * ((4 - len(binbuf) % 4) % 4)
    body = (struct.pack("<I", len(js)) + b"JSON" + js +
            struct.pack("<I", len(binbuf)) + b"BIN\0" + bytes(binbuf))
    open(dst, "wb").write(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)
    print("skins", len(j["skins"]), "animacoes", [a["name"] for a in j["animations"]])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
