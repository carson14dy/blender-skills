"""roof_pitch.py: photo (synthetic gable of known pitch), points, record, combine, rule. Plain numpy, no scene."""
import contextlib
import io
import json
import math

import bpy
import numpy as np
from run_all import TMP, skill_module

_SCENES = {}


def _rp():
    return skill_module("blender-suite", "roof_pitch")


def _fill(img, poly, value, ss=3):
    """Fill a convex polygon (px) with value, antialiased by supersampling."""
    poly = np.asarray(poly, float)
    x0, y0 = np.floor(poly.min(0)).astype(int) - 1
    x1, y1 = np.ceil(poly.max(0)).astype(int) + 1
    h, w = img.shape
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    if x1 <= x0 or y1 <= y0:
        return
    X, Y = np.meshgrid((np.arange((x1 - x0) * ss) + 0.5) / ss + x0, (np.arange((y1 - y0) * ss) + 0.5) / ss + y0)
    inside = np.ones(X.shape, bool)
    area = 0.5 * np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - np.roll(poly[:, 0], -1) * poly[:, 1])
    for a, b in zip(poly, np.roll(poly, -1, 0)):
        cr = (b[0] - a[0]) * (Y - a[1]) - (b[1] - a[1]) * (X - a[0])
        inside &= (cr >= 0) if area > 0 else (cr <= 0)
    cov = inside.reshape(y1 - y0, ss, x1 - x0, ss).mean((1, 3))
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - cov) + value * cov


def scene(pitch12=6.0, yaw_deg=25.0, overhang=0.3, casing=False, W=2400, H=1800, f=1900.0):
    """Gable wall in the plane y=0, 8 m wide, eave 2.7 m, seen yaw_deg off square from 12 m. The rake boards hang
    `overhang` in front of the wall. casing: a white door slab in a white casing 3.5 in. wide, with a 1/2 in. shadow
    gap between them (experiment 027). Returns the gray image (0-1) and the true pixel positions of its edges."""
    key = (pitch12, yaw_deg, overhang, casing)
    if key in _SCENES:
        return _SCENES[key]
    s, half, eave, yaw = pitch12 / 12, 4.0, 2.7, math.radians(yaw_deg)
    ridge = eave + half * s
    C = np.array([4 + 12 * math.sin(yaw), -12 * math.cos(yaw), 1.6])
    fw = np.array([4, 0, 2.6]) - C
    fw /= np.linalg.norm(fw)
    r = np.cross(fw, [0, 0, 1])
    r /= np.linalg.norm(r)
    R = np.stack([r, np.cross(fw, r), fw])
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1.0]])

    def P(X):
        x = (np.asarray(X, float) - C) @ R.T @ K.T
        return x[:, :2] / x[:, 2:3]
    img = np.full((H, W), 0.75)
    _fill(img, P([[-30, 5, 0], [40, 5, 0], [40, -11, 0], [-30, -11, 0]]), 0.35)              # ground
    _fill(img, P([[0, 0, 0], [8, 0, 0], [8, 0, eave], [4, 0, ridge], [0, 0, eave]]), 0.55)     # wall
    for i in range(1, 20):                                                                     # lap siding lines
        z = i * 0.18
        if z < eave - 0.05:
            _fill(img, P([[0.12, 0, z], [7.88, 0, z], [7.88, 0, z + 0.012], [0.12, 0, z + 0.012]]), 0.47)
    for x in (0.0, 7.9):                                                                       # corner boards
        _fill(img, P([[x, 0, 0], [x + 0.1, 0, 0], [x + 0.1, 0, eave], [x, 0, eave]]), 0.9)
    door = [[1.0, 0, 0.05], [1.914, 0, 0.05], [1.914, 0, 2.082], [1.0, 0, 2.082]]              # 36 x 80 in.
    for grow, v in ((0.1016, 0.92), (0.0127, 0.45)) if casing else ():                         # casing, shadow gap
        _fill(img, P([[1 - grow, 0, 0.05], [1.914 + grow, 0, 0.05], [1.914 + grow, 0, 2.082 + grow],
                      [1 - grow, 0, 2.082 + grow]]), v)
    _fill(img, P(door), 0.88 if casing else 0.2)
    _fill(img, P([[5.2, 0, 1.0], [6.4, 0, 1.0], [6.4, 0, 2.2], [5.2, 0, 2.2]]), 0.25)          # window
    o, e, th = -overhang, 0.35, 0.16
    for sx in (1, -1):                                                                         # rake boards
        a, b = np.array([4 - sx * (half + e), o, eave - e * s]), np.array([4.0, o, ridge])
        _fill(img, P([a, b, b + [0, 0, th], a + [0, 0, th]]), 0.92)
    img = np.clip(img + np.random.default_rng(0).normal(0, 0.01, img.shape), 0, 1)
    truth = {"door": P(door), "rake_l": P([[0.4, o, eave + 0.4 * s], [3.4, o, eave + 3.4 * s]]),
             "rake_r": P([[7.6, o, eave + 0.4 * s], [4.6, o, eave + 3.4 * s]]),
             "h": [P([[0.5, 0, 0.912], [7.5, 0, 0.912]]), P([[0.5, 0, 2.532], [7.5, 0, 2.532]])],
             "v": [P([[0.1, 0, 0.2], [0.1, 0, 2.5]]), P([[7.9, 0, 0.2], [7.9, 0, 2.5]])]}
    _SCENES[key] = img, truth
    return img, truth


