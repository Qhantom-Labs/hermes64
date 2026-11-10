"""Minimal GLB 2.0 reader (numpy). Exposes JSON, accessors, per-node world-space geometry."""
import hashlib
import json
import math
import struct

import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class GLB:
    def __init__(self, path=None, data=None):
        if data is None:
            with open(path, "rb") as f:
                data = f.read()
        self.data = data
        self.sha256 = hashlib.sha256(data).hexdigest()
        magic, ver, length = struct.unpack_from("<4sII", data, 0)
        if magic != b"glTF" or ver != 2:
            raise ValueError("not a GLB v2")
        pos = 12
        self.json = None
        self.bin = b""
        while pos < length:
            ln, kind = struct.unpack_from("<I4s", data, pos)
            body = data[pos + 8:pos + 8 + ln]
            if kind == b"JSON":
                self.json = json.loads(body.decode("utf-8"))
            elif kind == b"BIN\x00":
                self.bin = body
            pos += 8 + ln
        d = self.json
        self.nodes = d.get("nodes", [])
        self.meshes = d.get("meshes", [])
        self.materials = d.get("materials", [])
        self.images = d.get("images", [])
        self.skins = d.get("skins", [])
        self.animations = d.get("animations", [])
        self._parent = {}
        for i, n in enumerate(self.nodes):
            for c in n.get("children", []):
                self._parent[c] = i

    def accessor(self, idx):
        a = self.json["accessors"][idx]
        bv = self.json["bufferViews"][a["bufferView"]]
        dt = np.dtype(CT[a["componentType"]])
        nc = NC[a["type"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0)
        cnt = a["count"]
        if stride and stride != dt.itemsize * nc:
            raw = np.frombuffer(self.bin, dtype=np.uint8, count=stride * cnt, offset=off).reshape(cnt, stride)
            arr = raw[:, :dt.itemsize * nc].copy().view(dt).reshape(cnt, nc)
        else:
            arr = np.frombuffer(self.bin, dtype=dt, count=cnt * nc, offset=off).reshape(cnt, nc)
        if a.get("normalized"):
            arr = arr.astype(np.float64) / float(np.iinfo(dt).max)
        return arr

    def image_bytes(self, idx):
        im = self.images[idx]
        bv = self.json["bufferViews"][im["bufferView"]]
        o = bv.get("byteOffset", 0)
        return self.bin[o:o + bv["byteLength"]]

    @staticmethod
    def local_matrix(n):
        if "matrix" in n:
            return np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
        t = n.get("translation", [0, 0, 0])
        r = n.get("rotation", [0, 0, 0, 1])
        s = n.get("scale", [1, 1, 1])
        x, y, z, w = r
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4)
        M[:3, :3] = R * np.array(s)[None, :]
        M[:3, 3] = t
        return M

    def world_matrix(self, i):
        M = self.local_matrix(self.nodes[i])
        p = self._parent.get(i)
        while p is not None:
            M = self.local_matrix(self.nodes[p]) @ M
            p = self._parent.get(p)
        return M

    def mesh_nodes(self):
        return [i for i, n in enumerate(self.nodes) if "mesh" in n]

    def node_geometry(self, i, world=True):
        """Concatenate all primitives of node i -> dict(pos (N,3), idx (M,3), uv, col, mat (M,),
        joints, weights). Positions in world space unless world=False."""
        n = self.nodes[i]
        mesh = self.meshes[n["mesh"]]
        P, I, UV, C, MAT, J, W, NRM = [], [], [], [], [], [], [], []
        base = 0
        for p in mesh["primitives"]:
            at = p["attributes"]
            pos = self.accessor(at["POSITION"]).astype(np.float64)
            idx = self.accessor(p["indices"]).astype(np.int64).reshape(-1, 3) if "indices" in p else \
                np.arange(len(pos)).reshape(-1, 3)
            P.append(pos)
            I.append(idx + base)
            NRM.append(self.accessor(at["NORMAL"]).astype(np.float64) if "NORMAL" in at else np.zeros_like(pos))
            UV.append(self.accessor(at["TEXCOORD_0"]).astype(np.float64) if "TEXCOORD_0" in at else np.zeros((len(pos), 2)))
            if "COLOR_0" in at:
                c = self.accessor(at["COLOR_0"]).astype(np.float64)
                C.append(c[:, :3])
            else:
                C.append(np.ones((len(pos), 3)))
            if "JOINTS_0" in at:
                J.append(self.accessor(at["JOINTS_0"]).astype(np.int64))
                W.append(self.accessor(at["WEIGHTS_0"]).astype(np.float64))
            MAT.append(np.full(len(idx), p.get("material", -1)))
            base += len(pos)
        pos = np.concatenate(P)
        if world:
            M = self.world_matrix(i)
            pos = pos @ M[:3, :3].T + M[:3, 3]
        return {"pos": pos, "idx": np.concatenate(I), "uv": np.concatenate(UV), "col": np.concatenate(C),
                "nrm": np.concatenate(NRM), "mat": np.concatenate(MAT),
                "joints": np.concatenate(J) if J else None, "weights": np.concatenate(W) if W else None}

    def tri_count(self):
        t = 0
        for i in self.mesh_nodes():
            for p in self.meshes[self.nodes[i]["mesh"]]["primitives"]:
                if "indices" in p:
                    t += self.json["accessors"][p["indices"]]["count"] // 3
                else:
                    t += self.json["accessors"][p["attributes"]["POSITION"]]["count"] // 3
        return t


