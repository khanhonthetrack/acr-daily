"""Every car's driving cameras, from the game's files -> client/acr_daily/cameras.json (for the ghost cars).

    python cameras.py            (run from this folder; extracts the car blueprints to ext\\cars first)

Each car blueprint (Data/Vehicles/<Car>/BC_<Car>) overrides some of the camera components of the base car
(Data/Vehicles/Common/BC_CarAvatar): Bonnet, Bumper, Gauge (dash), FirstPerson (helmet), ThirdNear, ThirdFar.
The properties are unversioned (cooked): the car overrides use a handful of known slots (4: a float, 5: the field
of view, 36: location, 37: rotation, 38: scale); the base templates carry more and are read by their shape
(the field of view is the float just before the 512.0 ortho width; the location the 3 doubles just before a
rotation with yaw 90, or before a 0.25 scale).

Per camera, in cameras.json: x (cm, + = left), y (cm, + = forward), z (cm, up) from the car's root (on the
ground under the middle of the car), pitch / yaw / roll (degrees; yaw 90 = straight ahead), fov (degrees across
a 16:9 picture; the game keeps the view's height on other screen shapes). Checked in the game on 2026-11-05
(Skoda Fabia RS Rally2, 3440 x 1440): the game shows "Horizontal Field Of View 92" for a 75 camera, and every
view's road lined up on the start line.
"""
import glob
import json
import math
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry   # noqa: E402
import iostore    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, 'ext', 'cars')
OUT = os.path.join(HERE, '..', '..', 'client', 'acr_daily', 'cameras.json')
CARS_JS = os.path.join(HERE, '..', '..', 'server', 'src', 'cars.js')
CAMS = {'Bonnet': 'bonnet', 'Bumper': 'bumper', 'Gauge': 'gauge', 'FirstPerson': 'helmet', 'ThirdNear': 'near',
        'ThirdFar': 'far'}


def extract():
    os.makedirs(EXT, exist_ok=True)
    pat = re.compile(r'Data/Vehicles/([^/]+)/BC_[^/_]+\.uasset$|Data/Vehicles/Common/BC_CarAvatar\.uasset$')
    for t in iostore.tocs():
        for f, i in t.files.items():
            if pat.search(f):
                t.extract_index(i, os.path.join(EXT, os.path.basename(f)))


def header(d):
    """Unversioned property header -> ([(slot, is zero)], where the values start), or None."""
    o, idx, frags = 0, 0, []
    while True:
        if o + 2 > len(d):
            return None
        v = struct.unpack_from('<H', d, o)[0]
        o += 2
        skip, zeros, last, num = v & 0x7f, (v >> 7) & 1, (v >> 8) & 1, v >> 9
        idx += skip
        frags.append((idx, num, zeros))
        idx += num
        if last:
            break
    nz = sum(num for _i, num, z in frags if z)
    mask = 0
    if nz:
        nbytes = 1 if nz <= 8 else 2 if nz <= 16 else 4 * ((nz + 31) // 32)
        mask = int.from_bytes(d[o:o + nbytes], 'little')
        o += nbytes
    props, bit = [], 0
    for i, num, z in frags:
        for k in range(num):
            zero = False
            if z:
                zero = bool(mask >> bit & 1)
                bit += 1
            props.append((i + k, zero))
    return props, o


def decode_override(d):
    h = header(d)
    if not h:
        return None
    props, o = h
    out = {}
    for i, zero in props:
        if zero:
            continue
        if i in (4, 5):
            out[i] = struct.unpack_from('<f', d, o)[0]
            o += 4
        elif i in (36, 37, 38):
            out[i] = struct.unpack_from('<3d', d, o)
            o += 24
        else:
            return None
    return out


def decode_base(d):
    out = {}
    for o in range(0, len(d) - 7):
        f, nxt = struct.unpack_from('<2f', d, o)
        if nxt == 512.0 and 20.0 <= f <= 150.0:
            out['fov'] = f
            break
    tr = {}
    for o in range(0, len(d) - 23):
        v = struct.unpack_from('<3d', d, o)
        if all(math.isfinite(x) and abs(x) < 5000 for x in v):
            tr[o] = v
    for o in sorted(tr):
        loc, nxt = tr[o], tr.get(o + 24)
        if max(abs(x) for x in loc) < 10 or not nxt:
            continue
        if abs(nxt[1] - 90.0) < 1e-3 and abs(nxt[0]) < 45:
            out['loc'], out['rot'] = loc, nxt
            break
        if all(abs(x - 0.25) < 1e-9 for x in nxt):
            out['loc'], out['rot'] = loc, (0.0, 90.0, 0.0)
            break
    return out


def exports(path):
    b = open(path, 'rb').read()
    return {name.replace('_GEN_VARIABLE', ''): data for name, data, _a in geometry.exports(b)}


def car_names():
    """{blueprint name: [names the game / the server use for it]} from server/src/cars.js."""
    out = []
    for line in open(CARS_JS, encoding='utf-8'):
        m = re.search(r"id: '([^']+)', telemetry: '([^']+)', name: '([^']+)'(?:.*aliases: \[([^\]]*)\])?", line)
        if m:
            aliases = re.findall(r"'([^']+)'", m.group(4) or '')
            out.append([m.group(1), m.group(2), m.group(3)] + aliases)
    return out


def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def build():
    base_ex = exports(os.path.join(EXT, 'BC_CarAvatar.uasset'))
    base = {}
    for comp, cam in CAMS.items():
        v = decode_base(base_ex[comp])
        base[cam] = dict(x=v['loc'][0], y=v['loc'][1], z=v['loc'][2], pitch=v['rot'][0], yaw=v['rot'][1],
                         roll=v['rot'][2], fov=v.get('fov', 75.0))
    names = car_names()
    cars = {}
    for path in sorted(glob.glob(os.path.join(EXT, 'BC_*.uasset'))):
        car = os.path.basename(path)[3:-7]
        if car.startswith('Car'):
            continue                               # (the base and its helpers)
        ex = exports(path)
        cams = {}
        for comp, cam in CAMS.items():
            c = dict(base[cam])
            v = decode_override(ex[comp]) if comp in ex else {}
            if v is None:
                raise SystemExit('%s %s: a camera override this does not understand' % (car, comp))
            if 5 in v:
                c['fov'] = v[5]
            if 36 in v:
                c['x'], c['y'], c['z'] = v[36]
            if 37 in v:
                c['pitch'], c['yaw'], c['roll'] = v[37]
            cams[cam] = {k: round(x, 2) for k, x in c.items()}
        known = [n for n in names if norm(car) in map(norm, n)]
        cars[car] = {'names': known[0] if known else [car], 'cameras': cams}
        print('%-30s %s' % (car, ' '.join('%s %.0f/%.0f/%.0f %.1f° %.0f' % (k, c['x'], c['y'], c['z'], c['pitch'], c['fov'])
                                           for k, c in cams.items())))
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'cars': cars}, f, indent=1, sort_keys=True)
        f.write('\n')
    print('->', os.path.normpath(OUT), len(cars), 'cars')


if __name__ == '__main__':
    if '--no-extract' not in sys.argv:
        extract()
    build()
