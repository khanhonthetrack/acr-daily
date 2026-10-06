// Where each stage is on Earth (EXPERIMENTAL, for /lab/map): made by tools/gamefiles/geo (fit.py, build.py) by laying
// the routes on OpenStreetMap roads. lat/lon = where the game's (0, 0) is; every map is mirrored in x and turned by
// rotDeg (see labmap.js toLL). ok = false: it does not fit (median / 90 % distance from the real roads, metres).
export const GEO_FITS = {
 "Alsace Descente": {
  "lat": 47.9647979,
  "lon": 7.236915,
  "rotDeg": 268.5,
  "mirror": "x",
  "medianM": 18.2,
  "p90M": 45.4,
  "ok": false
 },
 "Alsace Forêt": {
  "lat": 48.7581049,
  "lon": 7.342638,
  "rotDeg": 274.5,
  "mirror": "x",
  "medianM": 15.4,
  "p90M": 51.9,
  "ok": false
 },
 "Alsace Forêt de Munster": {
  "lat": 47.9647979,
  "lon": 7.236915,
  "rotDeg": 268.5,
  "mirror": "x",
  "medianM": 18.5,
  "p90M": 47.0,
  "ok": false
 },
 "Alsace La Mossig": {
  "lat": 48.7581049,
  "lon": 7.342638,
  "rotDeg": 274.5,
  "mirror": "x",
  "medianM": 10.7,
  "p90M": 35.3,
  "ok": false
 },
 "Alsace Luttenbach": {
  "lat": 47.9647979,
  "lon": 7.236915,
  "rotDeg": 268.5,
  "mirror": "x",
  "medianM": 18.5,
  "p90M": 46.7,
  "ok": false
 },
 "Alsace Montée": {
  "lat": 47.9647979,
  "lon": 7.236915,
  "rotDeg": 268.5,
  "mirror": "x",
  "medianM": 18.0,
  "p90M": 45.4,
  "ok": false
 },
 "Alsace Obersteigen": {
  "lat": 48.7581049,
  "lon": 7.342638,
  "rotDeg": 274.5,
  "mirror": "x",
  "medianM": 10.8,
  "p90M": 33.6,
  "ok": false
 },
 "Alsace Petit Ballon": {
  "lat": 47.9647979,
  "lon": 7.236915,
  "rotDeg": 268.5,
  "mirror": "x",
  "medianM": 18.1,
  "p90M": 43.3,
  "ok": false
 },
 "Alsace Sommet": {
  "lat": 47.9647979,
  "lon": 7.236915,
  "rotDeg": 268.5,
  "mirror": "x",
  "medianM": 18.1,
  "p90M": 43.5,
  "ok": false
 },
 "Alsace Steigenbach": {
  "lat": 48.7581049,
  "lon": 7.342638,
  "rotDeg": 274.5,
  "mirror": "x",
  "medianM": 14.8,
  "p90M": 52.1,
  "ok": false
 },
 "Greece Aghii Theodori": {
  "lat": 37.9544488,
  "lon": 22.9648615,
  "rotDeg": 265.5,
  "mirror": "x",
  "medianM": 13.6,
  "p90M": 59.4,
  "ok": false
 },
 "Greece Aghii Theodori - Loutraki": {
  "lat": 37.9544488,
  "lon": 22.9648615,
  "rotDeg": 265.5,
  "mirror": "x",
  "medianM": 14.7,
  "p90M": 50.2,
  "ok": false
 },
 "Greece Aghii Theodori Reverse": {
  "lat": 37.9544488,
  "lon": 22.9648615,
  "rotDeg": 265.5,
  "mirror": "x",
  "medianM": 14.0,
  "p90M": 58.8,
  "ok": false
 },
 "Greece Elatia": {
  "lat": 38.6424449,
  "lon": 22.8264236,
  "rotDeg": 268.8,
  "mirror": "x",
  "medianM": 3.7,
  "p90M": 9.3,
  "ok": true
 },
 "Greece Elatia - Zeli": {
  "lat": 38.6424449,
  "lon": 22.8264236,
  "rotDeg": 268.8,
  "mirror": "x",
  "medianM": 2.8,
  "p90M": 8.3,
  "ok": true
 },
 "Greece Elatia Reverse": {
  "lat": 38.6424449,
  "lon": 22.8264236,
  "rotDeg": 268.8,
  "mirror": "x",
  "medianM": 3.7,
  "p90M": 9.4,
  "ok": true
 },
 "Greece Loutraki - Aghii Theodori": {
  "lat": 37.9544488,
  "lon": 22.9648615,
  "rotDeg": 265.5,
  "mirror": "x",
  "medianM": 14.7,
  "p90M": 50.6,
  "ok": false
 },
 "Greece New Loutraki": {
  "lat": 37.9544488,
  "lon": 22.9648615,
  "rotDeg": 265.5,
  "mirror": "x",
  "medianM": 16.4,
  "p90M": 45.3,
  "ok": false
 },
 "Greece New Loutraki Reverse": {
  "lat": 37.9544488,
  "lon": 22.9648615,
  "rotDeg": 265.5,
  "mirror": "x",
  "medianM": 16.5,
  "p90M": 45.5,
  "ok": false
 },
 "Greece Zeli": {
  "lat": 38.6424449,
  "lon": 22.8264236,
  "rotDeg": 268.8,
  "mirror": "x",
  "medianM": 2.3,
  "p90M": 6.1,
  "ok": true
 },
 "Greece Zeli - Elatia": {
  "lat": 38.6424449,
  "lon": 22.8264236,
  "rotDeg": 268.8,
  "mirror": "x",
  "medianM": 2.8,
  "p90M": 8.3,
  "ok": true
 },
 "Greece Zeli Reverse": {
  "lat": 38.6424449,
  "lon": 22.8264236,
  "rotDeg": 268.8,
  "mirror": "x",
  "medianM": 2.3,
  "p90M": 5.9,
  "ok": true
 },
 "Monte Carlo La Bollène": {
  "lat": 43.9661511,
  "lon": 7.3564906,
  "rotDeg": 267.0,
  "mirror": "x",
  "medianM": 2.0,
  "p90M": 4.2,
  "ok": true
 },
 "Monte Carlo Mézien - Sisteron": {
  "lat": 44.2347386,
  "lon": 6.0064018,
  "rotDeg": 267.9,
  "mirror": "x",
  "medianM": 2.5,
  "p90M": 5.0,
  "ok": true
 },
 "Monte Carlo Mézien - St. Geniez": {
  "lat": 44.2347386,
  "lon": 6.0064018,
  "rotDeg": 267.9,
  "mirror": "x",
  "medianM": 2.2,
  "p90M": 5.7,
  "ok": true
 },
 "Monte Carlo Peïra Cava": {
  "lat": 43.9661511,
  "lon": 7.3564906,
  "rotDeg": 267.0,
  "mirror": "x",
  "medianM": 2.0,
  "p90M": 4.2,
  "ok": true
 },
 "Monte Carlo Peïra Cava - Turini": {
  "lat": 43.9661511,
  "lon": 7.3564906,
  "rotDeg": 267.0,
  "mirror": "x",
  "medianM": 1.9,
  "p90M": 3.6,
  "ok": true
 },
 "Monte Carlo Pra d'Alart": {
  "lat": 43.9661511,
  "lon": 7.3564906,
  "rotDeg": 267.0,
  "mirror": "x",
  "medianM": 1.7,
  "p90M": 2.8,
  "ok": true
 },
 "Monte Carlo Sisteron - Mézien": {
  "lat": 44.2347386,
  "lon": 6.0064018,
  "rotDeg": 267.9,
  "mirror": "x",
  "medianM": 2.5,
  "p90M": 4.8,
  "ok": true
 },
 "Monte Carlo Sisteron - St. Geniez": {
  "lat": 44.2347386,
  "lon": 6.0064018,
  "rotDeg": 267.9,
  "mirror": "x",
  "medianM": 2.4,
  "p90M": 5.3,
  "ok": true
 },
 "Monte Carlo Sommet de Turini": {
  "lat": 43.9661511,
  "lon": 7.3564906,
  "rotDeg": 267.0,
  "mirror": "x",
  "medianM": 1.7,
  "p90M": 2.8,
  "ok": true
 },
 "Monte Carlo St. Geniez - Mézien": {
  "lat": 44.2347386,
  "lon": 6.0064018,
  "rotDeg": 267.9,
  "mirror": "x",
  "medianM": 2.2,
  "p90M": 5.7,
  "ok": true
 },
 "Monte Carlo St. Geniez - Sisteron": {
  "lat": 44.2347386,
  "lon": 6.0064018,
  "rotDeg": 267.9,
  "mirror": "x",
  "medianM": 2.3,
  "p90M": 5.3,
  "ok": true
 },
 "Monte Carlo Turini - Peïra Cava": {
  "lat": 43.9661511,
  "lon": 7.3564906,
  "rotDeg": 267.0,
  "mirror": "x",
  "medianM": 1.9,
  "p90M": 3.6,
  "ok": true
 },
 "Monte Carlo Turini Descente": {
  "lat": 43.9661511,
  "lon": 7.3564906,
  "rotDeg": 267.0,
  "mirror": "x",
  "medianM": 2.0,
  "p90M": 4.4,
  "ok": true
 },
 "Monte Carlo Turini Montée": {
  "lat": 43.9661511,
  "lon": 7.3564906,
  "rotDeg": 267.0,
  "mirror": "x",
  "medianM": 2.0,
  "p90M": 4.4,
  "ok": true
 },
 "Wales Afon Bidno": {
  "lat": 52.4645644,
  "lon": -3.7050868,
  "rotDeg": 269.6,
  "mirror": "x",
  "medianM": 9.5,
  "p90M": 28.8,
  "ok": true
 },
 "Wales Afon Biga": {
  "lat": 52.4807874,
  "lon": -3.7002606,
  "rotDeg": 271.9,
  "mirror": "x",
  "medianM": 4.2,
  "p90M": 10.2,
  "ok": true
 },
 "Wales Banc Gwyn": {
  "lat": 52.4807874,
  "lon": -3.7002606,
  "rotDeg": 271.9,
  "mirror": "x",
  "medianM": 4.0,
  "p90M": 10.5,
  "ok": true
 },
 "Wales Cwmbiga": {
  "lat": 52.4807874,
  "lon": -3.7002606,
  "rotDeg": 271.9,
  "mirror": "x",
  "medianM": 4.3,
  "p90M": 10.4,
  "ok": true
 },
 "Wales Fedw Fain": {
  "lat": 52.4807874,
  "lon": -3.7002606,
  "rotDeg": 271.9,
  "mirror": "x",
  "medianM": 4.3,
  "p90M": 10.0,
  "ok": true
 },
 "Wales Hafren Forest": {
  "lat": 52.4807874,
  "lon": -3.7002606,
  "rotDeg": 271.9,
  "mirror": "x",
  "medianM": 4.4,
  "p90M": 10.2,
  "ok": true
 },
 "Wales Ospreys": {
  "lat": 52.4807874,
  "lon": -3.7002606,
  "rotDeg": 271.9,
  "mirror": "x",
  "medianM": 4.1,
  "p90M": 10.5,
  "ok": true
 },
 "Wales Severn": {
  "lat": 52.4645644,
  "lon": -3.7050868,
  "rotDeg": 269.6,
  "mirror": "x",
  "medianM": 10.1,
  "p90M": 29.5,
  "ok": true
 }
};
