"""Offline tests: python3 -m unittest discover -s tests   (from the skill folder)."""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
sys.path.insert(0, HERE)

import synthetic  # noqa: E402
from roofmeasure import cityapi, esri, export, lidar, pipeline, planes, proj  # noqa: E402
from roofmeasure.units import FT_US, m2_to_ft2, m_to_ft  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def fixture_house():
    return load("city/footprint-235245.json")["features"][0], load("city/wireframe-79199.json")["features"][0]


def model_of(faces):
    return planes.build_model([np.array(f, float) for f in faces], unit_m=1.0)


def totals(m):
    return {t: v["lengthM"] for t, v in m.totals().items()}


class EsriDecode(unittest.TestCase):
    def test_city_fixture_decodes(self):
        _, solid = fixture_house()
        faces, shape = esri.decode_feature(solid)
        self.assertEqual(len(shape["parts"]), 31)
        self.assertEqual(len(shape["points"]), 239)
        self.assertEqual({t for t, _, _ in shape["parts"]}, {4})
        self.assertAlmostEqual(shape["zrange"][0], 1482.50, places=2)
        self.assertAlmostEqual(shape["zrange"][1], 1504.03, places=2)
        self.assertEqual(len(faces), 31)
        for f in faces:  # repeated and closing vertices are gone
            self.assertGreater(np.linalg.norm(f[0] - f[-1]), 1e-6)
            self.assertTrue(np.all(np.linalg.norm(np.diff(f, axis=0), axis=1) > 1e-6))

    def test_round_trip_compressed_and_plain(self):
        rings = [[(0, 0, 0), (4, 0, 0), (4, 3, 2.5), (0, 3, 2.5)], [(0, 0, 0), (0, 3, 2.5), (0, 3, 0)]]
        for compressed in (True, False):
            faces, shape = esri.decode_feature({"geometry": {"binaryPatches": esri.encode_multipatch(rings, compressed)}})
            self.assertEqual([len(f) for f in faces], [4, 3])
            np.testing.assert_allclose(faces[0], np.array(rings[0], float))

    def test_bad_input_is_a_clear_error(self):
        with self.assertRaises(esri.MultipatchError):
            esri.decode_feature({"geometry": {}})
        with self.assertRaises(esri.MultipatchError):
            esri.decode_feature({"geometry": {"binaryPatches": "AAAA"}})

    def test_strip_and_fan_parts_become_triangles(self):
        pts = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 2, 0)], float)
        tri = esri.faces_from_shape({"points": pts, "parts": [(0, 0, 5)]})
        self.assertEqual(len(tri), 3)
        fan = esri.faces_from_shape({"points": pts, "parts": [(1, 0, 5)]})
        self.assertEqual(len(fan), 3)


