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
        self.assertAlmostEqual(t["eave"], 112.8, delta=1.5)
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
        fit = lambda pitch, rmse=0.03, n=100, inl=95: {"pitchDeg": pitch, "rmseM": rmse, "points": n, "inliers": inl}
        self.assertEqual(lidar.reconcile(26.0, fit(27.0))[0], "agree")
        self.assertEqual(lidar.reconcile(26.0, fit(28.0))[:2], ("override", "use_lidar"))
        self.assertEqual(lidar.reconcile(26.0, fit(28.0, rmse=0.2))[0], "site_check")
        self.assertEqual(lidar.reconcile(26.0, fit(31.0))[0], "site_check")
        self.assertEqual(lidar.reconcile(26.0, fit(26.0, n=20, inl=20))[0], "not_checked")
        self.assertEqual(lidar.reconcile(26.0, fit(26.0, n=200, inl=60))[0], "site_check")
        self.assertEqual(lidar.reconcile(26.0, None)[0], "not_checked")

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
        changed = lidar.apply_overrides(m, chk)
        for pid in changed:
            self.assertEqual(m.planes[pid]["pitchSource"], "lidar")


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


if __name__ == "__main__":
    unittest.main()
