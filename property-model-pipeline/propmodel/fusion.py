"""Evidence fusion: fit the parametric building to *every* measurement source.

Each piece of evidence is an observation with a value and a 1-sigma
uncertainty (LiDAR points, footprint polygons, photo measurements, tape
measurements, numbers from past reports, assessor records...). The free wing
parameters are estimated by robust (Huber-IRLS) Levenberg-Marquardt weighted
least squares. Outputs:

* best-estimate parameters with 1-sigma uncertainties (from the covariance),
* every report quantity (roof area, ridge length, ...) with propagated 1-sigma,
* a residual table: which sources agree, which conflict (|r| > 3 sigma) — a
  conflict usually means a blunder, a renovation since the old report, or a
  wrong assumption (e.g. footprint traced at the roof edge, not the wall).

Observation schema (JSON), one dict per observation::

    {"target": "roof.area", "value": "2450 sqft", "sigma": "25 sqft",
     "source": "EagleView 2019-05", "kind": "past_report"}
    {"target": "M.length", "value": "42ft 6in", "sigma": "1in", "source": "tape"}
    {"target": "pitch@", "xy": [3.1, -2.0], "value": "6/12", "sigma": "0.25/12"}
    {"target": "roof_z", "points": [[x, y, z], ...], "sigma": 0.12, "source": "3DEP"}
    {"target": "outline", "which": "roof_outline", "polygon": [[x, y], ...],
     "sigma": 0.4, "source": "MS footprints", "shift": "msfp"}
    {"target": "outline", "which": "roof_outline", "segments": [[[x0, y0], [x1, y1]], ...],
     "sigma": 0.05, "source": "auto:edges ...", "kind": "lidar_drip"}   # measured pieces of the outline only

An observation with ``"disabled": true`` stays in observations.json but is not used by the fit
(e.g. the LiDAR hull outline once ``pm.py edges`` has measured the drip edges). A ``roof_z`` row
with ``"dz_param": "shift.<name>.dz"`` gets that vertical offset as a nuisance parameter
automatically (weak 2 m prior, like the horizontal outline shifts).

``target`` is either a measurement key from
:meth:`propmodel.roofgeom.BuildingModel.measurements` (``roof.area``,
``edge.ridge``, ``footprint.area``, ``wall.area``, ``wing.<id>.ridge_height``...),
a wing parameter ``<wing id>.<field>``, or one of the special vector targets
``roof_z``, ``outline``, ``pitch@``, ``azimuth@`` and ``z@``.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
from shapely.geometry import Polygon, Point, LineString

from . import units as U
from .roofgeom import Wing, plane_azimuth
from .roofgeom import build as _raw_build

_GROUND = None  # set by fit(): planar grade (a, b, c) used for wall bottoms


def build(wings):
    return _raw_build(wings, ground=_GROUND)

HUBER_K = 2.0

BOUNDS = {
    "length": (0.3, 200), "width": (0.3, 200), "pitch": (0.0, 4.0), "pitch_b": (0.0, 4.0), "end_pitch": (0.0, 4.0),
    "upper_pitch": (0.0, 4.0), "eave_height": (0.3, 60), "eave_overhang": (0.0, 4.0),
    "rake_overhang": (0.0, 2.0), "break_inset": (0.05, 50), "shed_high_overhang": (0.0, 4.0),
    "eave_overhang_b": (0.0, 4.0), "eave_height_b": (0.3, 60),
}
STEP = {"azimuth": 0.01, "pitch": 1e-4, "pitch_b": 1e-4, "end_pitch": 1e-4, "upper_pitch": 1e-4}
DEFAULT_STEP = 1e-4


# ---------------------------------------------------------------------------
# value parsing
# ---------------------------------------------------------------------------

def parse_area(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower().replace(" ", "").replace(",", "")
    for suf, f in (("sqft", 1 / U.SQFT_PER_SQM), ("ft2", 1 / U.SQFT_PER_SQM), ("sf", 1 / U.SQFT_PER_SQM),
                   ("squares", 100 / U.SQFT_PER_SQM), ("sq", 100 / U.SQFT_PER_SQM),
                   ("m2", 1.0), ("sqm", 1.0)):
        if s.endswith(suf):
            return float(s[: -len(suf)]) * f
    return float(s)


def kind_of(target):
    t = target.lower()
    if "pitch" in t.rsplit(".", 1)[-1] or t.startswith("pitch@") or t.endswith("pitch_weighted") or t.endswith("pitch_max") \
            or t.endswith("end_pitch") or t.endswith("upper_pitch"):
        return "slope"
    if "area" in t:
        return "area"
    if t.endswith("azimuth") or t.startswith("azimuth@"):
        return "angle"
    if t.endswith("facets"):
        return "count"
    return "length"


def parse_value(target, v):
    k = kind_of(target)
    if v is None:
        return None
    if k == "slope":
        if isinstance(v, str) and "/" in v:
            a, b = v.split("/", 1)
            return float(a) / float(b)
        return U.parse_pitch(v)
    if k == "area":
        return parse_area(v)
    if k in ("angle", "count"):
        return float(str(v).rstrip("°deg"))
    return U.parse_length(v)


def parse_sigma(target, s, value):
    if isinstance(s, str) and s.strip().endswith("%"):
        return abs(value) * float(s.strip()[:-1]) / 100.0
    return parse_value(target, s)


# ---------------------------------------------------------------------------
# parameter vector
# ---------------------------------------------------------------------------

class ParamSpace:
    """Maps the free parameter vector <-> wing fields (supports ties & nuisances)."""

    def __init__(self, wings, free, ties=(), nuisance=()):
        self.wings0 = [w if isinstance(w, Wing) else Wing.from_dict(w) for w in wings]
        self.groups = []   # list of lists of "wing.field"
        # union-find so overlapping tie groups ([a,b],[b,c]) become one group [a,b,c]
        parent = {}

        def find(a):
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for grp in ties:
            for name in grp[1:]:
                ra, rb = find(grp[0]), find(name)
                if ra != rb:
                    parent[rb] = ra
        members = {}
        for name in list(parent):
            members.setdefault(find(name), []).append(name)
        tied = {}
        for root, names in members.items():
            ordered = sorted(names, key=lambda nm: (nm not in free, free.index(nm) if nm in free else 0))
            for nm in names:
                tied[nm] = ordered
        seen = set()
        for name in free:
            if name in seen:
                continue
            grp = list(tied.get(name, [name]))
            seen.update(grp)
            self.groups.append(grp)
        for name in nuisance:
            if name not in seen:
                self.groups.append([name])
                seen.add(name)
        self.names = [g[0] for g in self.groups]
        self.nuis = {n: 0.0 for n in nuisance}

    def _get(self, wings, name):
        if name.startswith("shift."):
            return self.nuis.get(name, 0.0)
        wid, fld = name.split(".", 1)
        for w in wings:
            if w.id == wid:
                val = getattr(w, fld)
                if val is None:
                    val = _implicit(w, fld)
                return float(val)
        raise KeyError(f"unknown wing in parameter {name!r}")

    def x0(self):
        return np.array([self._get(self.wings0, g[0]) for g in self.groups], float)

    def apply(self, x):
        wings = copy.deepcopy(self.wings0)
        nuis = dict(self.nuis)
        byid = {w.id: w for w in wings}
        for grp, val in zip(self.groups, x):
            for name in grp:
                if name.startswith("shift."):
                    nuis[name] = float(val)
                    continue
                wid, fld = name.split(".", 1)
                setattr(byid[wid], fld, float(val))
        return wings, nuis

    def clamp(self, x):
        x = np.array(x, float)
        for i, g in enumerate(self.groups):
            fld = g[0].split(".", 1)[1]
            if fld in BOUNDS:
                lo, hi = BOUNDS[fld]
                x[i] = min(max(x[i], lo), hi)
        return x

    def steps(self, x):
        out = []
        for g, xi in zip(self.groups, x):
            fld = g[0].split(".", 1)[1]
            out.append(STEP.get(fld, max(DEFAULT_STEP, 1e-5 * abs(xi))))
        return np.array(out)


def _implicit(w: Wing, fld):
    if fld in ("end_pitch", "pitch_b"):
        return w.pitch
    if fld == "eave_height_b":
        return w.eave_height
    if fld == "eave_overhang_b":
        return w.eave_overhang
    if fld == "upper_pitch":
        return w.pitch / 3.0
    if fld == "break_inset":
        return w.width / 4.0
    if fld == "shed_high_overhang":
        return w.eave_overhang
    return 0.0


# ---------------------------------------------------------------------------
# predictions
# ---------------------------------------------------------------------------

@dataclass
class Obs:
    raw: dict
    target: str
    value: float = None
    sigma: float = None
    n: int = 1

    @property
    def source(self):
        return self.raw.get("source", "?")


def prepare(observations):
    out = []
    for o in observations:
        t = o["target"]
        if t == "roof_z":
            pts = np.asarray(o["points"], float)
            out.append(Obs(o, t, None, float(U.parse_length(o.get("sigma", 0.15))), len(pts)))
        elif t == "outline":
            out.append(Obs(o, t, None, float(U.parse_length(o.get("sigma", 0.5)))))
        else:
            v = parse_value(t, o["value"])
            s = parse_sigma(t, o.get("sigma"), v) if o.get("sigma") is not None else None
            if s is None or s <= 0:
                raise ValueError(f"observation {t} from {o.get('source')} needs a positive sigma")
            out.append(Obs(o, t, v, s))
    return out


def _outline_samples(poly_xy, spacing=0.5):
    ring = LineString(list(poly_xy) + [poly_xy[0]])
    n = max(int(ring.length / spacing), 8)
    return np.array([ring.interpolate(i / n, normalized=True).coords[0] for i in range(n)])


def _segment_samples(segments, spacing=0.5):
    """Samples along open outline pieces (measured edges): interval midpoints, >= 2 per segment."""
    out = []
    for seg in segments:
        a, b = np.asarray(seg[0], float)[:2], np.asarray(seg[-1], float)[:2]
        n = max(int(np.linalg.norm(b - a) / spacing), 2)
        t = (np.arange(n) + 0.5) / n
        out.append(a + np.outer(t, b - a))
    return np.vstack(out) if out else np.zeros((0, 2))


def active(observations):
    """Observations the fit uses (``"disabled": true`` rows are kept on file but skipped)."""
    return [o for o in observations if not o.get("disabled")]


class Predictor:
    def __init__(self, obs: List[Obs]):
        self.obs = obs
        self._cache = {}
        self._cur = None
        for o in obs:
            if o.target == "outline":
                if o.raw.get("segments"):
                    # measured edge pieces: one degree of freedom (the edge offset) per segment, so the
                    # observation's sigma is the 1-sigma of each measured edge position
                    samp = _segment_samples(o.raw["segments"], o.raw.get("spacing", 0.5))
                    n_eff = max(1, len(o.raw["segments"]))
                else:
                    poly = o.raw["polygon"]
                    samp = _outline_samples(poly, o.raw.get("spacing", 0.5))
                    n_eff = max(4, len(poly) - 1)
                self._cache[id(o)] = (samp, math.sqrt(max(len(samp), 1) / n_eff))

    def residuals(self, wings, nuis, with_meta=False):
        """Return normalised residual vector (pred-obs)/sigma and per-row obs index."""
        self._cur = None  # lazily built model for this parameter set
        rows, owner = [], []
        for k, o in enumerate(self.obs):
            t = o.target
            if t == "roof_z":
                pts = np.asarray(o.raw["points"], float)
                dz = nuis.get(o.raw.get("dz_param", ""), 0.0)
                z = _surface(wings, pts[:, :2])
                r = (z - (pts[:, 2] + dz)) / o.sigma
                out = np.isnan(z)
                if out.any():
                    # roof points the model does not cover: penalise by distance to the model outline
                    # (continuous, so the model cannot shrink away from evidence for free)
                    import shapely
                    from shapely.ops import unary_union
                    outline = unary_union([w.roof_outline() for w in wings])
                    d = shapely.distance(outline, shapely.points(pts[out, :2]))
                    r[out] = d / float(o.raw.get("outside_sigma", 0.5))
                rows.extend(r.tolist())
                owner.extend([k] * len(r))
                continue
            if t == "outline":
                model = self._model(wings)
                samp, infl = self._cache[id(o)]
                sh = o.raw.get("shift")
                if sh:
                    samp = samp + np.array([nuis.get(f"shift.{sh}.dx", 0.0), nuis.get(f"shift.{sh}.dy", 0.0)])
                geom = model.roof_outline() if o.raw.get("which", "roof_outline") == "roof_outline" else model.footprint()
                b = geom.boundary
                r = []
                for x, y in samp:
                    p = Point(x, y)
                    d = b.distance(p)
                    r.append((d if not geom.contains(p) else -d) / (o.sigma * infl))
                rows.extend(r)
                owner.extend([k] * len(r))
                continue
            pred = self.predict_scalar(o, wings)
            rows.append((pred - o.value) / o.sigma if kind_of(t) != "angle"
                        else (((pred - o.value + 180) % 360) - 180) / o.sigma)
            owner.append(k)
        return np.array(rows, float), np.array(owner, int)

    # scalar predictions -------------------------------------------------------
    def predict_scalar(self, o, wings):
        t = o.target
        if t in ("pitch@", "azimuth@", "z@"):
            model = self._model(wings)
            x, y = o.raw["xy"]
            f = model.facet_at(x, y)
            if f is None:
                # nearest facet
                p = Point(x, y)
                f = min(model.facets, key=lambda ff: ff.poly.distance(p))
            if t == "pitch@":
                return f.slope
            if t == "azimuth@":
                return plane_azimuth(f.plane) or 0.0
            return f.z(x, y)
        m = re.match(r"^([A-Za-z0-9_\-]+)\.([a-z_]+)$", t)
        if m and m.group(1) not in ("roof", "edge", "footprint", "wall", "building", "roof_outline", "wing"):
            wid, fld = m.groups()
            for w in wings:
                if w.id == wid:
                    v = getattr(w, fld)
                    return float(v if v is not None else _implicit(w, fld))
            raise KeyError(f"observation target {t!r}: no wing {wid!r}")
        meas = self._meas(wings)
        if t not in meas:
            raise KeyError(f"unknown observation target {t!r}; known: {sorted(meas)}")
        return meas[t]

    def _model(self, wings):
        if self._cur is None or self._cur[0] is not wings:
            self._cur = [wings, build(wings), None]
        return self._cur[1]

    def _meas(self, wings):
        self._model(wings)
        if self._cur[2] is None:
            self._cur[2] = self._cur[1].measurements()
        return self._cur[2]


def _surface(wings, xy):
    zs = np.stack([w.surface_z(xy) for w in wings])
    with np.errstate(all="ignore"):
        allnan = np.all(np.isnan(zs), axis=0)
        z = np.nanmax(np.where(np.isnan(zs), -np.inf, zs), axis=0)
    z[allnan] = np.nan
    return z


# ---------------------------------------------------------------------------
# solver
# ---------------------------------------------------------------------------

def _huber_w(r, k=HUBER_K):
    a = np.abs(r)
    return np.where(a <= k, 1.0, k / np.maximum(a, 1e-12))


def _fit_once(spec: dict, observations: List[dict], max_iter=40, robust=True, verbose=False, mc_samples=48):
    """Fit wing parameters. ``spec`` = {"wings": [...], "free": [...], "ties": [...],
    "priors": {name: {"value": v, "sigma": s}}, "nuisance": [...]}."""
    obs = prepare(active(observations))
    nuis_names = list(spec.get("nuisance", []))
    for o in obs:
        if o.target == "outline" and o.raw.get("shift"):
            for ax in ("dx", "dy"):
                nm = f"shift.{o.raw['shift']}.{ax}"
                if nm not in nuis_names:
                    nuis_names.append(nm)
        if o.target == "roof_z" and str(o.raw.get("dz_param", "")).startswith("shift.") \
                and o.raw["dz_param"] not in nuis_names:
            nuis_names.append(o.raw["dz_param"])
    ps = ParamSpace(spec["wings"], spec.get("free", []), spec.get("ties", []), nuis_names)
    pred = Predictor(obs)
    priors = []
    for name, pr in (spec.get("priors") or {}).items():
        if name in ps.names:
            i = ps.names.index(name)
            fld = name.split(".", 1)[1]
            tgt = fld if not name.startswith("shift.") else "length"
            v = parse_value(tgt, pr["value"])
            priors.append((i, v, parse_sigma(tgt, pr["sigma"], v)))
    for i, nm in enumerate(ps.names):  # weak default prior on nuisance shifts (2 m)
        if nm.startswith("shift.") and not any(p[0] == i for p in priors):
            priors.append((i, 0.0, 2.0))

    def full_res(x):
        wings, nuis = ps.apply(x)
        r, own = pred.residuals(wings, nuis)
        rp = np.array([(x[i] - v) / s for i, v, s in priors]) if priors else np.zeros(0)
        return np.concatenate([r, rp]), np.concatenate([own, -1 - np.arange(len(rp))])

    x = ps.clamp(ps.x0())
    n = len(x)
    lam = 1e-3
    r, own = full_res(x)
    w = _huber_w(r) if robust else np.ones_like(r)
    cost = float(np.sum(w * r * r))
    history = [cost]
    J = np.zeros((len(r), n))
    for it in range(max_iter if n else 0):
        h = ps.steps(x)
        J = np.zeros((len(r), n))
        for j in range(n):
            xp = x.copy()
            xp[j] += h[j]
            xm = x.copy()
            xm[j] -= h[j]
            J[:, j] = (full_res(xp)[0] - full_res(xm)[0]) / (2 * h[j])
        sw = np.sqrt(w)
        Jw, rw = J * sw[:, None], r * sw
        A = Jw.T @ Jw
        g = Jw.T @ rw
        improved = False
        for _ in range(12):
            try:
                dx = -np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-9), g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            xn = ps.clamp(x + dx)
            rn, _ = full_res(xn)
            wn = _huber_w(rn) if robust else np.ones_like(rn)
            cn = float(np.sum(wn * rn * rn))
            if cn < cost:
                x, r, w = xn, rn, wn
                rel = (cost - cn) / max(cost, 1e-12)
                cost = cn
                lam = max(lam / 3, 1e-9)
                improved = True
                break
            lam *= 4
        history.append(cost)
        if verbose:
            print(f"iter {it}: cost {cost:.4f} lambda {lam:.2e}")
        if not improved or rel < 1e-7:
            break

    # ---- covariance --------------------------------------------------------
    sw = np.sqrt(w)
    Jw = J * sw[:, None]
    dof = max(len(r) - n, 1)
    s2 = cost / dof
    try:
        C = np.linalg.pinv(Jw.T @ Jw) * max(1.0, s2)
    except np.linalg.LinAlgError:
        C = np.full((n, n), np.nan)
    wings, nuis = ps.apply(x)
    model = build(wings)
    meas = model.measurements()

    # propagate to every measurement by Monte-Carlo sampling of the parameter covariance.
    # Robust (MAD) spread: derived quantities such as edge lengths are piecewise-smooth
    # (an edge can change class), where linear propagation explodes.
    meas_sigma = {}
    if n and np.all(np.isfinite(C)):
        rng = np.random.default_rng(12345)
        try:
            Lc = np.linalg.cholesky(C + 1e-12 * np.eye(n))
        except np.linalg.LinAlgError:
            w_, V_ = np.linalg.eigh(C)
            Lc = V_ @ np.diag(np.sqrt(np.clip(w_, 0, None)))
        samples = []
        for _ in range(mc_samples):
            xs = ps.clamp(x + Lc @ rng.standard_normal(n))
            try:
                samples.append(build(ps.apply(xs)[0]).measurements())
            except Exception:
                continue
        for k in meas:
            vals = np.array([sm.get(k, np.nan) for sm in samples], float)
            vals = vals[np.isfinite(vals)]
            if len(vals) >= 5:
                meas_sigma[k] = float(1.4826 * np.median(np.abs(vals - np.median(vals))))

    # residual table (unweighted, in sigma units)
    table = []
    r_unw, own = pred.residuals(wings, nuis)
    for k, o in enumerate(obs):
        rk = r_unw[own == k]
        entry = {"target": o.target, "source": o.source, "kind": o.raw.get("kind", ""),
                 "n": int(len(rk)), "sigma": o.sigma}
        if o.value is not None and len(rk) == 1:
            entry.update({"observed": o.value, "predicted": o.value + rk[0] * o.sigma,
                          "residual_sigma": float(rk[0])})
            entry["flag"] = "CONFLICT" if abs(rk[0]) > 3 else ("check" if abs(rk[0]) > 2 else "ok")
        else:
            # outline rows are divided by sigma * infl (correlated-sample deflation); undo it here so
            # the table reports true distances and per-sample sigma units
            infl = pred._cache[id(o)][1] if o.target == "outline" else 1.0
            rk = rk * infl
            rms = float(np.sqrt(np.mean(rk ** 2))) if len(rk) else 0.0
            entry.update({"rms_sigma": rms, "frac_gt3": float(np.mean(np.abs(rk) > 3)) if len(rk) else 0.0,
                          "rms_m": rms * o.sigma})
            entry["flag"] = "CONFLICT" if rms > 3 else ("check" if rms > 1.5 else "ok")
        table.append(entry)

    params = {}
    for i, g in enumerate(ps.groups):
        params[g[0]] = {"value": float(x[i]), "sigma": float(math.sqrt(max(C[i, i], 0))) if n else 0.0,
                        "tied": g[1:]}
    return {
        "wings": [w.to_dict() for w in wings],
        "params": params,
        "nuisance": {k: v for k, v in nuis.items()},
        "measurements": meas,
        "measurement_sigma": meas_sigma,
        "residuals": table,
        "chi2": cost, "dof": dof, "variance_factor": s2,
        "iterations": len(history) - 1,
    }


def fit(spec: dict, observations: List[dict], max_iter=40, robust=True, verbose=False,
        snoop=True, snoop_threshold=4.0, max_excluded=5):
    """Robust fit + data snooping (Baarda-style blunder rejection).

    After each fit the scalar observation with the largest |residual| above
    ``snoop_threshold`` sigma is excluded and the fit repeated, so one bad number (an old
    report from before an addition, a unit slip) cannot drag the model. Excluded
    observations stay in the residual table, flagged EXCLUDED, with the value the final
    model predicts for them. Vector evidence (LiDAR, outlines) is never auto-excluded.
    """
    global _GROUND
    _GROUND = tuple(spec["ground"]) if spec.get("ground") else None
    use = active(observations)
    excluded = []
    res = _fit_once(spec, use, max_iter, robust, verbose)
    while snoop and len(excluded) < max_excluded:
        worst, wr = None, snoop_threshold
        for i, r in enumerate(res["residuals"]):
            if "residual_sigma" in r and abs(r["residual_sigma"]) > wr:
                worst, wr = i, abs(r["residual_sigma"])
        if worst is None:
            break
        excluded.append(use.pop(worst))
        if verbose:
            print(f"excluding blunder: {excluded[-1].get('source')} -> {excluded[-1]['target']} ({wr:.1f} sigma)")
        res = _fit_once(spec, use, max_iter, robust, verbose)
    if excluded:
        wings = [Wing.from_dict(w) for w in res["wings"]]
        pred = Predictor(prepare(excluded))
        pred._cur = None
        for o in pred.obs:
            p_ = pred.predict_scalar(o, wings)
            r = (p_ - o.value) / o.sigma
            res["residuals"].append({"target": o.target, "source": o.source, "kind": o.raw.get("kind", ""),
                                     "n": 1, "sigma": o.sigma, "observed": o.value, "predicted": p_,
                                     "residual_sigma": float(r), "flag": "EXCLUDED"})
    res["excluded"] = excluded
    return res
