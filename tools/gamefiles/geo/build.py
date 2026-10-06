"""map_fits.json + routes_full.json -> geo_fits.json (per track) and index.html (Leaflet test page)."""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'pylib'))
import numpy as np
from scipy.spatial import cKDTree
import fit

M_LAT = 111132.954


def game_to_latlon(x, z, g):
    """THE conversion (port this to JS as is)."""
    sx = -1 if g['mirror'] == 'x' else 1
    sz = -1 if g['mirror'] == 'z' else 1
    r = math.radians(g['rotDeg'])
    xm, zm = x * sx, z * sz
    e = xm * math.cos(r) - zm * math.sin(r)
    n = xm * math.sin(r) + zm * math.cos(r)
    return g['lat'] + n / M_LAT, g['lon'] + e / (111319.49 * math.cos(math.radians(g['lat'])))


rows = json.load(open(os.path.join(HERE, 'routes_full.json'), encoding='utf-8-sig'))[0]['results']
fits = json.load(open(os.path.join(HERE, 'map_fits.json')))
out, pages = {}, []
for r in sorted(rows, key=lambda r: r['track']):
    prefix = next((p for p in fits if (r['stage_id'] or '').startswith(p)), None)
    if not prefix:
        continue
    geo = fits[prefix]['geo']
    lat0 = geo['latRef'] + geo['n0'] / M_LAT                      # the game origin (0, 0) on Earth
    lon0 = geo['lonRef'] + geo['e0'] / fit.m_lon(geo['latRef'])
    g = {'lat': round(lat0, 7), 'lon': round(lon0, 7), 'rotDeg': geo['rotDeg'], 'mirror': geo['mirror']}
    pts = json.loads(r['points'])
    ll = [game_to_latlon(x, z, g) for x, z in pts]
    # quality with exactly this formula, against the OSM roads used for the fit
    lat_c, lon_c, km, _ = fit.MAPS[prefix]
    roads = fit.road_points(fit.osm_roads(lat_c, lon_c, km), lat_c, lon_c)
    en = np.array([((lo - lon_c) * fit.m_lon(lat_c), (la - lat_c) * M_LAT) for la, lo in ll])
    d, _ = cKDTree(roads).query(en)
    med, p90 = float(np.median(d)), float(np.percentile(d, 90))
    out[r['track']] = dict(g, stageId=r['stage_id'], medianM=round(med, 1), p90M=round(p90, 1), ok=bool(p90 <= 40))
    pages.append({'track': r['track'], 'ok': p90 <= 40, 'med': round(med, 1), 'p90': round(p90, 1),
                  'route': [[round(a, 6), round(b, 6)] for a, b in ll[::2]]})
json.dump(out, open(os.path.join(HERE, 'geo_fits.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
for k, v in out.items():
    print('%-40s %-34s med %5.1f  p90 %6.1f  %s' % (k, v['stageId'], v['medianM'], v['p90M'], 'ok' if v['ok'] else 'POOR'))

first = next((i for i, p in enumerate(pages) if p['track'] == (sys.argv[1] if len(sys.argv) > 1 else 'Wales Hafren Forest')), 0)
html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stage Satellite Test</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
:root{--bg:#0A0A0C;--fg:#F4F4F5;--muted:#8A8A93;--acc:#E30613}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
#bar{display:flex;gap:10px;align-items:center;padding:8px 12px;flex-wrap:wrap}
#bar select{background:#16161a;color:var(--fg);border:1px solid #333;padding:4px 6px}
#q{color:var(--muted)} #map{position:absolute;top:44px;bottom:0;left:0;right:0}
.dot{width:14px;height:14px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 4px #000}
</style></head><body>
<div id="bar"><b>Stage on satellite (test)</b><select id="sel"></select><span id="q"></span></div>
<div id="map"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const STAGES = __DATA__;
const sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {maxZoom: 19, attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community'});
const topo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
  {maxZoom: 17, attribution: '&copy; OpenStreetMap contributors, SRTM | style &copy; OpenTopoMap (CC-BY-SA)'});
const osm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'});
const map = L.map('map', {layers: [sat]});
L.control.layers({'Satellite': sat, 'Topo': topo, 'OpenStreetMap': osm}).addTo(map);
const layer = L.layerGroup().addTo(map);
const COLS = ['#FFD60A', '#30D158', '#0A84FF'], NAMES = ['osiek', 'IndyCheck', 'MaybeIWill'];
function at(route, f) { return route[Math.min(route.length - 1, Math.round(f * (route.length - 1)))]; }
function show(i) {
  const s = STAGES[i]; layer.clearLayers();
  L.polyline(s.route, {color: '#E30613', weight: 4, opacity: .9}).addTo(layer);
  L.circleMarker(s.route[0], {radius: 7, color: '#fff', fillColor: '#30D158', fillOpacity: 1}).bindTooltip('Start').addTo(layer);
  L.circleMarker(s.route[s.route.length - 1], {radius: 7, color: '#fff', fillColor: '#E30613', fillOpacity: 1}).bindTooltip('Finish').addTo(layer);
  [.2, .5, .8].forEach((f, k) => L.marker(at(s.route, f), {icon: L.divIcon({className: '', html:
    '<div class="dot" style="background:' + COLS[k] + '"></div>', iconSize: [18, 18]})}).bindTooltip(NAMES[k], {permanent: true, direction: 'right'}).addTo(layer));
  map.fitBounds(L.polyline(s.route).getBounds(), {padding: [30, 30]});
  document.getElementById('q').textContent = 'fit to OSM roads: median ' + s.med + ' m, 90% within ' + s.p90 + ' m' + (s.ok ? '' : ' (poor fit)');
}
const sel = document.getElementById('sel');
STAGES.forEach((s, i) => sel.add(new Option(s.track + (s.ok ? '' : ' (poor fit)'), i)));
sel.onchange = () => show(+sel.value);
sel.value = __FIRST__; show(__FIRST__);
</script></body></html>"""
html = html.replace('__DATA__', json.dumps(pages)).replace('__FIRST__', str(first))
open(os.path.join(HERE, 'index.html'), 'w', encoding='utf-8').write(html)
print('index.html', len(html), 'bytes;', len(pages), 'stages')