class SyntheticRoofs(unittest.TestCase):
    def check(self, m, exp, tol=0.01):
        t = totals(m)
        for key, want in exp.items():
            if key == "plan":
                self.assertAlmostEqual(m.plan_area, want, delta=tol, msg=key)
            elif key == "sloped":
                self.assertAlmostEqual(m.sloped_area, want, delta=tol, msg=key)
            else:
                self.assertAlmostEqual(t[key], want, delta=tol, msg=key)

    def test_gable(self):
        faces, exp = synthetic.gable()
        m = model_of(faces)
        self.assertEqual(len(m.planes), 2)
        self.check(m, exp)
        for p in m.planes:
            self.assertAlmostEqual(p["pitchIn12"], 6.0, places=3)
        self.assertEqual(sorted(round(p["azimuthGridDeg"]) for p in m.planes), [0, 180])  # one faces north, one south
        self.assertEqual(len([e for e in m.edges if e["type"] == "ridge"]), 1)

    def test_gable_split_into_fragments_merges_back(self):
        faces, exp = synthetic.gable(split=True)
        m = model_of(faces)
        self.assertEqual(len(m.planes), 2)
        self.assertEqual(max(p["faceCount"] for p in m.planes), 2)
        self.check(m, exp)
        self.assertEqual(len([e for e in m.edges if e["type"] == "ridge"]), 1)  # collinear pieces joined
        self.assertEqual(len([e for e in m.edges if e["type"] == "eave"]), 2)

    def test_hip(self):
        faces, exp = synthetic.hip()
        m = model_of(faces)
        self.assertEqual(len(m.planes), 4)
        self.check(m, exp)
        self.assertEqual(len([e for e in m.edges if e["type"] == "hip"]), 4)
        for p in m.planes:
            self.assertAlmostEqual(p["pitchDeg"], math.degrees(math.atan(0.5)), places=3)

    def test_steep_and_shallow_pitch(self):
        for pitch in (2.0, 12.0):
            faces, exp = synthetic.gable(pitch12=pitch)
            m = model_of(faces)
            self.check(m, exp)
            self.assertAlmostEqual(m.planes[0]["pitchIn12"], pitch, places=3)

    def test_roof_against_a_taller_wall_is_flashing_not_rake_or_ridge(self):
        faces, exp = synthetic.lean_to()
        m = model_of(faces)
        self.check(m, exp)
        head = [e for e in m.edges if e["type"] == "headwall"]
        self.assertEqual(len(head), 1)
        self.assertFalse(head[0].get("lowSide"))

    def test_butterfly_valley_and_high_edges(self):
        faces, exp = synthetic.butterfly()
        self.check(model_of(faces), exp)

    def test_winding_does_not_matter(self):
        faces, exp = synthetic.hip()
        flipped = [f[::-1] if i % 2 else f for i, f in enumerate(faces)]
        self.check(model_of(flipped), exp)

    def test_face_under_the_roof_is_ignored(self):
        faces, exp = synthetic.gable()
        cap = [(0, 0, 3), (10, 0, 3), (10, 8, 3), (0, 8, 3)]  # a level cap polygon at eave height
        m = model_of(faces + [cap])
        self.assertEqual(m.stats["hiddenFaces"], 1)
        self.check(m, exp)

    def test_face_delivered_twice_is_counted_once(self):
        # Review round 1: a duplicated roof face doubled its area in version 1.
        faces, exp = synthetic.gable()
        m = model_of(faces + [faces[0]])
        self.assertAlmostEqual(m.sloped_area, exp["sloped"], delta=0.01)
        self.assertEqual(m.stats["duplicateFaces"], 1)
        self.assertAlmostEqual(totals(m)["ridge"], exp["ridge"], delta=0.01)

    def test_ridge_drawn_with_a_sliver_wall_is_one_ridge(self):
        # Review round 1: some city solids put a wall a few centimetres tall between the two sides of a ridge
        # (benchmark houses 176864 and 363469). Version 1 reported the ridge as two "top" edges, twice the length.
        L, W, eave, step = 10.0, 8.0, 3.0, 0.06
        r = eave + 2.0
        roofs = [[(0, 0, eave), (L, 0, eave), (L, W / 2, r), (0, W / 2, r)],
                 [(L, W, eave), (0, W, eave), (0, W / 2, r - step), (L, W / 2, r - step)]]
        walls = [[(0, 0, 0), (L, 0, 0), (L, 0, eave), (0, 0, eave)],
                 [(L, W, 0), (0, W, 0), (0, W, eave), (L, W, eave)],
                 [(0, W, 0), (0, 0, 0), (0, 0, eave), (0, W / 2, r), (0, W / 2, r - step), (0, W, eave)],
                 [(L, 0, 0), (L, W, 0), (L, W, eave), (L, W / 2, r - step), (L, W / 2, r), (L, 0, eave)],
                 [(0, W / 2, r - step), (L, W / 2, r - step), (L, W / 2, r), (0, W / 2, r)]]     # the sliver
        m = model_of(roofs + walls)
        t = totals(m)
        self.assertAlmostEqual(t["ridge"], L, delta=0.01)
        self.assertAlmostEqual(t["top"], 0.0, delta=0.01)
        self.assertAlmostEqual(t["headwall"], 0.0, delta=0.01)
        self.assertAlmostEqual(m.stats["splitRidgeM"], L, delta=0.01)
        # a real step (0.5 m) stays a wall joint: high edge on one side, headwall flashing on the other
        roofs[1] = [(L, W, eave), (0, W, eave), (0, W / 2, r - 0.5), (L, W / 2, r - 0.5)]
        walls[2] = [(0, W, 0), (0, 0, 0), (0, 0, eave), (0, W / 2, r), (0, W / 2, r - 0.5), (0, W, eave)]
        walls[3] = [(L, 0, 0), (L, W, 0), (L, W, eave), (L, W / 2, r - 0.5), (L, W / 2, r), (L, 0, eave)]
        walls[4] = [(0, W / 2, r - 0.5), (L, W / 2, r - 0.5), (L, W / 2, r), (0, W / 2, r)]
        t = totals(model_of(roofs + walls))
        self.assertAlmostEqual(t["ridge"], 0.0, delta=0.01)
        self.assertAlmostEqual(t["top"], L, delta=0.01)
        self.assertAlmostEqual(t["headwall"], L, delta=0.01)

    def test_eave_a_few_degrees_out_of_level_stays_an_eave(self):
        # Review round 1: version 1 called any outer edge sloping more than 3 degrees a rake. An eave that the
        # source drew 5 degrees out of level (about 0.9 m over 10 m) still runs along the contour of its plane.
        L, W, eave, r = 10.0, 8.0, 3.0, 5.0
        roofs = [[(0, 0, eave), (L, 0, eave + 0.45), (L, W / 2, r), (0, W / 2, r)],
                 [(L, W, eave), (0, W, eave), (0, W / 2, r), (L, W / 2, r)]]
        walls = [[(0, 0, 0), (L, 0, 0), (L, 0, eave + 0.45), (0, 0, eave)],
                 [(L, W, 0), (0, W, 0), (0, W, eave), (L, W, eave)],
                 [(0, W, 0), (0, 0, 0), (0, 0, eave), (0, W / 2, r), (0, W, eave)],
                 [(L, 0, 0), (L, W, 0), (L, W, eave), (L, W / 2, r), (L, 0, eave + 0.45)]]
        t = totals(model_of(roofs + walls))
        self.assertAlmostEqual(t["eave"], L + math.hypot(L, 0.45), delta=0.05)
        self.assertAlmostEqual(t["ridge"], L, delta=0.01)
        self.assertEqual(sum(1 for e in model_of(roofs + walls).edges if e["type"] == "rake"), 4)

    def test_feet_input_gives_metres(self):
        faces, exp = synthetic.gable()
        ft = [np.array(f, float) / FT_US + np.array([2239372.9, 15802731.7, 1482.5]) for f in faces]
        m = planes.build_model(ft)
        self.assertAlmostEqual(m.sloped_area, exp["sloped"], delta=0.01)
        self.assertAlmostEqual(m.origin_ft[0], 2239372.9, places=3)


