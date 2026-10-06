// Where each stage is on Earth (EXPERIMENTAL, for /lab/map): made by tools/gamefiles/geo (fit.py, build.py) by laying
// the routes on OpenStreetMap roads. lat/lon = where the game's (0, 0) is; every map is mirrored in x and turned by
// rotDeg (see labmap.js toLL); scale when not 1:1 (Saverne). ok = false: it does not fit (median / 90 % distance from
// the real roads, metres). Munster, Saverne, Loutraki, Elatia: placed from the game menu's start coordinates, then fitted.
export const GEO_FITS = {
 "Alsace Descente": {
  "lat": 48.0320364,
  "lon": 7.120421,
  "rotDeg": 267.39,
  "mirror": "x",
  "medianM": 6.1,
  "p90M": 17.7,
  "ok": true
 },
 "Alsace Forêt": {
  "lat": 48.6558124,
  "lon": 7.295497,
  "rotDeg": 266.69,
  "mirror": "x",
  "medianM": 11.9,
  "p90M": 34.8,
  "ok": true,
  "scale": 1.02
 },
 "Alsace Forêt de Munster": {
  "lat": 48.0320364,
  "lon": 7.120421,
  "rotDeg": 267.39,
  "mirror": "x",
  "medianM": 7.2,
  "p90M": 18.9,
  "ok": true
 },
 "Alsace La Mossig": {
  "lat": 48.6558124,
  "lon": 7.295497,
  "rotDeg": 266.69,
  "mirror": "x",
  "medianM": 5.1,
  "p90M": 20.5,
  "ok": true,
  "scale": 1.02
 },
 "Alsace Luttenbach": {
  "lat": 48.0320364,
  "lon": 7.120421,
  "rotDeg": 267.39,
  "mirror": "x",
  "medianM": 6.8,
  "p90M": 18.8,
  "ok": true
 },
 "Alsace Montée": {
  "lat": 48.0320364,
  "lon": 7.120421,
  "rotDeg": 267.39,
  "mirror": "x",
  "medianM": 5.7,
  "p90M": 17.9,
  "ok": true
 },
 "Alsace Obersteigen": {
  "lat": 48.6558124,
  "lon": 7.295497,
  "rotDeg": 266.69,
  "mirror": "x",
  "medianM": 4.8,
  "p90M": 20.5,
  "ok": true,
  "scale": 1.02
 },
 "Alsace Petit Ballon": {
  "lat": 48.0320364,
  "lon": 7.120421,
  "rotDeg": 267.39,
  "mirror": "x",
  "medianM": 4.3,
  "p90M": 8.6,
  "ok": true
 },
 "Alsace Sommet": {
  "lat": 48.0320364,
  "lon": 7.120421,
  "rotDeg": 267.39,
  "mirror": "x",
  "medianM": 4.4,
  "p90M": 8.6,
  "ok": true
 },
 "Alsace Steigenbach": {
  "lat": 48.6558124,
  "lon": 7.295497,
  "rotDeg": 266.69,
  "mirror": "x",
  "medianM": 11.6,
  "p90M": 35.5,
  "ok": true,
  "scale": 1.02
 },
 "Greece Aghii Theodori": {
  "lat": 37.9974855,
  "lon": 23.0617882,
  "rotDeg": 268.82,
  "mirror": "x",
  "medianM": 3.0,
  "p90M": 6.4,
  "ok": true
 },
 "Greece Aghii Theodori - Loutraki": {
  "lat": 37.9974855,
  "lon": 23.0617882,
  "rotDeg": 268.82,
  "mirror": "x",
  "medianM": 2.4,
  "p90M": 5.4,
  "ok": true
 },
 "Greece Aghii Theodori Reverse": {
  "lat": 37.9974855,
  "lon": 23.0617882,
  "rotDeg": 268.82,
  "mirror": "x",
  "medianM": 3.0,
  "p90M": 6.3,
  "ok": true
 },
 "Greece Elatia": {
  "lat": 38.6424201,
  "lon": 22.8264562,
  "rotDeg": 268.95,
  "mirror": "x",
  "medianM": 2.0,
  "p90M": 4.4,
  "ok": true
 },
 "Greece Elatia - Zeli": {
  "lat": 38.6424201,
  "lon": 22.8264562,
  "rotDeg": 268.95,
  "mirror": "x",
  "medianM": 2.0,
  "p90M": 3.7,
  "ok": true
 },
 "Greece Elatia Reverse": {
  "lat": 38.6424201,
  "lon": 22.8264562,
  "rotDeg": 268.95,
  "mirror": "x",
  "medianM": 2.0,
  "p90M": 4.5,
  "ok": true
 },
 "Greece Loutraki - Aghii Theodori": {
  "lat": 37.9974855,
  "lon": 23.0617882,
  "rotDeg": 268.82,
  "mirror": "x",
  "medianM": 2.5,
  "p90M": 5.3,
  "ok": true
 },
 "Greece New Loutraki": {
  "lat": 37.9974855,
  "lon": 23.0617882,
  "rotDeg": 268.82,
  "mirror": "x",
  "medianM": 2.1,
  "p90M": 4.0,
  "ok": true
 },
 "Greece New Loutraki Reverse": {
  "lat": 37.9974855,
  "lon": 23.0617882,
  "rotDeg": 268.82,
  "mirror": "x",
  "medianM": 2.1,
  "p90M": 3.9,
  "ok": true
 },
 "Greece Zeli": {
  "lat": 38.6424201,
  "lon": 22.8264562,
  "rotDeg": 268.95,
  "mirror": "x",
  "medianM": 1.9,
  "p90M": 3.4,
  "ok": true
 },
 "Greece Zeli - Elatia": {
  "lat": 38.6424201,
  "lon": 22.8264562,
  "rotDeg": 268.95,
  "mirror": "x",
  "medianM": 1.9,
  "p90M": 3.9,
  "ok": true
 },
 "Greece Zeli Reverse": {
  "lat": 38.6424201,
  "lon": 22.8264562,
  "rotDeg": 268.95,
  "mirror": "x",
  "medianM": 2.0,
  "p90M": 3.5,
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
