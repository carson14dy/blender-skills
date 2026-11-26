"""Convert a binary GLB into an embedded glTF JSON file (one base64 data: buffer), and back.

Hosts that cannot serve .glb (the Roof Layer Studio artifact) take the model as `<slug>.gltf.json`. The page decodes
the base64 itself and repacks a GLB in memory (sandboxed hosts' CSP blocks fetch() of data: URLs), so the buffer
must be exactly the GLB BIN chunk's payload.

    python3 glb_to_gltf_json.py IN.glb OUT.gltf.json         GLB -> embedded glTF JSON (compact)
    python3 glb_to_gltf_json.py --reverse IN.gltf.json OUT.glb   and back (for checks)

`gltf_to_glb(glb_to_gltf(b)) == b` for any GLB whose JSON chunk is compact JSON padded with spaces (what this module
and Blender write), so a round trip is byte-identical.
"""
import argparse
import base64
import json
import re
import struct
import sys

MAGIC = 0x46546C67          # b"glTF"
CHUNK_JSON = 0x4E4F534A     # b"JSON"
CHUNK_BIN = 0x004E4942      # b"BIN\0"
DATA_URI = "data:application/octet-stream;base64,"


class GlbError(ValueError):
    pass


def read_glb(data):
    """GLB bytes -> (json dict, BIN chunk payload bytes or None)."""
    if len(data) < 20:
        raise GlbError("file too short to be a GLB")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != MAGIC:
        raise GlbError("not a GLB (bad magic)")
    if version != 2:
        raise GlbError(f"GLB version {version}, expected 2")
    if length > len(data):
        raise GlbError(f"GLB header says {length} bytes, file has {len(data)}")
    off, js, binb = 12, None, None
    while off + 8 <= length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if len(chunk) != clen:
            raise GlbError("truncated GLB chunk")
        off += 8 + clen
        if ctype == CHUNK_JSON and js is None:
            js = json.loads(chunk.decode("utf-8").rstrip(" \x00"))
        elif ctype == CHUNK_BIN and binb is None:
            binb = bytes(chunk)
    if js is None:
        raise GlbError("GLB has no JSON chunk")
    return js, binb


def glb_to_gltf(data):
    """GLB bytes -> glTF dict whose single buffer is an embedded base64 data: URI."""
    js, binb = read_glb(data)
    bufs = js.get("buffers") or []
    if binb is None:
        if bufs:
            raise GlbError("GLB declares buffers but has no BIN chunk")
        return js
    if len(bufs) != 1:
        raise GlbError(f"expected exactly one buffer, found {len(bufs)}")
    if "uri" in bufs[0]:
        raise GlbError("the GLB buffer already has a uri (external buffer)")
    n = int(bufs[0].get("byteLength", len(binb)))
    if n > len(binb):
        raise GlbError(f"buffer byteLength {n} exceeds the BIN chunk ({len(binb)} bytes)")
    bufs[0]["uri"] = DATA_URI + base64.b64encode(binb[:n]).decode("ascii")
    return js


def decode_buffer(gltf):
    """The raw bytes of an embedded glTF's single data: buffer (what the studio page decodes)."""
    bufs = gltf.get("buffers") or []
    if len(bufs) != 1:
        raise GlbError(f"embedded model must have exactly one buffer, found {len(bufs)}")
    m = re.match(r"^data:[^,]*;base64,(.*)$", bufs[0].get("uri", ""), re.S)
    if not m:
        raise GlbError("buffer is not a base64 data: URI")
    return base64.b64decode(m.group(1))


def _pad(b, fill):
    return b + fill * ((4 - len(b) % 4) % 4)


def gltf_to_glb(gltf):
    """Embedded glTF dict -> GLB bytes (the same repack the studio page does). Does not modify `gltf`."""
    js = json.loads(json.dumps(gltf))
    binb = None
    if js.get("buffers"):
        binb = decode_buffer(js)
        del js["buffers"][0]["uri"]
        js["buffers"][0]["byteLength"] = len(binb)
    jb = _pad(dumps(js).encode("utf-8"), b" ")
    out = struct.pack("<II", len(jb), CHUNK_JSON) + jb
    if binb is not None:
        bb = _pad(binb, b"\x00")
        out += struct.pack("<II", len(bb), CHUNK_BIN) + bb
    return struct.pack("<III", MAGIC, 2, 12 + len(out)) + out


def dumps(js):
    return json.dumps(js, separators=(",", ":"), ensure_ascii=False)


def summary(gltf):
    names = [n.get("name", "") for n in gltf.get("nodes", [])]
    return {"nodes": len(names), "meshes": len(gltf.get("meshes", [])),
            "extensions": sorted(gltf.get("extensionsUsed", [])), "names": names}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--reverse", action="store_true", help="embedded .gltf.json -> .glb")
    a = ap.parse_args(argv)
    if a.reverse:
        with open(a.src, encoding="utf-8") as f:
            out = gltf_to_glb(json.load(f))
        with open(a.dst, "wb") as f:
            f.write(out)
        print(f"wrote {a.dst} ({len(out)} bytes)")
        return 0
    with open(a.src, "rb") as f:
        gl = glb_to_gltf(f.read())
    text = dumps(gl)
    with open(a.dst, "w", encoding="utf-8") as f:
        f.write(text)
    s = summary(gl)
    print(f"wrote {a.dst} ({len(text.encode('utf-8')) / 1e6:.2f} MB, {s['nodes']} nodes, {s['meshes']} meshes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
