import json

import streamlit as st
import streamlit.components.v1 as components

from f1analytics.pitwall import replay

MAPLIBRE = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl"
DECK = "https://unpkg.com/deck.gl@9.0.38/dist.min.js"
STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"

HTML = """<!doctype html><html><head><meta charset="utf-8">
<link href="__MAPLIBRE__.css" rel="stylesheet">
<script src="__MAPLIBRE__.js"></script><script src="__DECK__"></script>
<link href="https://fonts.googleapis.com/css2?family=Michroma&display=swap" rel="stylesheet">
<style>
html,body{margin:0;background:#101016;color:#F3F3F5;font-family:'Michroma',sans-serif}
#wrap{display:flex;flex-wrap:wrap;gap:10px}
#mapbox{position:relative;flex:999 1 520px;min-width:0;height:__H__px;border-radius:14px;overflow:hidden;border:1px solid #2E2E3A}
#map{position:absolute;inset:0}
#hud{position:absolute;left:10px;top:10px;display:flex;gap:6px;z-index:2}
.chip{background:rgba(20,20,28,.85);border:1px solid #2E2E3A;border-radius:999px;padding:6px 11px;font-size:11px;letter-spacing:.06em}
.chip.sc{background:#FFD12E;color:#14141C;border-color:#FFD12E}.chip.red{background:#E10600;border-color:#E10600}
#board{flex:1 1 200px;background:#1A1A24;border:1px solid #2E2E3A;border-radius:14px;padding:8px 10px;max-height:__H__px;overflow:auto}
.row{display:grid;grid-template-columns:22px 4px 1fr;gap:8px;align-items:center;height:26px;font-size:11px;border-top:1px solid #2E2E3A}
.row:first-child{border-top:0}.row i{display:block;width:4px;height:14px;border-radius:2px}.row.me{background:rgba(225,6,0,.14);margin:0 -10px;padding:0 10px}
.k{font-size:9px;letter-spacing:.1em;color:#A3A3B2;margin:2px 0 6px}
#ctl{display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap}
button,select{font-family:inherit;background:#232330;color:#F3F3F5;border:1px solid #2E2E3A;border-radius:10px;height:40px;padding:0 12px;font-size:11px;cursor:pointer}
#play{min-width:84px}input[type=range]{flex:1 1 160px;accent-color:#E10600;height:40px}
#clock{font-size:11px;color:#A3A3B2;min-width:70px;text-align:right}
.maplibregl-ctrl-attrib{font-size:9px}
</style></head><body>
<div id="wrap"><div id="mapbox"><div id="map"></div><div id="hud"><span class="chip" id="lap">LAP 0</span><span class="chip" id="flag" style="display:none"></span></div></div>
<div id="board"><div class="k">RUNNING ORDER</div><div id="rows"></div></div></div>
<div id="ctl"><button id="play" aria-label="Play or pause">▶ Play</button>
<select id="speed" aria-label="Replay speed"><option value="1">1×</option><option value="5">5×</option><option value="15" selected>15×</option><option value="40">40×</option></select>
<button id="names" aria-label="Show every driver's name">All names</button>
<input id="seek" type="range" min="0" max="1" step="1" value="0" aria-label="Race time"><span id="clock">0:00</span></div>
<script>
const D = __DATA__; const FOCUS = __FOCUS__;
const steps = D.cars[0].lon.length, dt = D.dt, T = (steps - 1) * dt;
const rgb = h => { h = h.replace('#',''); if (h.length < 6) h = '9A9AA8'; return [0,2,4].map(i => parseInt(h.substr(i,2),16)); };
const cars = D.cars.map(c => ({...c, rgb: rgb(c.colour), me: FOCUS.includes(c.code)}));
const byNum = Object.fromEntries(cars.map(c => [c.n, c]));
let t = D.lap_t.length ? Math.max(0, D.lap_t[0] - 5) : 0, playing = false, last = null;
const seek = document.getElementById('seek'); seek.max = Math.floor(T); seek.value = Math.floor(t);
function at(c, t){ const i = t / dt, a = Math.floor(i), f = i - a; if (a < 0 || a + 1 >= steps) return null;
  const x0 = c.lon[a], y0 = c.lat[a], x1 = c.lon[a+1], y1 = c.lat[a+1];
  if (x0 == null || x1 == null) return x0 == null ? null : [x0, y0]; return [x0 + (x1-x0)*f, y0 + (y1-y0)*f]; }
const lons = D.track.map(p=>p[0]), lats = D.track.map(p=>p[1]);
const map = new maplibregl.Map({container:'map', style:'__STYLE__', center:[(Math.min(...lons)+Math.max(...lons))/2,(Math.min(...lats)+Math.max(...lats))/2],
  zoom: 13, pitch: 55, bearing: -15, attributionControl: {compact: true}});
map.addControl(new maplibregl.NavigationControl({visualizePitch:true}), 'top-right');
let styled = false; map.on('load', () => { styled = true; });
setTimeout(() => { if (!styled) map.setStyle({version: 8, sources: {}, layers: [{id: 'bg', type: 'background', paint: {'background-color': '#101016'}}]}); }, 7000);
map.on('load', () => map.fitBounds([[Math.min(...lons),Math.min(...lats)],[Math.max(...lons),Math.max(...lats)]], {padding:40, pitch:55, bearing:-15, duration:0}));
const overlay = new deck.MapboxOverlay({interleaved:false, layers:[]}); map.addControl(overlay);
const track = [{path: D.track.concat([D.track[0]])}];
function layers(){
  const pts = cars.map(c => ({c, p: at(c, t)})).filter(o => o.p);
  return [
    new deck.PathLayer({id:'edge', data:track, getPath:d=>d.path, getColor:[243,243,245,60], widthUnits:'meters', getWidth:26, widthMinPixels:5, jointRounded:true}),
    new deck.PathLayer({id:'track', data:track, getPath:d=>d.path, getColor:[46,46,58], widthUnits:'meters', getWidth:18, widthMinPixels:3, jointRounded:true}),
    new deck.ScatterplotLayer({id:'cars', data:pts, getPosition:o=>o.p, getFillColor:o=>o.c.rgb, getLineColor:o=>o.c.me?[255,255,255]:[16,16,22],
      stroked:true, lineWidthMinPixels:1, getLineWidth:o=>o.c.me?3:1, lineWidthUnits:'pixels', radiusUnits:'meters', getRadius:o=>o.c.me?18:13,
      radiusMinPixels:5, updateTriggers:{getPosition:t}}),
    new deck.TextLayer({id:'codes', data:pts.filter(o=>o.c.me || o.c.n === leader() || showAll), getPosition:o=>o.p, getText:o=>o.c.code, getSize:o=>o.c.me?13:10,
      getColor:o=>o.c.me?[255,255,255]:[200,200,210], getPixelOffset:[0,-14], fontFamily:'Michroma, sans-serif', billboard:true,
      outlineWidth:3, outlineColor:[16,16,22], fontSettings:{sdf:true}, updateTriggers:{getPosition:t}})
  ];
}
let showAll = false;
function leader(){ const o = D.order[Math.min(D.order.length - 1, Math.floor(t / D.order_dt))] || []; return o[0]; }
function fmt(s){ s = Math.max(0, Math.round(s)); return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
function hud(){
  const lap = D.lap_t.filter(x => x <= t).length; document.getElementById('lap').textContent = 'LAP ' + Math.max(lap,0) + ' / ' + D.lap_t.length;
  let st = null; for (const f of D.flags) { if (f.t <= t) st = f.s; else break; }
  const el = document.getElementById('flag');
  if (st === 'SC' || st === 'VSC' || st === 'RED') { el.style.display = ''; el.textContent = st === 'RED' ? 'RED FLAG' : (st === 'SC' ? 'SAFETY CAR' : 'VIRTUAL SC');
    el.className = 'chip ' + (st === 'RED' ? 'red' : 'sc'); } else if (st === 'FINISH') { el.style.display=''; el.textContent='CHEQUERED'; el.className='chip'; } else el.style.display = 'none';
  const o = D.order[Math.min(D.order.length - 1, Math.floor(t / D.order_dt))] || [];
  document.getElementById('rows').innerHTML = o.slice(0, 22).map((n, i) => { const c = byNum[n]; if (!c) return '';
    return `<div class="row${c.me?' me':''}"><span style="color:#A3A3B2">${i+1}</span><i style="background:${c.colour}"></i><span>${c.code}</span></div>`; }).join('');
  document.getElementById('clock').textContent = fmt(t - (D.lap_t[0]||0));
  if (!dragging) seek.value = Math.floor(t);
}
let dragging = false, lastHud = 0;
seek.addEventListener('input', () => { dragging = true; t = +seek.value; draw(true); });
seek.addEventListener('change', () => { dragging = false; });
document.getElementById('names').onclick = () => { showAll = !showAll; document.getElementById('names').textContent = showAll ? 'Key names' : 'All names'; draw(true); };
document.getElementById('play').onclick = () => { playing = !playing; document.getElementById('play').textContent = playing ? '❚❚ Pause' : '▶ Play'; last = null; };
function draw(force){ overlay.setProps({layers: layers()}); const now = performance.now(); if (force || now - lastHud > 250) { hud(); lastHud = now; } }
function loop(ts){ if (playing) { if (last != null) t = Math.min(T, t + (ts - last) / 1000 * +document.getElementById('speed').value); last = ts;
  if (t >= T) { playing = false; document.getElementById('play').textContent = '▶ Play'; } } draw(false); requestAnimationFrame(loop); }
map.on('load', () => { draw(true); requestAnimationFrame(loop); });
</script></body></html>"""


def available(session_key):
    return replay.path_for(session_key).exists()


def render(session_key, focus=(), height=460):
    data = replay.load(session_key)
    if data is None:
        st.info("The 3D replay for this race hasn't been built yet. It's made on the Mac with `python scripts/build_replay.py "
                f"{int(session_key)}` and then pushed.")
        return False
    html = (HTML.replace("__MAPLIBRE__", MAPLIBRE).replace("__DECK__", DECK).replace("__STYLE__", STYLE).replace("__H__", str(height))
            .replace("__FOCUS__", json.dumps([str(f) for f in focus])).replace("__DATA__", json.dumps(data, separators=(",", ":"))))
    components.html(html, height=height + 70, scrolling=False)
    st.caption(f"Every car's real position from OpenF1 GPS, every {data['dt']:.0f} seconds, smoothed between points, placed on a real street map "
               f"(track lined up with its real outline to about {data['fit_rms_m']:.0f} m). Drag to pan, right-drag or two-finger drag to tilt and turn, pinch to zoom. "
               "Map © OpenStreetMap contributors, © CARTO. Circuit outlines: bacinger/f1-circuits (MIT).")
    return True
