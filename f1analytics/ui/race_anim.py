import json

import streamlit.components.v1 as components

SPEEDS = [1, 2, 5, 10]

TEMPLATE = """
<div id="wrap" style="position:relative;width:100%;height:__H__px;background:transparent;font-family:'Titillium Web',system-ui,sans-serif">
  <canvas id="c" style="width:100%;height:100%;display:block"></canvas>
  <div id="hud" style="position:absolute;left:8px;top:6px;color:#9A9AA8;font-size:12px"></div>
  <div style="position:absolute;right:6px;top:4px;display:flex;gap:4px" id="btns"></div>
</div>
<link href="https://fonts.googleapis.com/css2?family=Titillium+Web:wght@400;700&display=swap" rel="stylesheet">
<script>
const D = __DATA__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d'), hud = document.getElementById('hud');
let speed = D.speed, t0 = performance.now(), paused = false, pauseAt = 0;
const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const btns = document.getElementById('btns');
function mkBtn(label, on) { const b = document.createElement('button'); b.textContent = label;
  b.style.cssText = 'background:#1F1F2B;color:#F3F3F5;border:1px solid #2E2E3A;border-radius:4px;font:700 11px Titillium Web,sans-serif;padding:2px 7px;cursor:pointer';
  b.onclick = on; btns.appendChild(b); return b; }
const pb = mkBtn('❚❚', () => { if (paused) { t0 = performance.now() - pauseAt * 1000 / speed; paused = false; pb.textContent = '❚❚'; } else { pauseAt = now(); paused = true; pb.textContent = '▶'; } });
D.speeds.forEach(s => { const b = mkBtn(s + '×', () => { const cur = now(); speed = s; t0 = performance.now() - cur * 1000 / speed; mark(); }); b.dataset.s = s; });
function mark() { [...btns.children].forEach(b => { if (b.dataset.s) b.style.background = (+b.dataset.s === speed) ? '#E10600' : '#1F1F2B'; }); }
mark();
function now() { return paused ? pauseAt : ((performance.now() - t0) / 1000 * speed) % D.duration; }
let box;
function fit() {
  const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  cv.width = r.width * dpr; cv.height = r.height * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const xs = D.outline.x, ys = D.outline.y;
  const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
  const pad = 26, s = Math.min((r.width - 2 * pad) / (maxx - minx), (r.height - 2 * pad - 14) / (maxy - miny));
  box = { s, ox: (r.width - s * (maxx - minx)) / 2 - s * minx, oy: (r.height + 14 + s * (maxy - miny)) / 2 + s * miny };
}
function P(x, y) { return [box.ox + box.s * x, box.oy - box.s * y]; }
const N = D.outline.x.length, SEG = D.total / N;
function onTrack(s) {
  s = ((s % D.total) + D.total) % D.total; const f = s / SEG, i = Math.floor(f) % N, j = (i + 1) % N, w = f - Math.floor(f);
  return [D.outline.x[i] + w * (D.outline.x[j] - D.outline.x[i]), D.outline.y[i] + w * (D.outline.y[j] - D.outline.y[i])];
}
function at(c, t) {
  const T = c.t, S = c.s, n = T.length; let s;
  if (t <= T[0]) s = S[0]; else if (t >= T[n - 1]) s = S[n - 1];
  else { let lo = 0, hi = n - 1; while (hi - lo > 1) { const m = (lo + hi) >> 1; if (T[m] <= t) lo = m; else hi = m; }
    const f = (t - T[lo]) / (T[hi] - T[lo] || 1); s = S[lo] + f * (S[hi] - S[lo]); }
  return onTrack(s);
}
function draw() {
  const r = cv.getBoundingClientRect(); ctx.clearRect(0, 0, r.width, r.height);
  ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  [[10, '#2E2E3A'], [6, '#1F1F2B']].forEach(([w, col]) => { ctx.beginPath(); D.outline.x.forEach((x, i) => { const [a, b] = P(x, D.outline.y[i]); i ? ctx.lineTo(a, b) : ctx.moveTo(a, b); }); ctx.closePath(); ctx.lineWidth = w; ctx.strokeStyle = col; ctx.stroke(); });
  const [sx, sy] = P(D.outline.x[0], D.outline.y[0]); ctx.fillStyle = '#F3F3F5'; ctx.fillRect(sx - 1.5, sy - 7, 3, 14);
  const t = now();
  const order = D.cars.slice().sort((a, b) => a.size - b.size);
  for (const c of order) {
    const [x, y] = at(c, t), [a, b] = P(x, y);
    ctx.beginPath(); ctx.arc(a, b, c.size, 0, 2 * Math.PI); ctx.fillStyle = c.colour; ctx.fill();
    ctx.lineWidth = c.focus ? 2.5 : 1.2; ctx.strokeStyle = c.focus ? '#FFFFFF' : '#15151E'; ctx.stroke();
    if (c.label) { ctx.font = (c.focus ? '700 13px' : '700 11px') + ' Titillium Web, sans-serif'; ctx.fillStyle = '#F3F3F5'; ctx.textAlign = 'center'; ctx.fillText(c.code, a, b - c.size - 4); }
  }
  const m = Math.floor(t / 60), s = Math.floor(t % 60);
  hud.textContent = D.title + ' · ' + m + ':' + String(s).padStart(2, '0') + ' / ' + Math.floor(D.duration / 60) + ':' + String(Math.floor(D.duration % 60)).padStart(2, '0');
  if (!reduce || paused === false) requestAnimationFrame(draw);
}
fit(); window.addEventListener('resize', () => { fit(); }); requestAnimationFrame(draw);
</script>
"""