class House235245(unittest.TestCase):
    """Acceptance: the research note's numbers for footprint 235245 / wireframe 79199."""

    @classmethod
    def setUpClass(cls):
        cls.fp, cls.solid = fixture_house()
        cls.m, _ = pipeline.model_from_features(cls.fp, cls.solid)

    def test_seven_planes_at_about_six_in_twelve(self):
        self.assertEqual(len(self.m.planes), 7)
        self.assertEqual(self.m.stats["roofFaces"], 7)
        self.assertEqual(self.m.stats["wallFaces"], 24)
        for p in self.m.planes:
            self.assertTrue(5.5 <= p["pitchIn12"] <= 6.2, p["pitchIn12"])
            self.assertTrue(5.6 <= 12 * math.tan(math.radians(p["sourcePitchDeg"])) <= 6.11)

    def test_areas(self):
        self.assertAlmostEqual(m2_to_ft2(self.m.stats["sourceSlopedAreaM2"]), 3269, delta=1.5)   # as delivered
        self.assertAlmostEqual(m2_to_ft2(self.m.stats["sourcePlanAreaM2"]), 2941, delta=1.0)
        self.assertAlmostEqual(m2_to_ft2(self.m.sloped_area), 3269, delta=3269 * 0.005)          # after cleaning: within 0.5 %
        self.assertAlmostEqual(m2_to_ft2(self.m.plan_area), self.fp["attributes"]["Shape.STArea()"], delta=2941 * 0.005)

    def test_main_ridge_is_53_5_ft_and_level(self):
        ridges = [e for e in self.m.edges if e["type"] == "ridge"]
        main = max(ridges, key=lambda e: e["lengthM"])
        self.assertAlmostEqual(m_to_ft(main["lengthM"]), 53.5, delta=0.3)
        self.assertLess(abs(main["a"][2] - main["b"][2]), 0.1)

    def test_edge_classes_present_and_no_double_count(self):
        t = {k: m_to_ft(v) for k, v in totals(self.m).items()}
        self.assertAlmostEqual(t["ridge"], 78.7, delta=1.0)
        self.assertAlmostEqual(t["valley"], 28.6, delta=1.0)
        # 112.8 ft of eave is certain; one 3.9 ft outer edge runs about 10 degrees off its plane's contour
        # and may be called eave or rake
        self.assertTrue(112.8 - 1.5 <= t["eave"] <= 116.7 + 1.5, t["eave"])
        self.assertGreater(t["step_flashing"] + t["headwall"], 40)   # wall steps are not counted as rake
        self.assertAlmostEqual(sum(t.values()), 472.0, delta=3.0)    # every roof edge counted once (research total: 472 ft)

    def test_cleaning_stays_small(self):
        self.assertLess(self.m.stats["regularizeMaxShiftM"], 0.3)
        self.assertLess(self.m.stats["regularizeMaxGapM"], 0.01)
        self.assertLess(self.m.stats["maxPitchChangeDeg"], 0.3)

    def test_top_matches_footprint_top_elevation(self):
        top_ft = self.m.origin_ft[2] + m_to_ft(self.m.stats["topZM"])
        self.assertAlmostEqual(top_ft, self.fp["attributes"]["BUILDINGTOPELEVATION"], delta=1.0)


class Projection(unittest.TestCase):
    def test_matches_proj_reference_values(self):
        # reference: pyproj 3.8 Transformer.from_crs(4326, 32164, always_xy=True)
        e, n = proj.lonlat_to_city(-96.72939748, 43.54765556)
        self.assertAlmostEqual(float(e), 2242198.293825377, delta=0.02)
        self.assertAlmostEqual(float(n), 15827194.793140152, delta=0.02)

    def test_lidar_reprojection_matches_proj(self):
        # reference: pyproj 3.8 Transformer.from_crs(3857, 32164, always_xy=True).transform(-10768000, 5381000)
        e, n = proj.webmerc_to_city(-10768000.0, 5381000.0)
        self.assertAlmostEqual(float(e), 2242834.7675437303, delta=0.02)
        self.assertAlmostEqual(float(n), 15792269.845577892, delta=0.02)

    def test_round_trips(self):
        lon, lat = proj.city_to_lonlat(2239372.9, 15802731.7)
        e, n = proj.lonlat_to_city(lon, lat)
        self.assertAlmostEqual(float(e), 2239372.9, delta=0.001)
        self.assertAlmostEqual(float(n), 15802731.7, delta=0.001)
        x, y = proj.city_to_webmerc(2239372.9, 15802731.7)
        e, n = proj.webmerc_to_city(x, y)
        self.assertAlmostEqual(float(e), 2239372.9, delta=0.001)
        self.assertAlmostEqual(float(n), 15802731.7, delta=0.001)

    def test_convergence_sign(self):
        self.assertAlmostEqual(proj.grid_convergence_deg(-96.74, 43.48), 1.555, delta=0.02)