def clicks(tr, sigma, extras=True, seed=100, scale=1.0):
    """Rough points as Claude would read them: the truth plus click noise, in an image `scale` times the file."""
    rng = np.random.default_rng(seed)
    j = lambda p: ((np.asarray(p) + rng.normal(0, sigma, np.shape(p))) * scale).tolist()  # noqa: E731
    pts = {"view_size": [2400 * scale, 1800 * scale], "rect": j(tr["door"]), "rect_size": ["36in", "80in"],
           "rect_name": "door", "rakes": [j(tr["rake_l"]), j(tr["rake_r"])]}
    if extras:
        pts.update(horizontals=[j(s) for s in tr["h"]], verticals=[j(s) for s in tr["v"]])
    return pts


def _cli(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = _rp().main([str(a) for a in args])
    return rc, json.loads(out.getvalue().strip().splitlines()[-1])


def test_pitch_photo_synthetic_cases():
    rp = _rp()
    for pitch12, yaw, sigma, extras in ((6, 0, 6, True), (6, 25, 8, True), (4, 35, 8, True), (9, 20, 10, True),
                                        (12, 30, 6, True), (6, 25, 8, False)):
        img, tr = scene(pitch12, yaw)
        r = rp.run("photo", image=img, points=clicks(tr, sigma, extras), synthetic=True)
        err = r["rise_per_12"] - pitch12
        assert r["ok"] and abs(err) <= max(0.15, 3 * r["sigma_per_12"]), (pitch12, yaw, r)
        if (pitch12, yaw, extras) == (6, 25, True):          # rake boards 0.3 m in front of the wall: no bias
            assert abs(err) <= 0.05 and r["sigma_per_12"] < 0.1 and r["label"].startswith("6/12 (measured "), r
        # 9/12 with 10 px clicks locks one line onto a neighbouring edge; its own checks say so
        assert r["confidence"] == ("low" if pitch12 == 9 else "ok"), (pitch12, r["checks"], r["notes"])
    assert r["checks"]["lines"] == 6 and r["notes"] == ["no --overlay: write one and look at it"], r


def test_pitch_photo_wrong_line_is_low():
    img, tr = scene(6, 25)
    pts = clicks(tr, 8)
    pts["verticals"] = pts["verticals"] + [pts["rakes"][0]]   # a rake given as a vertical
    r = _rp().run("photo", image=img, points=pts, synthetic=True)
    assert r["ok"] and r["confidence"] == "low" and "rake_spread_per_12 > 0.5" in r["notes"], r


def test_pitch_photo_double_edge_is_low():
    img, tr = scene(6, 25, casing=True)        # slab corners clicked inside a casing (experiment 027, try 1)
    r = _rp().run("photo", image=img, points=clicks(tr, 8), synthetic=True)
    assert r["confidence"] == "low" and "rect_second_edge > 0.75" in r["notes"], r
    assert abs(r["rise_per_12"] - 6) > 2 * r["sigma_per_12"], r          # the snapped rectangle is wrong


def _png(path, gray):
    """Save a gray 0-1 array as PNG with Blender (the bpy reader in roof_pitch.py reads it back)."""
    h, w = gray.shape
    im = bpy.data.images.new("gable", w, h)
    px = np.ones((h, w, 4), np.float32)
    px[..., :3] = gray[::-1, :, None]                         # Blender stores the bottom row first
    im.pixels.foreach_set(px.ravel())
    im.filepath_raw, im.file_format = str(path), "PNG"
    im.save()
    bpy.data.images.remove(im)


def test_pitch_photo_file_view_size_overlay():
    img, tr = scene(6, 25)
    png, pts, ov = TMP / "gable.png", TMP / "pts.json", TMP / "gable_lines.png"
    _png(png, img)
    pts.write_text(json.dumps(clicks(tr, 8, scale=0.5)))       # Claude saw the photo at half size
    rc, r = _cli("photo", "--image", png, "--points", pts, "--overlay", ov, "--out", TMP / "photo.json")
    full = _rp().run("photo", image=img, points=clicks(tr, 8))
    assert rc == 0 and r["ok"] and abs(r["slope"] - full["slope"]) < 0.002, (r, full)
    assert r["sigma_per_12"] == 0.25 and any("photo floor" in n for n in r["notes"]), r   # a real photo's floor
    assert r["source"] == "gable.png, door 36in x 80in" and r["label"].startswith("6/12 (measured "), r
    head = ov.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(head[16:20], "big") == 2400, head
    assert json.loads((TMP / "photo.json").read_text())["slope"] == r["slope"]
    rc, r = _cli("photo", "--image", png, "--points", TMP / "missing.json")
    assert rc == 1 and not r["ok"] and r["error"], r
    pts.write_text(json.dumps(dict(clicks(tr, 8), view_size=[1800, 2400])))                 # rotated
    rc, r = _cli("photo", "--image", png, "--points", pts)
    assert rc == 1 and "view_size" in r["error"], r


def test_pitch_points():
    rng = np.random.default_rng(1)
    xy = rng.uniform(0, 6, (400, 2))
    xyz = np.column_stack([xy + [512000, 4824000], 3 + 0.5 * xy[:, 1] + rng.normal(0, 0.03, 400)])  # 6/12, UTM-sized
    np.savetxt(TMP / "facet.txt", xyz)
    np.save(TMP / "facet.npy", xyz)
    for name in ("facet.txt", "facet.npy"):
        rc, r = _cli("points", "--file", TMP / name)
        assert rc == 0 and abs(r["rise_per_12"] - 6) < 0.1 and r["sigma_per_12"] < 0.1, r
        assert r["checks"]["points"] == 400 and r["nearest_whole"] == "6/12", r


def test_pitch_record_and_combine():
    rc, r = _cli("record", "--method", "report", "--value", "6/12")
    assert rc == 1 and "--source is required" in r["error"], r
    rc, r = _cli("record", "--method", "plans", "--value", "7/12", "--source", "permit 21-0042, sheet A3")
    assert rc == 0 and r["sigma_per_12"] == 0.5 and "design intent, not as built" in r["notes"][0], r
    assert r["label"] == "7/12 (per plans 7.00 ± 0.50)", r
    rp = _rp()
    a, b = (rp.run("record", method=m, value=v, sigma=s, source="test") for m, v, s in (("lidar", "6/12", 0.1),
                                                                                         ("gauge", "5.9/12", 0.3)))
    # 7.5 +/- 0.5 is 2.9 of its own sigma from the mean, just inside 3: 7.6 is past it
    c = rp.run("record", method="report", value="7.6/12", sigma=0.5, source="old report 2019")
    r = rp.run("combine", files=[a, b, c])
    assert r["ok"] and not r["agree"] and r["confidence"] == "low", r
    assert r["checks"]["conflicts"] == ["report (old report 2019): 7.6/12, 3.1 sigma from the mean"], r
    r = rp.run("combine", files=[a, b])
    assert r["agree"] and r["confidence"] == "ok" and abs(r["rise_per_12"] - 5.99) < 0.01, r
    assert r["sigma_per_12"] < 0.1, r


def test_pitch_rule():
    rules = TMP / "design-rules.json"
    rules.write_text(json.dumps({"approved_by": "user", "approved_on": "2026-11-22", "note": "extra keys are fine",
                                 "new_build_pitch": {"accessory": "6/12", "house": "6/12"},
                                 "accessory": {"ice_barrier": False, "ridge_vent": False}}))
    rc, r = _cli("rule", "--covering", "asphalt_shingle", "--building", "accessory", "--rules", rules)
    assert rc == 0 and r["label"] == "6/12 (design rule)" and r["sigma_per_12"] == 0 and not r["notes"], r
    assert "approved by user on 2026-11-22" in r["source"] and "IRC R905.2.2" in r["source"], r
    rc, r = _cli("rule", "--covering", "asphalt_shingle", "--building", "house", "--match", "3.2/12", "--rules", rules)
    assert rc == 0 and r["rise_per_12"] == 3 and r["notes"] == ["double underlayment (IRC R905.2.2)"], r
    assert r["source"].startswith("matches the main house (measured 3.2/12)"), r
    rc, r = _cli("rule", "--covering", "asphalt_shingle", "--building", "house", "--match", "1.2/12", "--rules", rules)
    assert rc == 1 and "below the 2/12 minimum" in r["error"], r
    rc, r = _cli("rule", "--covering", "metal_lapped", "--building", "house", "--match", "2.4/12", "--rules", rules)
    assert rc == 1 and "below the 3/12 minimum for metal_lapped (IRC R905.10.2)" in r["error"], r
    (TMP / "unapproved.json").write_text(json.dumps({"new_build_pitch": {"house": "6/12"}}))
    for path in (TMP / "no-such-rules.json", TMP / "unapproved.json"):
        rc, r = _cli("rule", "--covering", "asphalt_shingle", "--building", "house", "--rules", path)
        assert rc == 1 and r["error"].startswith("no approved design rules: ask the user once"), r
    rp = _rp()
    ok = rp.run("rule", covering="asphalt_shingle", building="house", rules=str(rules))
    r = rp.run("combine", files=[ok, rp.run("record", method="gauge", value="6/12", source="tape")])
    assert not r["ok"] and "cannot be combined" in r["error"], r