def render(outline, total, cars, duration, title, speed=2, height=340):
    data = {"outline": outline, "total": total, "cars": cars, "duration": float(max(duration, 1.0)), "title": title, "speed": speed, "speeds": SPEEDS}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__H__", str(int(height)))
    components.html(html, height=height + 4)
    return html


def _resample(xs, ys, step):
    import numpy as np

    x = np.asarray(list(xs) + [xs[0]], float)
    y = np.asarray(list(ys) + [ys[0]], float)
    seg = np.hypot(np.diff(x), np.diff(y))
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = float(cum[-1])
    s = np.arange(0, total, step)
    return np.interp(s, cum, x), np.interp(s, cum, y), total


def project_traces(outline_x, outline_y, traces, step=None):
    """Snap each car's GPS samples onto the circuit line and return distance-along-track over time.

    traces: {num: (t[], x[], y[])}. Returns (ox, oy, total_length, {num: (t[], s[])}) where s is unwrapped distance.
    """
    import numpy as np

    span = max(np.ptp(outline_x), np.ptp(outline_y))
    ox, oy, total = _resample(outline_x, outline_y, step or span / 900)
    n = len(ox)
    seg_len = total / n
    out = {}
    for num, (t, x, y) in traces.items():
        t, x, y = np.asarray(t, float), np.asarray(x, float), np.asarray(y, float)
        if len(t) < 3:
            continue
        d2 = (x[:, None] - ox[None, :]) ** 2 + (y[:, None] - oy[None, :]) ** 2
        idx = d2.argmin(axis=1)
        s = idx * seg_len
        for i in range(1, len(s)):
            while s[i] < s[i - 1] - total / 2:
                s[i] += total
            while s[i] > s[i - 1] + total / 2:
                s[i] -= total
        s = np.maximum.accumulate(s)
        s = s - (s[0] // total) * total
        k = min(5, len(s))
        if k >= 3:
            pad = np.pad(s, (k // 2, k // 2), mode="edge")
            s = np.convolve(pad, np.ones(k) / k, mode="valid")
        out[num] = (t.round(2).tolist(), s.round(1).tolist())
    return ox.round(1).tolist(), oy.round(1).tolist(), float(total), out