class LidarMath(unittest.TestCase):
    def test_plane_fit_ignores_tree_points(self):
        rng = np.random.default_rng(1)
        xy = rng.uniform(0, 8, (300, 2))
        z = 0.5 * xy[:, 1] + 3 + rng.normal(0, 0.03, 300)
        z[:40] += rng.uniform(1, 4, 40)  # branches above the roof
        fit = lidar.fit_plane(np.column_stack([xy, z]))
        self.assertAlmostEqual(fit["pitchDeg"], math.degrees(math.atan(0.5)), delta=0.3)
        self.assertLess(fit["rmseM"], 0.06)
        self.assertGreaterEqual(fit["inliers"], 240)
        self.assertAlmostEqual(fit["azimuthGridDeg"], 180.0, delta=1.0)   # faces south (downhill is -y)

    def test_reconcile_rule(self):
        fit = lambda pitch, se=0.1, n=100, inl=95: {"pitchDeg": pitch, "rmseM": 0.03, "seDeg": se, "points": n, "inliers": inl}
        # a precise lidar fit supplies the pitch, whether the city agrees (no review) or differs 1.5-4 deg (review)
        self.assertEqual(lidar.reconcile(26.0, fit(27.0))[:2], ("agree", "use_lidar"))
        self.assertEqual(lidar.reconcile(26.0, fit(28.0))[:2], ("override", "use_lidar"))
        # an imprecise fit never supplies the pitch: too few points on the plane, or a large standard error
        self.assertEqual(lidar.reconcile(26.0, fit(27.0, se=0.6))[:2], ("agree", "keep_city"))
        self.assertEqual(lidar.reconcile(26.0, fit(27.0, inl=70))[:2], ("agree", "keep_city"))
        self.assertEqual(lidar.reconcile(26.0, fit(28.0, se=0.6))[:2], ("agree", "keep_city"))      # 2.0 deg is within 1.5 + 2 * 0.6
        self.assertEqual(lidar.reconcile(26.0, fit(29.5, se=0.6))[:2], ("site_check", "keep_city"))
        self.assertEqual(lidar.reconcile(26.0, fit(26.5, n=45, inl=36))[:2], ("not_checked", "keep_city"))   # 36 points on the plane
        self.assertEqual(lidar.reconcile(26.0, fit(28.0, inl=70))[:2], ("site_check", "keep_city"))
        self.assertEqual(lidar.reconcile(26.0, fit(31.0))[0], "site_check")
        self.assertEqual(lidar.reconcile(26.0, fit(26.0, n=20, inl=20))[0], "not_checked")
        self.assertEqual(lidar.reconcile(26.0, fit(26.0, n=200, inl=60))[0], "site_check")
        self.assertEqual(lidar.reconcile(26.0, None)[0], "not_checked")

    def test_half_covered_plane_cannot_override(self):
        # Review round 1, bug: version 1 called a fit "clean" when the RMSE of its inliers was under 0.10 m.
        # Inliers are within 0.10 m by construction, so a plane half covered by a tree could override the city.
        rng = np.random.default_rng(5)
        xy = rng.uniform(0, 6, (200, 2))
        z = math.tan(math.radians(28.0)) * xy[:, 1] + 3 + rng.normal(0, 0.03, 200)
        z[:90] += rng.uniform(0.5, 4, 90)    # 45% of the points are branches
        fit = lidar.fit_plane(np.column_stack([xy, z]))
        self.assertLess(fit["rmseM"], 0.10)                       # the old test would have passed
        self.assertFalse(lidar.is_precise(fit))
        self.assertEqual(lidar.reconcile(26.0, fit)[:2], ("site_check", "keep_city"))

    def test_pitch_standard_error(self):
        rng = np.random.default_rng(6)
        wide = rng.uniform(0, 6, (200, 2))
        narrow = np.column_stack([rng.uniform(0, 6, 60), rng.uniform(0, 0.5, 60)])   # spans 0.5 m of the slope
        f = lambda xy: lidar.fit_plane(np.column_stack([xy, 0.5 * xy[:, 1] + rng.normal(0, 0.03, len(xy))]))
        a, b = f(wide), f(narrow)
        self.assertLess(a["seDeg"], 0.1)
        self.assertGreater(b["seDeg"], lidar.PRECISE_SE_DEG)      # too little slope under the points to trust the pitch
        self.assertTrue(lidar.is_precise(a))
        self.assertFalse(lidar.is_precise(b))

    def test_lidar_pitch_retilts_the_geometry(self):
        # city gable drawn at 5.5/12, lidar sees 6/12: plan area and outline stay, pitch and sloped area follow lidar
        faces, _ = synthetic.gable(L=10, W=8, pitch12=5.5)
        m = model_of(faces)
        m.origin_ft = (0.0, 0.0, 0.0)
        rng = np.random.default_rng(7)
        xy = rng.uniform((0, 0), (10, 8), (2500, 2))
        z = 3 + 0.5 * np.minimum(xy[:, 1], 8 - xy[:, 1]) + rng.normal(0, 0.02, 2500)
        chk = lidar.cross_check(m, {"x_ft": xy[:, 0] / FT_US, "y_ft": xy[:, 1] / FT_US, "z_m": z, "cls": np.ones(2500, np.uint8)})
        self.assertEqual([r["action"] for r in chk["planes"]], ["use_lidar", "use_lidar"])
        self.assertEqual(sorted(lidar.apply_overrides(m, chk)), [0, 1])
        k = math.sqrt(1 + 0.5 ** 2)
        for p in m.planes:
            self.assertAlmostEqual(p["pitchIn12"], 6.0, delta=0.05)
            self.assertAlmostEqual(12 * math.tan(math.radians(p["cityPitchDeg"])), 5.5, delta=0.01)
            self.assertEqual(p["pitchSource"], "lidar")
        self.assertAlmostEqual(m.plan_area, 80.0, delta=0.02)                 # the outline did not move
        self.assertAlmostEqual(m.sloped_area, 80.0 * k, delta=80 * k * 0.002)
        t = totals(m)
        self.assertAlmostEqual(t["eave"], 20.0, delta=0.01)
        self.assertAlmostEqual(t["ridge"], 10.0, delta=0.01)
        self.assertAlmostEqual(t["rake"], 16.0 * k, delta=0.03)               # rakes follow the new pitch
        self.assertLess(m.stats["regularizeMaxGapM"], 0.005)
        # the GLB is written from the same geometry, so the studio measures the same area as roof.json
        tri_area = sum(float(np.linalg.norm(planes.newell(t3))) for _, t3 in m.roof_triangles())
        self.assertAlmostEqual(tri_area, m.sloped_area, delta=0.01)

    def test_ept_node_bounds(self):
        b = (0, 0, 0, 8, 8, 8)
        self.assertEqual(lidar.node_bounds(b, 0, 0, 0, 0), (0, 0, 0, 8, 8, 8))
        self.assertEqual(lidar.node_bounds(b, 2, 3, 1, 0), (6, 2, 0, 8, 4, 2))

    def test_cross_check_on_synthetic_points_finds_shift_and_pitch(self):
        faces, _ = synthetic.hip(L=14, W=10)
        m = model_of(faces)
        rng = np.random.default_rng(3)
        xy = rng.uniform((0, 0), (14, 10), (3000, 2))
        # true roof = same hip, shifted 0.2 m east and 0.1 m up
        x, y = xy[:, 0] - 0.2, xy[:, 1]
        z = 3 + 0.5 * np.minimum.reduce([y, 10 - y, x, 14 - x]) + 0.1 + rng.normal(0, 0.02, 3000)
        pts = {"x_ft": xy[:, 0] / FT_US, "y_ft": xy[:, 1] / FT_US, "z_m": z, "cls": np.ones(3000, np.uint8)}
        m.origin_ft = (0.0, 0.0, 0.0)
        chk = lidar.cross_check(m, pts)
        self.assertEqual(chk["summary"]["agree"], 4)
        self.assertAlmostEqual(chk["registration"]["eastM"], 0.2, delta=0.05)
        self.assertAlmostEqual(chk["registration"]["verticalM"], 0.1, delta=0.05)

    def test_cross_check_on_real_points(self):
        fp, solid = fixture_house()
        m, _ = pipeline.model_from_features(fp, solid)
        pts = lidar.load_points(os.path.join(FIX, "lidar", "lidar_points-235245.npz"))
        chk = lidar.cross_check(m, pts)
        main = {r["plane"]: r for r in chk["planes"]}
        for pid in (0, 1, 2):   # the three largest planes agree with lidar within 1.5 degrees
            self.assertEqual(main[pid]["status"], "agree")
            self.assertLess(main[pid]["rmseM"], 0.06)
        self.assertGreaterEqual(chk["summary"]["areaCheckedPct"], 90)
        reg = chk["registration"]
        self.assertLess(math.hypot(reg["eastM"], reg["northM"]), 0.5)   # outline within the plan's 0.5 m target
        plan_before = m.plan_area
        changed = lidar.apply_overrides(m, chk)
        self.assertTrue({0, 1, 2} <= set(changed))    # precise fits: the main planes take the lidar pitch
        for pid in changed:
            self.assertEqual(m.planes[pid]["pitchSource"], "lidar")
            self.assertAlmostEqual(m.planes[pid]["pitchDeg"], main[pid]["lidarPitchDeg"], delta=0.15)
        # independent evidence (references/validation.md): this house is framed at 6/12 and lidar finds it
        for pid in (0, 1, 2):
            self.assertAlmostEqual(m.planes[pid]["pitchIn12"], 6.0, delta=0.12)
        self.assertAlmostEqual(m.plan_area, plan_before, delta=plan_before * 0.0005)   # a re-tilt keeps the outline
        self.assertAlmostEqual(m2_to_ft2(m.sloped_area), 3284, delta=8)


