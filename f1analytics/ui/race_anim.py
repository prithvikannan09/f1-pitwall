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


RACE_SPEEDS = [1, 5, 10, 20, 50]

RACE_TEMPLATE = """
<div style="width:100%;font-family:'Titillium Web',system-ui,sans-serif;color:#F3F3F5">
  <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px">
    <button id="pp" class="b">❚❚</button>
    <span id="speeds" style="display:flex;gap:4px"></span>
    <span id="hud" style="margin-left:auto;color:#9A9AA8;font-size:12px"></span>
  </div>
  <div style="position:relative;width:100%;height:__H__px"><canvas id="c" style="width:100%;height:100%;display:block"></canvas>
    <div id="lap" style="position:absolute;left:6px;top:4px;font:800 italic 18px 'Titillium Web',sans-serif"></div></div>
  <input id="scrub" type="range" min="0" max="1000" value="0" style="width:100%;accent-color:#E10600">
</div>
<style>.b{background:#1F1F2B;color:#F3F3F5;border:1px solid #2E2E3A;border-radius:4px;font:700 11px 'Titillium Web',sans-serif;padding:3px 8px;cursor:pointer}.b.on{background:#E10600;border-color:#E10600}</style>
<link href="https://fonts.googleapis.com/css2?family=Titillium+Web:ital,wght@0,400;0,700;1,800&display=swap" rel="stylesheet">
<script>
const D = __DATA__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const hud = document.getElementById('hud'), lapEl = document.getElementById('lap'), scrub = document.getElementById('scrub'), pp = document.getElementById('pp');
let speed = D.speed, simT = D.start, last = performance.now(), paused = false, dragging = false;
const sp = document.getElementById('speeds');
D.speeds.forEach(s => { const b = document.createElement('button'); b.className = 'b' + (s === speed ? ' on' : ''); b.textContent = s + '×';
  b.onclick = () => { speed = s; [...sp.children].forEach(x => x.classList.toggle('on', x === b)); }; sp.appendChild(b); });
pp.onclick = () => { paused = !paused; pp.textContent = paused ? '▶' : '❚❚'; };
scrub.oninput = () => { dragging = true; simT = D.t0 + (D.t1 - D.t0) * scrub.value / 1000; };
scrub.onchange = () => { dragging = false; };
const N = D.outline.x.length, L = D.total, SEG = L / N;
function onTrack(s) { s = ((s % L) + L) % L; const f = s / SEG, i = Math.floor(f) % N, j = (i + 1) % N, w = f - Math.floor(f);
  return [D.outline.x[i] + w * (D.outline.x[j] - D.outline.x[i]), D.outline.y[i] + w * (D.outline.y[j] - D.outline.y[i])]; }
function interp(xs, ys, x) { let lo = 0, hi = xs.length - 1; if (x <= xs[0]) return ys[0]; if (x >= xs[hi]) return ys[hi];
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] <= x) lo = m; else hi = m; }
  return ys[lo] + (x - xs[lo]) / (xs[hi] - xs[lo] || 1) * (ys[hi] - ys[lo]); }
function dist(c, t) {
  const E = c.e; if (t <= c.s0[0]) return { d: -c.grid * 16, live: true };
  let lo = 0, hi = E.length - 1;
  if (t >= E[hi]) return { d: (hi + 1) * L, live: t - E[hi] < 25 && !c.out, done: true };
  while (lo < hi) { const m = (lo + hi) >> 1; if (E[m] < t) lo = m + 1; else hi = m; }
  const k = lo, a = c.s0[k], b1 = c.b1[k], b2 = c.b2[k], e = E[k];
  let tau; if (t < b1) tau = D.tb[1] * (t - a) / (b1 - a); else if (t < b2) tau = D.tb[1] + (D.tb[2] - D.tb[1]) * (t - b1) / (b2 - b1); else tau = D.tb[2] + (1 - D.tb[2]) * (t - b2) / (e - b2);
  return { d: (k + interp(D.refT, D.refS, Math.min(Math.max(tau, 0), 1))) * L, live: true };
}
let box;
function fit() { const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1; cv.width = r.width * dpr; cv.height = r.height * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const xs = D.outline.x, ys = D.outline.y, minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys), pad = 24;
  const s = Math.min((r.width - 2 * pad) / (maxx - minx), (r.height - 2 * pad - 18) / (maxy - miny));
  box = { s, ox: (r.width - s * (maxx - minx)) / 2 - s * minx, oy: (r.height + 18 + s * (maxy - miny)) / 2 + s * miny }; }
function P(x, y) { return [box.ox + box.s * x, box.oy - box.s * y]; }
function fmt(sec) { sec = Math.max(0, sec); const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = Math.floor(sec % 60); return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0'); }
function frame(nowMs) {
  const dt = Math.min((nowMs - last) / 1000, 0.25); last = nowMs;
  if (!paused && !dragging) { simT += dt * speed; if (simT > D.t1) simT = D.t1; }
  if (!dragging) scrub.value = Math.round(1000 * (simT - D.t0) / (D.t1 - D.t0));
  const r = cv.getBoundingClientRect(); ctx.clearRect(0, 0, r.width, r.height); ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  [[10, '#2E2E3A'], [6, '#1F1F2B']].forEach(([w, col]) => { ctx.beginPath(); D.outline.x.forEach((x, i) => { const [a, b] = P(x, D.outline.y[i]); i ? ctx.lineTo(a, b) : ctx.moveTo(a, b); }); ctx.closePath(); ctx.lineWidth = w; ctx.strokeStyle = col; ctx.stroke(); });
  const [sx, sy] = P(D.outline.x[0], D.outline.y[0]); ctx.fillStyle = '#F3F3F5'; ctx.fillRect(sx - 1.5, sy - 8, 3, 16);
  const pos = D.cars.map(c => ({ c, ...dist(c, simT) })).filter(p => p.live);
  pos.sort((a, b) => b.d - a.d);
  const rank = {}; pos.forEach((p, i) => rank[p.c.code] = i + 1);
  const leadLap = pos.length ? Math.min(D.laps, Math.floor(pos[0].d / L) + 1) : 0;
  pos.slice().sort((a, b) => a.c.size - b.c.size).forEach(p => { const [x, y] = onTrack(p.d), [a, b] = P(x, y);
    ctx.beginPath(); ctx.arc(a, b, p.c.size, 0, 2 * Math.PI); ctx.fillStyle = p.c.colour; ctx.fill();
    ctx.lineWidth = p.c.focus ? 2.5 : 1.2; ctx.strokeStyle = p.c.focus ? '#FFFFFF' : '#15151E'; ctx.stroke();
    if (p.c.focus || p.c.mine || rank[p.c.code] <= 3) { ctx.font = (p.c.focus ? '700 13px' : '700 11px') + " 'Titillium Web',sans-serif"; ctx.fillStyle = '#F3F3F5'; ctx.textAlign = 'center';
      ctx.fillText((p.c.focus ? 'P' + rank[p.c.code] + ' ' : '') + p.c.code, a, b - p.c.size - 4); } });
  lapEl.textContent = simT < D.start0 ? 'Grid' : (leadLap >= D.laps && pos.length && pos[0].d >= D.laps * L ? 'Finish' : 'Lap ' + leadLap + ' / ' + D.laps);
  hud.textContent = 'Race time ' + fmt(simT - D.start0);
  requestAnimationFrame(frame);
}
fit(); window.addEventListener('resize', fit); requestAnimationFrame(frame);
</script>
"""


