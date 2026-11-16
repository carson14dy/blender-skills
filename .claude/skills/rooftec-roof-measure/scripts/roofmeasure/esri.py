"""Decode Esri multipatch geometry as returned by ArcGIS REST (`f=json`).

The city's Building Wireframe layer returns each building as
`geometry.binaryPatches`: base64 of

    uint32  shape type with flags (0x80800036 = MultiPatch | HasZ | Compressed)
    uint32  uncompressed byte length
    uint32  compressed byte length
    bytes   zlib stream

and the inflated bytes are a standard Esri shape buffer:

    uint32  shape type (low byte 54 = GeneralMultiPatch; 0x80000000 = HasZ)
    4 x f64 xmin, ymin, xmax, ymax
    int32   numParts, int32 numPoints
    int32[numParts]  part start index
    int32[numParts]  part type (0 strip, 1 fan, 2 outer ring, 3 inner ring, 4 first ring, 5 ring, 6 triangles)
    f64[2*numPoints] x, y
    f64 zmin, f64 zmax, f64[numPoints] z
    (optional M block and trailing extension bytes, ignored)

Verified against wireframe OBJECTID 79199 on 2026-11-16. Only ring parts were
seen in the city data (all type 4). Triangle strips, fans and triangle lists are
expanded to triangles so other multipatch sources still work.
"""
import base64
import struct
import zlib

import numpy as np

FLAG_Z = 0x80000000
FLAG_COMPRESSED = 0x00800000
PART_NAMES = {0: "strip", 1: "fan", 2: "outer_ring", 3: "inner_ring", 4: "first_ring", 5: "ring", 6: "triangles"}


class MultipatchError(ValueError):
    pass


def inflate(raw):
    """Return the plain shape buffer for raw `binaryPatches` bytes (handles both compressed and plain)."""
    if len(raw) < 44:
        raise MultipatchError("shape buffer too short (%d bytes)" % len(raw))
    (stype,) = struct.unpack_from("<I", raw, 0)
    if stype & FLAG_COMPRESSED:
        usize, csize = struct.unpack_from("<II", raw, 4)
        try:
            out = zlib.decompress(raw[12:12 + csize] if csize and 12 + csize <= len(raw) else raw[12:])
        except zlib.error as e:
            raise MultipatchError("zlib inflate failed: %s" % e)
        if usize and len(out) != usize:
            raise MultipatchError("inflated %d bytes, header says %d" % (len(out), usize))
        return out
    return raw


def decode_shape_buffer(buf):
    """Plain multipatch shape buffer -> dict(points Nx3 float64, parts [(type, start, end)], bbox, zrange)."""
    (stype,) = struct.unpack_from("<I", buf, 0)
    if (stype & 0xFF) not in (54, 32, 31):  # GeneralMultiPatch, MultiPatch, MultiPatchM
        raise MultipatchError("not a multipatch shape (type 0x%08x)" % stype)
    bbox = struct.unpack_from("<4d", buf, 4)
    nparts, npts = struct.unpack_from("<2i", buf, 36)
    if nparts < 0 or npts < 0 or 44 + 8 * nparts + 24 * npts + 16 > len(buf):
        raise MultipatchError("corrupt counts: %d parts, %d points, %d bytes" % (nparts, npts, len(buf)))
    o = 44
    starts = list(struct.unpack_from("<%di" % nparts, buf, o)); o += 4 * nparts
    types = list(struct.unpack_from("<%di" % nparts, buf, o)); o += 4 * nparts
    xy = np.frombuffer(buf, "<f8", npts * 2, o).reshape(-1, 2); o += 16 * npts
    zrange = struct.unpack_from("<2d", buf, o); o += 16
    z = np.frombuffer(buf, "<f8", npts, o)
    pts = np.column_stack([xy, z]).astype(np.float64)
    ends = starts[1:] + [npts]
    parts = [(t & 0xF, s, e) for t, s, e in zip(types, starts, ends)]
    return {"points": pts, "parts": parts, "bbox": bbox, "zrange": zrange, "shapeType": stype}


def clean_ring(pts, tol=1e-6):
    """Drop repeated and closing vertices (the city rings repeat their start vertex several times)."""
    out = []
    for p in pts:
        if not out or np.linalg.norm(p - out[-1]) > tol:
            out.append(p)
    while len(out) > 1 and np.linalg.norm(out[0] - out[-1]) <= tol:
        out.pop()
    return np.array(out, dtype=np.float64).reshape(-1, 3)


def faces_from_shape(shape):
    """Turn multipatch parts into simple polygons (each an Nx3 array, no repeated vertices)."""
    pts = shape["points"]
    faces = []
    for ptype, s, e in shape["parts"]:
        p = pts[s:e]
        if ptype in (2, 3, 4, 5):
            # inner rings (holes) are rare on houses; they are returned as faces of their own
            # and flagged by the caller through the plan-area check
            r = clean_ring(p)
            if len(r) >= 3:
                faces.append(r)
        elif ptype == 0:
            for i in range(len(p) - 2):
                tri = p[i:i + 3] if i % 2 == 0 else p[[i + 1, i, i + 2]]
                faces.append(np.array(tri))
        elif ptype == 1:
            for i in range(1, len(p) - 1):
                faces.append(np.array([p[0], p[i], p[i + 1]]))
        elif ptype == 6:
            for i in range(0, len(p) - 2, 3):
                faces.append(np.array(p[i:i + 3]))
    return [f for f in faces if len(f) >= 3]


def decode_feature(feature):
    """ArcGIS feature dict -> (faces in source units, shape dict). Raises MultipatchError if no geometry."""
    geom = feature.get("geometry") or {}
    b64 = geom.get("binaryPatches")
    if not b64:
        raise MultipatchError("feature has no geometry.binaryPatches (was returnGeometry=true and f=json used?)")
    shape = decode_shape_buffer(inflate(base64.b64decode(b64)))
    return faces_from_shape(shape), shape


def encode_multipatch(rings, compressed=True):
    """Build a `binaryPatches` string from rings (lists of xyz). Used by tests and synthetic fixtures."""
    pts, starts = [], []
    for r in rings:
        starts.append(len(pts))
        r = [tuple(map(float, p)) for p in r]
        pts.extend(r + [r[0]])
    a = np.array(pts, dtype="<f8")
    buf = struct.pack("<I", FLAG_Z | 54)
    buf += struct.pack("<4d", a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max())
    buf += struct.pack("<2i", len(rings), len(pts))
    buf += struct.pack("<%di" % len(rings), *starts)
    buf += struct.pack("<%di" % len(rings), *([4] * len(rings)))
    buf += a[:, :2].tobytes() + struct.pack("<2d", a[:, 2].min(), a[:, 2].max()) + a[:, 2].tobytes()
    if compressed:
        z = zlib.compress(buf)
        buf = struct.pack("<III", FLAG_Z | FLAG_COMPRESSED | 54, len(buf), len(z)) + z
    return base64.b64encode(buf).decode("ascii")