class LidarSurface(unittest.TestCase):
    """Review round 2: the plane fit ignores points off the roof surface, so a plane could "agree" while a tree
    hung over it, a dormer was missing from the city model, or part of it was not built when lidar flew."""

    def _check(self, edit):
        faces, _ = synthetic.gable(L=12, W=10, pitch12=6)
        m = model_of(faces)
        m.origin_ft = (0.0, 0.0, 0.0)
        rng = np.random.default_rng(11)
        xy = rng.uniform((0, 0), (12, 10), (2400, 2))
        z = 3 + 0.5 * np.minimum(xy[:, 1], 10 - xy[:, 1]) + rng.normal(0, 0.02, 2400)
        south = xy[:, 1] < 5
        z = edit(xy, z, south)
        chk = lidar.cross_check(m, {"x_ft": xy[:, 0] / FT_US, "y_ft": xy[:, 1] / FT_US, "z_m": z, "cls": np.ones(2400, np.uint8)})
        by_side = {("south" if m.planes[r["plane"]]["centroid"][1] < 5 else "north"): r for r in chk["planes"]}
        return m, chk, by_side

    def test_clean_roof_has_no_note(self):
        _, chk, side = self._check(lambda xy, z, south: z)
        self.assertEqual(chk["summary"]["surfaceNotes"], 0)
        self.assertEqual(side["south"]["surface"], {"groundShare": 0.0, "aboveShare": 0.0, "belowShare": 0.0})

    def test_dormer_or_tree_above_a_plane_is_reported(self):
        def dormer(xy, z, south):   # a 4 m wide box 0.8 m proud of the south plane: a dormer the model lacks
            box = south & (xy[:, 0] > 4) & (xy[:, 0] < 8) & (xy[:, 1] > 1) & (xy[:, 1] < 4)
            return np.where(box, z + 0.8, z)
        m, chk, side = self._check(dormer)
        self.assertEqual(side["south"]["status"], "agree")            # the fit alone does not see it
        self.assertGreater(side["south"]["surface"]["aboveShare"], 0.15)
        self.assertIn("above the roof surface", side["south"]["surfaceNote"])
        self.assertNotIn("surfaceNote", side["north"])
        _, flags, _ = pipeline.assess(m, None, {}, {"by": "files"}, chk, permits=[])
        msg = [f for f in flags if f["code"] == "lidar-surface"]
        self.assertEqual(len(msg), 1)
        self.assertEqual(msg[0]["severity"], "review")

    def test_ground_under_a_plane_is_reported(self):
        def not_built(xy, z, south):   # the east 40% of the south plane was open ground when lidar flew
            return np.where(south & (xy[:, 0] > 7.2), 0.05, z)
        _, chk, side = self._check(not_built)
        self.assertEqual(side["south"]["status"], "agree")
        self.assertAlmostEqual(side["south"]["surface"]["groundShare"], 0.4, delta=0.06)
        self.assertIn("ground level", side["south"]["surfaceNote"])