def race_payload(laps, drivers, total_laps, ref_t=None, ref_s=None, tb=None):
    """laps: DataFrame with DriverNumber, Driver, LapNumber, LapStartTime/Time (timedelta from session start), Sector1Time, Sector2Time."""
    import numpy as np
    import pandas as pd

    df = laps.copy()
    df["a"] = df["LapStartTime"].dt.total_seconds()
    df["e"] = df["Time"].dt.total_seconds()
    df = df.dropna(subset=["a", "e"])
    df = df[df["e"] > df["a"]]
    s1 = df["Sector1Time"].dt.total_seconds()
    s2 = df["Sector2Time"].dt.total_seconds()
    dur = df["e"] - df["a"]
    tb = tb or [0.0, 0.3, 0.65, 1.0]
    df["b1"] = np.where(s1.notna() & (s1 > 0) & (s1 < dur), df["a"] + s1, df["a"] + tb[1] * dur)
    df["b2"] = np.where(s1.notna() & s2.notna() & (s1 + s2 < dur), df["a"] + s1 + s2, df["a"] + tb[2] * dur)
    df["b2"] = np.maximum(df["b2"], df["b1"] + 0.1)
    start0 = float(df.loc[df["LapNumber"] == 1, "a"].min()) if (df["LapNumber"] == 1).any() else float(df["a"].min())
    first = df[df["LapNumber"] == 1].sort_values("e")
    grid_order = {n: i for i, n in enumerate(first["DriverNumber"].astype(str))}
    cars = []
    for num, g in df.sort_values("LapNumber").groupby("DriverNumber"):
        num = str(num)
        d = drivers.get(num) or {}
        g = g.sort_values("LapNumber").copy()
        a0 = g["a"].to_numpy(dtype=float).copy()
        e0 = g["e"].to_numpy(dtype=float)
        a0[1:] = e0[:-1]
        b1 = np.maximum(g["b1"].to_numpy(dtype=float), a0 + 0.1)
        b2 = np.maximum(g["b2"].to_numpy(dtype=float), b1 + 0.1)
        ok = e0 > b2 + 0.05
        g = g.assign(a=a0, b1=b1, b2=b2)[ok]
        if g.empty:
            continue
        cars.append({"code": d.get("code") or str(g["Driver"].iloc[0]), "colour": d.get("colour") or "#888",
                     "s0": g["a"].round(2).tolist(), "b1": g["b1"].round(2).tolist(), "b2": g["b2"].round(2).tolist(), "e": g["e"].round(2).tolist(),
                     "grid": grid_order.get(num, 10), "out": int(g["LapNumber"].max()) < int(total_laps)})
    end = float(df["e"].max())
    if ref_t is None or ref_s is None:
        ref_t, ref_s = [0.0, 1.0], [0.0, 1.0]
    return {"cars": cars, "t0": start0 - 20, "t1": end + 30, "start0": start0, "laps": int(total_laps),
            "refT": [round(x, 4) for x in ref_t], "refS": [round(x, 4) for x in ref_s], "tb": [round(x, 4) for x in tb]}


def reference_profile(t, s):
    """Turn one GPS lap (time, distance) into normalised time→distance fractions."""
    import numpy as np

    t, s = np.asarray(t, float), np.asarray(s, float)
    if len(t) < 10 or s[-1] - s[0] <= 0:
        return None, None
    ft = (t - t[0]) / (t[-1] - t[0])
    fs = (s - s[0]) / (s[-1] - s[0])
    grid = np.linspace(0, 1, 201)
    return grid.tolist(), np.clip(np.interp(grid, ft, fs), 0, 1).tolist()


def render_race(outline, total, payload, focus_style, speed=10, height=360):
    for c in payload["cars"]:
        c.update(focus_style.get(c["code"], {"size": 4.5, "focus": False, "mine": False}))
    data = dict(payload, outline=outline, total=total, speed=speed, speeds=RACE_SPEEDS)
    data["start"] = data.get("start", data["t0"])
    html = RACE_TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__H__", str(int(height)))
    components.html(html, height=height + 74)
    return html
