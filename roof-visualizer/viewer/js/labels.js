// Exploded-view callouts: labels stacked in a column beside the roof with
// leader lines to an anchor on each layer. The same layout is used on screen
// and when burning labels into high-resolution snapshots.

import * as THREE from 'three';

const _p = new THREE.Vector3();

/** Project label anchors and lay the labels out without overlaps. */
export function layoutLabels(items, camera, { width, height, labelW = 250, labelH = 40, gap = 6, margin = 16 }) {
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
  let side = 'right';
  let colX = maxX + 56;
  if (colX + labelW > width - margin) {
    if (minX - 56 - labelW > margin) { side = 'left'; colX = minX - 56 - labelW; }
    else colX = width - margin - labelW;
  }
  // top-to-bottom order follows the anchors; push down to resolve overlaps, then pull up to fit
  pts.sort((a, b) => a.sy - b.sy);
  const step = labelH + gap;
  let y = -Infinity;
  for (const p of pts) { p.ly = Math.max(p.sy - labelH / 2, y + step); y = p.ly; }
  const overflow = y + labelH - (height - margin);
  if (overflow > 0) pts.forEach((p) => { p.ly -= overflow; });
  if (pts[0].ly < margin) { const d = margin - pts[0].ly; pts.forEach((p) => { p.ly += d; }); }
  for (const p of pts) { p.lx = colX; p.side = side; }
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
    const placed = layoutLabels(items, camera, { width, height, labelW: width < 600 ? 190 : 250, labelH: width < 600 ? 36 : 42 });
    const seen = new Set();
    let paths = '';
    for (const p of placed) {
      seen.add(p.id);
      let el = this.nodes.get(p.id);
      if (!el) {
        el = document.createElement('div');
        el.className = 'callout';
        el.innerHTML = '<b></b><i></i>';
        this.root.append(el);
        this.nodes.set(p.id, el);
      }
      el.querySelector('b').textContent = p.title;
      el.querySelector('i').textContent = p.spec;
      el.style.transform = `translate(${p.lx.toFixed(1)}px, ${p.ly.toFixed(1)}px)`;
      el.style.opacity = String(p.opacity ?? 1);
      el.hidden = false;
      const ly = p.ly + (width < 600 ? 18 : 21);
      const ex = p.side === 'right' ? p.lx : p.lx + (width < 600 ? 190 : 250);
      const mx = p.side === 'right' ? ex - 18 : ex + 18;
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
  const placed = layoutLabels(items, camera, { width, height, labelW, labelH, gap: 6 * s, margin: 16 * s });
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