def weld(pos, tol=1e-4):
    """Map vertices to welded ids by position quantisation."""
    q = np.round(pos / tol).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    return inv.reshape(-1)


def shape_tris(q, idx):
    """Canonical triangle soup of quantised positions: each triangle rotated so its smallest vertex comes
    first (winding kept), list sorted. Independent of the exporter's attribute-driven vertex splitting and
    vertex order."""
    out = []
    for t in idx.reshape(-1, 3):
        v = [tuple(int(c) for c in q[j]) for j in t]
        k = min(range(3), key=lambda m: v[m])
        out.append(tuple(v[k:] + v[:k]))
    out.sort()
    return out


def hashes(g):
    """geometry/topology/uv/skin hashes for a GLB (node-name sorted). shape_sha256 (3.1.0) hashes the
    canonical welded triangle soup, so it is equal whenever the shape is equal, whatever the exporter did
    with vertex splitting (packs change vertex colours/UV tiling, which changes the split pattern and
    therefore geometry_sha256 / topology_sha256)."""
    hg, ht, hu, hs, hp = hashlib.sha256(), hashlib.sha256(), hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    order = sorted(g.mesh_nodes(), key=lambda i: g.nodes[i].get("name", ""))
    for i in order:
        geo = g.node_geometry(i, world=True)
        name = g.nodes[i].get("name", "").encode()
        q = np.round(geo["pos"] * 1e4).astype(np.int64)
        hg.update(name + q.tobytes() + geo["idx"].tobytes())
        hp.update(name + repr(shape_tris(q, geo["idx"])).encode())
        ht.update(name + struct.pack("<q", len(geo["pos"])) + geo["idx"].tobytes() + geo["mat"].astype(np.int64).tobytes())
        hu.update(name + np.round(geo["uv"] * 1e4).astype(np.int64).tobytes())
        if geo["joints"] is not None:
            hs.update(name + geo["joints"].tobytes() + np.round(geo["weights"] * 1e3).astype(np.int64).tobytes())
    for s in g.skins:
        hs.update(json.dumps([g.nodes[j].get("name") for j in s["joints"]]).encode())
    return {"geometry_sha256": hg.hexdigest(), "topology_sha256": ht.hexdigest(), "uv_sha256": hu.hexdigest(),
            "shape_sha256": hp.hexdigest(), "skin_sha256": hs.hexdigest() if g.skins else None}