class Permits(unittest.TestCase):
    """Review round 2: an addition built after the June 2023 capture gave a clean estimate of the old roof."""

    def _assess(self, permits):
        fp, solid = fixture_house()
        m, _ = pipeline.model_from_features(fp, solid)
        return pipeline.assess(m, fp, {}, {"by": "oid"}, None, permits=permits)

    def test_addition_after_capture_needs_a_site_check(self):
        checks, flags, site = self._assess([{"workClass": "Reshingle", "issuedMs": 1597795200000, "status": "Finaled"},
                                            {"workClass": "Addition", "issuedMs": 1709856000000, "status": "Finaled"}])
        f = [x for x in flags if x["code"] == "permit-since-capture"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "site-check")
        self.assertIn("2024-03-08", f[0]["message"])
        self.assertIn("Site check required", site)
        self.assertEqual(checks["permits"]["lastReshingle"], "2020-08-19")

    def test_old_permits_and_reshingles_do_not_block(self):
        checks, flags, _ = self._assess([{"workClass": "Addition", "issuedMs": 1500000000000, "status": "Finaled"},
                                         {"workClass": "Reshingle", "issuedMs": 1720000000000, "status": "Issued"}])
        self.assertNotIn("permit-since-capture", {x["code"] for x in flags})
        self.assertEqual(checks["permits"]["roofShapePermits"], 1)
        self.assertEqual(checks["permits"]["sinceCapture"], [])

    def test_no_lookup_is_said_out_loud(self):
        checks, flags, _ = self._assess(None)
        self.assertFalse(checks["permits"]["checked"])
        self.assertIn("permits-not-checked", {x["code"] for x in flags})

    def test_a_neighbours_permit_in_the_bounding_box_is_dropped(self):
        fp, _ = fixture_house()
        x0, y0, x1, y1 = cityapi.footprint_bbox(fp)
        ring = np.asarray(fp["geometry"]["rings"][0], float)[:, :2]
        on_house = ring.mean(axis=0)

        class FakeHttp:
            def get_json(self, url, params, cache_path=None):
                self.params = params
                return {"features": [
                    {"attributes": {"WORKCLASS": "Addition", "ISSUEDATE": 1709856000000}, "geometry": {"x": on_house[0], "y": on_house[1]}},
                    {"attributes": {"WORKCLASS": "Razing", "ISSUEDATE": 1719856000000}, "geometry": {"x": x0 - 40.0, "y": y0 - 40.0}}]}
        h = FakeHttp()
        got = cityapi.permits_for_footprint(h, fp, "unused")
        self.assertEqual([p["workClass"] for p in got], ["Addition"])
        self.assertLessEqual(h.params["resultRecordCount"], 25)


class Download(unittest.TestCase):
    def test_a_download_cut_off_half_way_is_retried(self):
        # Review round 2, bug: http.client.IncompleteRead is not an OSError, so it skipped the retry loop and
        # reached the user as a traceback (seen once in 32 live runs).
        import http.client
        import urllib.request
        calls = []

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                calls.append(1)
                if len(calls) == 1:
                    raise http.client.IncompleteRead(b"half", 100)
                return b"whole"
        real, real_sleep = urllib.request.urlopen, cityapi.time.sleep
        urllib.request.urlopen = lambda req, timeout=None: Resp()
        cityapi.time.sleep = lambda s: None
        try:
            h = cityapi.Http(min_interval=0.0)
            self.assertEqual(h.get_bytes("https://example.invalid/x"), b"whole")
            self.assertEqual(len(calls), 2)
        finally:
            urllib.request.urlopen, cityapi.time.sleep = real, real_sleep


class Outputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="roofmeasure-test-")
        fp, solid = fixture_house()
        for name, feat in (("footprint.json", "city/footprint-235245.json"), ("wireframe.json", "city/wireframe-79199.json")):
            os.makedirs(os.path.join(cls.tmp, "235245", "raw"), exist_ok=True)
            shutil.copy(os.path.join(FIX, feat), os.path.join(cls.tmp, "235245", "raw", name))
        shutil.copy(os.path.join(FIX, "lidar", "lidar_points-235245.npz"), os.path.join(cls.tmp, "235245", "raw", "lidar_points.npz"))
        cls.http = cityapi.Http(offline=True)
        cls.doc, cls.paths = pipeline.run(cls.http, cls.tmp, oid=235245, with_lidar=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_no_network_was_used(self):
        self.assertEqual(self.http.requests_made, 0)

    def test_every_value_has_source_and_confidence(self):
        self.assertEqual(export.validate_roof_json(self.doc), [])
        for item in self.doc["planes"] + self.doc["edges"]:
            self.assertEqual(item["provenance"]["confidence"], "estimate")   # nothing is verified before the study
            self.assertEqual(item["provenance"]["capturedOn"], "2023-06")
        self.assertEqual(self.doc["summary"]["confidence"], "estimate")
        self.assertEqual(self.doc["assumptions"]["overhangM"]["provenance"]["confidence"], "assumed")

    def test_verified_needs_study_and_lidar_agreement(self):
        fp, solid = fixture_house()
        m, _ = pipeline.model_from_features(fp, solid)
        chk = lidar.cross_check(m, lidar.load_points(os.path.join(FIX, "lidar", "lidar_points-235245.npz")))
        export.STUDY_PASSED = True
        try:
            doc = export.build_roof_json(m, fp, solid, lidar=chk, flags=[])
            by_status = {p["id"]: (p["lidar"]["status"], p["provenance"]["confidence"]) for p in doc["planes"]}
            for status, conf in by_status.values():
                self.assertEqual(conf, "verified" if status == "agree" else "estimate")
            blocked = export.build_roof_json(m, fp, solid, lidar=chk, flags=[{"code": "x", "severity": "site-check", "message": ""}])
            self.assertTrue(all(p["provenance"]["confidence"] == "estimate" for p in blocked["planes"]))
            no_lidar = export.build_roof_json(m, fp, solid, lidar=None, flags=[])
            self.assertEqual(no_lidar["summary"]["confidence"], "estimate")
        finally:
            export.STUDY_PASSED = False

    def test_attribution_travels_with_the_data(self):
        text = " ".join(self.doc["attribution"])
        self.assertIn("City of Sioux Falls", text)
        self.assertIn("CC BY 4.0", text)
        self.assertIn("USGS", text)
        with open(self.paths["report"], encoding="utf-8") as f:
            report = f.read()
        self.assertIn("City of Sioux Falls, CC BY 4.0", report)
        self.assertIn("City of Sioux Falls", export.read_glb_json(self.paths["glb"])["asset"]["copyright"])

    def test_validator_catches_missing_provenance(self):
        bad = json.loads(json.dumps(self.doc))
        del bad["planes"][0]["provenance"]["confidence"]
        self.assertTrue(export.validate_roof_json(bad))

    def test_glb_has_a_mesh_named_roof(self):
        g = export.read_glb_json(self.paths["glb"])
        names = [n["name"] for n in g["nodes"]]
        self.assertEqual(names, ["Roof", "Walls"])
        self.assertEqual(g["asset"]["version"], "2.0")
        roof_acc = g["accessors"][g["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
        self.assertEqual(roof_acc["count"] % 3, 0)
        self.assertGreater(roof_acc["count"], 20)
        # metres, Y up: the roof is 3 to 6.5 m above the ground and about 20 x 24 m in plan
        self.assertTrue(2.0 < roof_acc["min"][1] < 4 and 5.5 < roof_acc["max"][1] < 7, (roof_acc["min"], roof_acc["max"]))
        self.assertAlmostEqual(roof_acc["max"][0] - roof_acc["min"][0], 65.2 * FT_US, delta=0.3)
        with open(self.paths["glb"], "rb") as f:
            self.assertEqual(os.path.getsize(self.paths["glb"]), int.from_bytes(f.read(12)[8:], "little"))

    def test_roof_json_numbers(self):
        s = self.doc["summary"]
        self.assertEqual(s["planeCount"], 7)
        self.assertAlmostEqual(s["squares"], 32.7, delta=0.2)
        self.assertAlmostEqual(s["predominantPitchIn12"], 5.9, delta=0.3)
        self.assertAlmostEqual(self.doc["origin"]["lat"], 43.4809, delta=0.001)
        self.assertAlmostEqual(self.doc["origin"]["lon"], -96.7424, delta=0.001)
        self.assertTrue(self.doc["checks"]["planAreaVsFootprint"]["pass"])
        self.assertEqual(self.doc["checks"]["lidar"]["summary"]["siteCheck"], 0)

    def test_report_is_readable(self):
        with open(self.paths["report"], encoding="utf-8") as f:
            report = f.read()
        for needle in ("squares", "Ridge", "ESTIMATE", "Lidar cross-check"):
            self.assertIn(needle, report)

    def test_site_check_is_not_reported_as_an_estimate(self):
        # Review round 2: a house that must not be used carried the headline "Status: ESTIMATE" and the same
        # summary.confidence as a clean one. The summary now has a yes/no field and the report says it.
        self.assertIs(self.doc["summary"]["siteCheckRequired"], False)
        fp, solid = fixture_house()
        fp = dict(fp, attributes=dict(fp["attributes"], OCCUPIEDDATE=1700000000000))   # occupied after the capture
        tmp = tempfile.mkdtemp(prefix="roofmeasure-test-")
        try:
            doc, paths = pipeline.run(cityapi.Http(offline=True), tmp, footprint=fp, solid=solid)
            self.assertIs(doc["summary"]["siteCheckRequired"], True)
            with open(paths["report"], encoding="utf-8") as f:
                head = f.read().split("\n")[2]
            self.assertIn("SITE CHECK REQUIRED", head)
            self.assertNotIn("ESTIMATE", head)
            self.assertIs(export.read_glb_json(paths["glb"])["scenes"][0]["extras"]["siteCheckRequired"], True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cli_runs_offline_from_cache(self):
        r = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "roof.py"), "measure", "--oid", "235245",
                            "--out", self.tmp, "--offline", "--quiet", "--json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["summary"]["planeCount"], 7)

    def test_cli_fails_cleanly_when_not_cached(self):
        r = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "roof.py"), "measure", "--oid", "1",
                            "--out", self.tmp, "--offline", "--quiet"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Could not measure", r.stderr)


class AccuracyStudy(unittest.TestCase):
    def test_compare_against_truth(self):
        from roofmeasure import study
        fp, solid = fixture_house()
        tmp = tempfile.mkdtemp(prefix="roofmeasure-test-")
        try:
            doc, _ = pipeline.run(cityapi.Http(offline=True), tmp, footprint=fp, solid=solid)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        good = {"slopedAreaFt2": 3300, "predominantPitchIn12": 6, "edgesFt": {"ridge": 79, "valley": 29}}
        rows, ok = study.compare(doc, good)
        self.assertTrue(ok, rows)
        rows, ok = study.compare(doc, {"slopedAreaFt2": 3500, "edgesFt": {"ridge": 79}})
        self.assertFalse(ok)                      # 7 % off the area target
        self.assertTrue(rows[1]["ok"])
        self.assertIn("FAIL", study.markdown(doc, {}, rows, ok))
        with self.assertRaises(ValueError):
            study.compare(doc, {"edgesFt": {"gutter": 10}})


class Lookup(unittest.TestCase):
    def test_address_normalising(self):
        n = cityapi.normalize_address
        self.assertEqual(n("224 West 9th Street, Sioux Falls, SD 57104"), "224 W 9TH ST")
        self.assertEqual(n("  7112 s. redstone ave "), "7112 S REDSTONE AVE")
        self.assertEqual(n("100 N West Ave"), "100 N WEST AVE")         # a street that is named after a direction
        self.assertEqual(n("500 E 41st Street North"), "500 E 41ST ST N")

    def test_pick_solid_prefers_the_matching_building(self):
        fp, solid = fixture_house()
        far = json.loads(json.dumps(solid))
        ring = [[(0, 0, 0), (10, 0, 0), (10, 10, 3), (0, 10, 3)]]
        far["geometry"]["binaryPatches"] = esri.encode_multipatch(ring)
        far["attributes"]["OBJECTID"] = 1
        best, info = cityapi.pick_solid({"features": [far, solid]}, fp)
        self.assertEqual(best["attributes"]["OBJECTID"], 79199)
        self.assertEqual(info["candidates"], 2)
        self.assertGreater(info["bboxIoU"], 0.99)

    def test_no_solid_is_a_clear_message(self):
        fp, _ = fixture_house()
        with self.assertRaises(cityapi.LookupError_) as cm:
            cityapi.pick_solid({"features": []}, fp)
        self.assertIn("tier C", str(cm.exception))

    def test_point_distance_to_outline(self):
        sq = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]
        self.assertEqual(cityapi._ring_distance(sq, 5, 5), 0.0)
        self.assertAlmostEqual(cityapi._ring_distance(sq, 13, 5), 3.0)

    def test_flags_for_a_new_house_and_missing_lidar(self):
        fp, solid = fixture_house()
        m, _ = pipeline.model_from_features(fp, solid)
        checks, flags, site = pipeline.assess(m, fp, {}, {"by": "address", "yearBuilt": "2024", "distanceFt": 0}, None)
        codes = {f["code"] for f in flags}
        self.assertIn("newer-than-solid", codes)
        self.assertIn("no-lidar-check", codes)
        self.assertIn("Site check required", site)

    def test_house_newer_than_lidar_is_flagged_without_an_address(self):
        # Review round 1: version 1 knew the build year only for address lookups, so --oid runs on houses
        # occupied after the lidar flight got lidar "disagreements" with no explanation.
        fp, solid = fixture_house()
        m, _ = pipeline.model_from_features(fp, solid)
        fp = dict(fp, attributes=dict(fp["attributes"], OCCUPIEDDATE=1640995200000))   # 2022-01-01
        _, flags, _ = pipeline.assess(m, fp, {}, {"by": "oid"}, None)
        self.assertIn("newer-than-lidar", {f["code"] for f in flags})
        self.assertNotIn("newer-than-solid", {f["code"] for f in flags})


if __name__ == "__main__":
    unittest.main()
