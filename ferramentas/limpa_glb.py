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


def _ler(j, binbuf, acc_id):
    acc = j["accessors"][acc_id]
    bv = j["bufferViews"][acc["bufferView"]]
    dt = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}[acc["componentType"]]
    isz = np.dtype(dt).itemsize
    stride = bv.get("byteStride", 4 * isz)
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    raw = np.frombuffer(bytes(binbuf), np.uint8)
    idx = start + np.arange(acc["count"])[:, None] * stride + np.arange(4 * isz)[None, :]
    a = raw[idx].copy().view(dt).reshape(acc["count"], 4)
    if acc.get("normalized") and dt != np.float32:
        a = a.astype(np.float32) / np.iinfo(dt).max
    return a


def pesos_4(j, binbuf):
    """O Mixamo exporta ate 8 ossos por vertice (JOINTS_1/WEIGHTS_1) e o panda3d-gltf perde
    esses pesos (a malha fica parada). Mantem os 4 mais fortes, renormalizados, em JOINTS_0."""
    feitos = {}
    for mesh in j["meshes"]:
        for prim in mesh["primitives"]:
            at = prim["attributes"]
            if "JOINTS_1" not in at or "WEIGHTS_1" not in at:
                continue
            chave = (at["JOINTS_0"], at["WEIGHTS_0"], at["JOINTS_1"], at["WEIGHTS_1"])
            if chave not in feitos:
                J = np.concatenate([_ler(j, binbuf, at["JOINTS_0"]), _ler(j, binbuf, at["JOINTS_1"])], 1)
                W = np.concatenate([_ler(j, binbuf, at["WEIGHTS_0"]), _ler(j, binbuf, at["WEIGHTS_1"])], 1)
                o = np.argsort(-W, axis=1)[:, :4]
                J4 = np.take_along_axis(J, o, 1).astype(np.uint16)
                W4 = np.take_along_axis(W, o, 1).astype(np.float32)
                W4 /= np.maximum(W4.sum(1, keepdims=True), 1e-8)
                # o panda3d-gltf indexa cada combinacao osso/peso em 16 bits (max 65535):
                # quantiza os pesos para caber, aumentando o passo se precisar
                for q in (24, 16, 12, 8):
                    Wq = np.round(W4 * q)
                    Wq[:, 0] = np.maximum(Wq[:, 0], 1)
                    Wq /= Wq.sum(1, keepdims=True)
                    Jq = np.where(Wq > 0, J4, 0)
                    combos = len(np.unique(np.concatenate([Jq.astype(np.float32), Wq], 1), axis=0))
                    if combos < 60000:
                        break
                print("  combinacoes de pesos: %d (passo 1/%d)" % (combos, q))
                W4, J4 = Wq.astype(np.float32), Jq.astype(np.uint16)
                ids = []
                for arr, comp, nome in ((J4, 5123, "j"), (W4, 5126, "w")):
                    binbuf += b"\0" * ((4 - len(binbuf) % 4) % 4)
                    off = len(binbuf)
                    binbuf += arr.tobytes()
                    j["bufferViews"].append({"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes})
                    acc = {"bufferView": len(j["bufferViews"]) - 1, "componentType": comp,
                           "count": len(arr), "type": "VEC4"}
                    j["accessors"].append(acc)
                    ids.append(len(j["accessors"]) - 1)
                feitos[chave] = ids
            at["JOINTS_0"], at["WEIGHTS_0"] = feitos[chave]
            del at["JOINTS_1"], at["WEIGHTS_1"]
    if feitos:
        j["buffers"][0]["byteLength"] = len(binbuf) + (4 - len(binbuf) % 4) % 4
        print("pesos reduzidos a 4 ossos por vertice")
    return binbuf


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
    binbuf = pesos_4(j, binbuf)

    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    binbuf += b"\0" * ((4 - len(binbuf) % 4) % 4)
    body = (struct.pack("<I", len(js)) + b"JSON" + js +
            struct.pack("<I", len(binbuf)) + b"BIN\0" + bytes(binbuf))
    open(dst, "wb").write(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)
    print("skins", len(j["skins"]), "animacoes", [a["name"] for a in j["animations"]])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
