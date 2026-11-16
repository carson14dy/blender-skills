"""Measure an arbitrary roof mesh inside Blender (photogrammetry, AI-generated, hand-modelled).

    blender -b file.blend -P measure_mesh.py -- --object Roof --out measure.json [--up-threshold 0.2]
    (or via send_to_mcp.py)

Groups faces into planar facets (region growing on normals + plane offset), then classifies
facet-to-facet edges by convexity and slope (ridge / hip / valley / transition) and boundary
edges by slope (eave / rake). Reports true areas, pitches and edge lengths in world units —
apply the object's transform first or this script uses matrix_world for you.

ACCURACY: the result is only as metric as the mesh. A generative image-to-3D mesh has an
arbitrary scale; scale/georeference it first (pm.py align with >= 3 known points) and check
it against LiDAR/tape before trusting any number.
"""
import json
import math
import sys
from collections import defaultdict

import bpy
import bmesh
from mathutils import Vector


def parse_args():
    argv = globals().get("PM_ARGS")
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--object", required=True)
    ap.add_argument("--out")
    ap.add_argument("--angle-tol", type=float, default=5.0, help="deg between normals within a facet")
    ap.add_argument("--dist-tol", type=float, default=0.08, help="m plane offset within a facet")
    ap.add_argument("--up-threshold", type=float, default=0.2, help="min normal.z to count as roof")
    ap.add_argument("--min-area", type=float, default=0.3, help="m2; smaller facets are reported as clutter")
    return ap.parse_args(argv)


def main():
    a = parse_args()
    ob = bpy.data.objects[a.object]
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    roof = [f for f in bm.faces if f.normal.z > a.up_threshold and f.calc_area() > 1e-8]
    cos_tol = math.cos(math.radians(a.angle_tol))
    label = {}
    facets = []
    for seed in sorted(roof, key=lambda f: -f.calc_area()):
        if seed.index in label:
            continue
        fid = len(facets)
        n0, p0 = seed.normal.copy(), seed.calc_center_median()
        stack, members = [seed], []
        label[seed.index] = fid
        while stack:
            f = stack.pop()
            members.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index in label or g.normal.z <= a.up_threshold:
                        continue
                    if g.normal.dot(n0) >= cos_tol and abs((g.calc_center_median() - p0).dot(n0)) < a.dist_tol:
                        label[g.index] = fid
                        stack.append(g)
        area = sum(f.calc_area() for f in members)
        n = Vector((0, 0, 0))
        for f in members:
            n += f.normal * f.calc_area()
        n.normalize()
        slope = math.hypot(n.x, n.y) / max(n.z, 1e-9)
        az = (math.degrees(math.atan2(n.x, n.y)) + 360) % 360 if slope > 0.02 else None
        facets.append({"id": fid, "area_m2": area, "pitch_rise_per_12": slope * 12, "azimuth": az,
                       "normal": list(n), "centre": list(sum((f.calc_center_median() for f in members), Vector()) / len(members)),
                       "faces": len(members)})
    lengths = defaultdict(float)
    for e in bm.edges:
        lf = [f for f in e.link_faces if f.index in label]
        L = e.calc_length()
        v0, v1 = e.verts[0].co, e.verts[1].co
        horiz = abs(v1.z - v0.z) <= 0.05 * max((v1.xy - v0.xy).length, 1e-9)
        ids = {label[f.index] for f in lf}
        if len(lf) == 2 and len(ids) == 2:
            f1, f2 = lf
            convex = (f2.calc_center_median() - f1.calc_center_median()).dot(f1.normal) < 0
            opposite = f1.normal.xy.length > 1e-6 and f2.normal.xy.length > 1e-6 and \
                f1.normal.xy.normalized().dot(f2.normal.xy.normalized()) < -0.7
            if horiz:
                kind = ("ridge" if opposite else "transition") if convex else ("valley" if opposite else "transition")
            else:
                kind = "hip" if convex else "valley"
            lengths[kind] += L
        elif len(lf) == 1 and len(e.link_faces) == 1:
            lengths["eave" if horiz else "rake"] += L
        elif len(lf) == 1:
            lengths["wall_junction"] += L
    big = [f for f in facets if f["area_m2"] >= a.min_area]
    out = {"object": a.object, "roof_area_m2": sum(f["area_m2"] for f in big),
           "roof_area_sqft": sum(f["area_m2"] for f in big) * 10.7639104,
           "clutter_area_m2": sum(f["area_m2"] for f in facets if f["area_m2"] < a.min_area),
           "facets": big, "edges_m": dict(lengths),
           "note": "noisy meshes split facets and inflate edge totals; decimate/planarize first or fit wings with pm.py"}
    txt = json.dumps(out, indent=2)
    print(txt)
    if a.out:
        open(a.out, "w").write(txt)
    bm.free()


main()
