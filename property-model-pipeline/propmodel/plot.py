"""Overview images (PIL only) so an agent or a person can *look* at the evidence.

Layers drawn in the local ENU frame on top of the orthophoto: footprint candidates,
LiDAR roof points coloured by height, detected planes (arrow = downslope), the current
model's facets and edges. Use it after every step — most blunders are obvious visually.
"""
from __future__ import annotations

import json
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

EDGE_COLORS = {"ridge": (255, 40, 40), "hip": (255, 140, 0), "valley": (40, 120, 255), "eave": (0, 220, 0),
               "rake": (0, 200, 200), "transition": (200, 0, 200), "headwall": (255, 255, 0), "sidewall": (255, 220, 120)}
PALETTE = [(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180),
           (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255)]


def _colormap(t):
    t = np.clip(t, 0, 1)
    r = np.clip(1.5 - np.abs(4 * t - 3), 0, 1)
    g = np.clip(1.5 - np.abs(4 * t - 2), 0, 1)
    b = np.clip(1.5 - np.abs(4 * t - 1), 0, 1)
    return (np.stack([r, g, b], 1) * 255).astype(int)


class Canvas:
    def __init__(self, bounds, px=1024, background=None, bg_bounds=None):
        self.b = bounds  # (x0, y0, x1, y1) local metres
        self.px = px
        w = bounds[2] - bounds[0]
        self.s = px / w
        self.h = int(round((bounds[3] - bounds[1]) * self.s))
        if background is not None:
            bg = Image.open(background).convert("RGB")
            bb = bg_bounds
            # crop/scale the ortho to our bounds
            sx = bg.width / (bb[2] - bb[0])
            sy = bg.height / (bb[3] - bb[1])
            box = ((bounds[0] - bb[0]) * sx, (bb[3] - bounds[3]) * sy, (bounds[2] - bb[0]) * sx, (bb[3] - bounds[1]) * sy)
            self.img = bg.crop(tuple(int(round(v)) for v in box)).resize((px, self.h), Image.LANCZOS)
            self.img = Image.blend(self.img, Image.new("RGB", self.img.size, (0, 0, 0)), 0.25)
        else:
            self.img = Image.new("RGB", (px, self.h), (25, 25, 30))
        self.d = ImageDraw.Draw(self.img, "RGBA")
        try:
            self.font = ImageFont.load_default(size=14)
        except TypeError:
            self.font = ImageFont.load_default()

    def xy(self, x, y):
        return ((x - self.b[0]) * self.s, (self.b[3] - y) * self.s)

    def poly(self, ring, color, width=2, fill=None):
        pts = [self.xy(*p[:2]) for p in ring]
        if fill:
            self.d.polygon(pts, fill=fill)
        self.d.line(pts + [pts[0]], fill=color, width=width)

    def line(self, a, b, color, width=3):
        self.d.line([self.xy(*a[:2]), self.xy(*b[:2])], fill=color, width=width)

    def text(self, x, y, s, color=(255, 255, 255)):
        X, Y = self.xy(x, y)
        self.d.text((X + 1, Y + 1), s, fill=(0, 0, 0), font=self.font)
        self.d.text((X, Y), s, fill=color, font=self.font)

    def points(self, xy, colors, r=1.5):
        for (x, y), c in zip(xy, colors):
            X, Y = self.xy(x, y)
            self.d.ellipse([X - r, Y - r, X + r, Y + r], fill=tuple(int(v) for v in c))

    def scalebar(self, meters=5):
        x0, y0 = 20, self.h - 30
        L = meters * self.s
        self.d.rectangle([x0 - 4, y0 - 18, x0 + L + 50, y0 + 10], fill=(0, 0, 0, 160))
        self.d.line([(x0, y0), (x0 + L, y0)], fill=(255, 255, 255), width=4)
        self.d.text((x0 + L + 6, y0 - 8), f"{meters} m", fill=(255, 255, 255), font=self.font)
        # north arrow
        self.d.polygon([(self.px - 30, 15), (self.px - 38, 40), (self.px - 22, 40)], fill=(255, 255, 255))
        self.d.text((self.px - 34, 42), "N", fill=(255, 255, 255), font=self.font)

    def legend(self, items):
        y = 10
        self.d.rectangle([8, 6, 240, 12 + 18 * len(items)], fill=(0, 0, 0, 170))
        for label, color in items:
            self.d.rectangle([14, y + 3, 30, y + 13], fill=color)
            self.d.text((36, y), label, fill=(255, 255, 255), font=self.font)
            y += 18

    def save(self, path):
        self.img.save(path)
        return path


def overview(path, bounds, ortho=None, ortho_meta=None, footprints=(), roof_pts=None, planes=(), model=None,
             title=None, px=1024):
    cv = Canvas(bounds, px, ortho, ortho_meta["bounds_local"] if ortho_meta else None)
    legend = []
    if roof_pts is not None and len(roof_pts) and roof_pts.shape[1] >= 4:
        lab = roof_pts[:, 3].astype(int)
        cols = np.array([PALETTE[l % len(PALETTE)] if l >= 0 else (90, 90, 90) for l in lab])
        cv.points(roof_pts[:, :2], cols, r=1.6)
        legend.append(("LiDAR pts by plane (grey=none)", (200, 200, 200)))
    elif roof_pts is not None and len(roof_pts):
        z = roof_pts[:, 2]
        t = (z - np.percentile(z, 2)) / max(np.percentile(z, 98) - np.percentile(z, 2), 1e-6)
        cv.points(roof_pts[:, :2], _colormap(t), r=1.4)
        legend.append((f"LiDAR {np.percentile(z, 2):.1f}-{np.percentile(z, 98):.1f} m", (255, 200, 0)))
    for i, p in enumerate(planes):
        c = PALETTE[i % len(PALETTE)]
        cx, cy = p["centroid"][:2]
        if p.get("azimuth") is not None:
            a = math.radians(p["azimuth"])
            cv.line((cx, cy), (cx + 1.5 * math.sin(a), cy + 1.5 * math.cos(a)), c, 3)
        cv.text(cx, cy, f"P{i + 1} {p['pitch_rise_per_12']:.1f}/12 h{p['z_max']:.1f}", c)
    for i, (name, ring) in enumerate(footprints):
        c = [(255, 255, 255), (0, 255, 255), (255, 0, 255), (255, 255, 0)][i % 4]
        cv.poly(ring, c, 2)
        legend.append((name, c))
    if model is not None:
        for f in model.facets:
            from .roofgeom import _polys
            for pg in _polys(f.poly):
                cv.poly(list(pg.exterior.coords), (255, 255, 255, 90), 1, fill=(255, 255, 255, 35))
            c = f.poly.representative_point()
            cv.text(c.x, c.y, f"{f.id} {f.slope * 12:.1f}/12", (255, 255, 255))
        for e in model.edges:
            cv.line(e.p0, e.p1, EDGE_COLORS.get(e.kind, (255, 255, 255)), 3)
        legend += [(k, v) for k, v in EDGE_COLORS.items() if model.edge_total(k) > 0]
    if title:
        cv.d.rectangle([0, cv.h - 56, cv.px, cv.h - 36], fill=(0, 0, 0, 150))
        cv.d.text((10, cv.h - 54), title, fill=(255, 255, 255), font=cv.font)
    if legend:
        cv.legend(legend)
    cv.scalebar(5)
    return cv.save(path)
