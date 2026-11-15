// Exploded-view callouts: labels stacked in a column beside the roof with
// leader lines to an anchor on each layer. The same layout is used on screen
// and when burning labels into high-resolution snapshots.

import * as THREE from 'three';

const _p = new THREE.Vector3();

/** Label size for a given 3D view width. Shared with the camera framing in app.js. */
export function labelMetrics(width) {
  if (width < 520) return { labelW: 134, labelH: 26, lead: 20, mode: 'compact' }; // title only
  if (width < 780) return { labelW: 196, labelH: 34, lead: 36, mode: 'mid' };
  return { labelW: 250, labelH: 42, lead: 56, mode: 'full' };
}

/** Screen space the on-screen chrome covers (top bar, toolbar), in px. */
export const SCREEN_INSETS = { top: 64, bottom: 80, side: 16 };

/** Pixels to keep free on the right of the 3D view for the label column. */
export function labelReserve(width) {
  const m = labelMetrics(width);
  return m.labelW + m.lead + SCREEN_INSETS.side;
}

/**
 * Project label anchors and lay the labels out in one column without overlaps.
 * The column sits right of the model when it fits, else against the right edge
 * (the camera framing leaves that strip free), and only uses the left side when
 * the right edge would cover the anchors and the left has room.
 */
export function layoutLabels(items, camera, { width, height, labelW = 250, labelH = 42, gap = 6, top = 16, bottom = 16, side = 16, lead = 56 }) {
  const pts = [];
  for (const it of items) {
    if (!it.show) continue;
    it.object.getWorldPosition(_p);
    _p.project(camera);
    if (_p.z > 1 || _p.z < -1) continue;
    pts.push({ ...it, sx: (_p.x * 0.5 + 0.5) * width, sy: (-_p.y * 0.5 + 0.5) * height });
  }
  if (!pts.length) return [];
  const maxX = Math.max(...pts.map((p) => p.sx)), minX = Math.min(...pts.map((p) => p.sx));
  let colX = Math.min(maxX + lead, width - side - labelW);
  let where = 'right';
  if (colX < maxX + 12) {
    const leftX = minX - lead - labelW;
    if (leftX >= side) { where = 'left'; colX = leftX; }
  }
  // vertical: keep inside [top, height - bottom]; squeeze the spacing when there are many layers
  const avail = Math.max(labelH, height - top - bottom);
  const step = Math.min(labelH + gap, Math.max(labelH * 0.7, (avail - labelH) / Math.max(1, pts.length - 1)));
  pts.sort((a, b) => a.sy - b.sy);
  let y = -Infinity;
  for (const p of pts) { p.ly = Math.max(p.sy - labelH / 2, y + step); y = p.ly; }
  const overflow = y + labelH - (height - bottom);
  if (overflow > 0) pts.forEach((p) => { p.ly -= overflow; });
  if (pts[0].ly < top) { const d = top - pts[0].ly; pts.forEach((p) => { p.ly += d; }); }
  for (const p of pts) { p.lx = colX; p.side = where; }
  return pts;
}

export class LabelOverlay {
  constructor(container) {
    this.root = container;
    this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    this.svg.setAttribute('class', 'leader-lines');
    this.root.append(this.svg);
    this.nodes = new Map();
  }

  update(items, camera, width, height) {
    const m = labelMetrics(width);
    const placed = layoutLabels(items, camera, { width, height, labelW: m.labelW, labelH: m.labelH, lead: m.lead, gap: m.mode === 'compact' ? 4 : 6, ...SCREEN_INSETS });
    const seen = new Set();
    let paths = '';
    for (const p of placed) {
      seen.add(p.id);
      let el = this.nodes.get(p.id);
      if (!el) {
        el = document.createElement('div');
        el.innerHTML = '<b></b><i></i>';
        this.root.append(el);
        this.nodes.set(p.id, el);
      }
      el.className = `callout ${m.mode}`;
      el.style.width = `${m.labelW}px`;
      el.style.height = `${m.labelH}px`;
      el.querySelector('b').textContent = p.title;
      el.querySelector('i').textContent = p.spec;
      el.title = `${p.title}: ${p.spec}`;
      el.style.transform = `translate(${p.lx.toFixed(1)}px, ${p.ly.toFixed(1)}px)`;
      el.style.opacity = String(p.opacity ?? 1);
      el.hidden = false;
      const ly = p.ly + m.labelH / 2;
      const ex = p.side === 'right' ? p.lx : p.lx + m.labelW;
      const mx = p.side === 'right' ? ex - Math.min(18, m.lead / 2) : ex + Math.min(18, m.lead / 2);
      paths += `<path d="M${p.sx.toFixed(1)} ${p.sy.toFixed(1)} L${mx.toFixed(1)} ${ly.toFixed(1)} L${ex.toFixed(1)} ${ly.toFixed(1)}" style="opacity:${p.opacity ?? 1}"/><circle cx="${p.sx.toFixed(1)}" cy="${p.sy.toFixed(1)}" r="3.5" style="opacity:${p.opacity ?? 1}"/>`;
    }
    for (const [id, el] of this.nodes) if (!seen.has(id)) el.hidden = true;
    this.svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    this.svg.innerHTML = paths;
  }
}

/** Draw the same callouts into a 2D canvas (snapshot export). */
export function drawCallouts(ctx, items, camera, width, height) {
  const s = Math.max(1, width / 1600);
  const labelW = 250 * s, labelH = 42 * s;
  const placed = layoutLabels(items, camera, { width, height, labelW, labelH, gap: 6 * s, top: 16 * s, bottom: 16 * s, side: 16 * s, lead: 56 * s });
  ctx.save();
  for (const p of placed) {
    ctx.globalAlpha = p.opacity ?? 1;
    const ly = p.ly + labelH / 2;
    const ex = p.side === 'right' ? p.lx : p.lx + labelW;
    const mx = p.side === 'right' ? ex - 18 * s : ex + 18 * s;
    ctx.strokeStyle = '#4c9cff'; ctx.lineWidth = 1.6 * s;
    ctx.beginPath(); ctx.moveTo(p.sx, p.sy); ctx.lineTo(mx, ly); ctx.lineTo(ex, ly); ctx.stroke();
    ctx.fillStyle = '#4c9cff'; ctx.beginPath(); ctx.arc(p.sx, p.sy, 3.5 * s, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'rgba(18,23,31,0.9)';
    roundRect(ctx, p.lx, p.ly, labelW, labelH, 6 * s); ctx.fill();
    ctx.fillStyle = '#f3f5f8';
    ctx.font = `600 ${14 * s}px "Barlow Semi Condensed", Barlow, system-ui, sans-serif`;
    ctx.fillText(fit(ctx, p.title, labelW - 20 * s), p.lx + 10 * s, p.ly + 18 * s);
    ctx.fillStyle = '#a9b3c1';
    ctx.font = `${12 * s}px Barlow, system-ui, sans-serif`;
    ctx.fillText(fit(ctx, p.spec, labelW - 20 * s), p.lx + 10 * s, p.ly + 34 * s);
  }
  ctx.restore();
}

function fit(ctx, text, w) {
  if (ctx.measureText(text).width <= w) return text;
  let t = text;
  while (t.length > 3 && ctx.measureText(t + '…').width > w) t = t.slice(0, -1);
  return t + '…';
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
