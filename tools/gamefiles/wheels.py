"""Each car's wheels at rest -> mod/ACRDailyGhosts/Scripts/wheels.lua (where the ACR Daily mod puts a ghost car's wheels).

    python wheels.py wheels_measured.json

wheels_measured.json was measured in the game (2026-11-10, St. Geniez - Mezien, each car as your own car standing on
the start line; the test-only probe mod read the car's EXT_FL/FR/RL/RR_Tire bones in the car's own space, cm: x + =
left, y + = forward, z + = up from the car's root). Left and right are averaged per axle (the road's camber tilts a
standing car a little).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '..', 'mod', 'ACRDailyGhosts', 'Scripts', 'wheels.lua')


def axle(left, right):
    x = (abs(left[0]) + abs(right[0])) / 2.0
    y = (left[1] + right[1]) / 2.0
    z = (left[2] + right[2]) / 2.0
    return (x, y, z), (-x, y, z)


def build(measured):
    lines = ['-- Each car\'s wheels at rest, in the car\'s own space (cm: x + = left, y + = forward, z + = up), in the game\'s',
             '-- wheel order FL, FR, RL, RR. Made by tools/gamefiles/wheels.py from measurements in the game.',
             'return {']
    for car in sorted(measured):
        m = measured[car]
        w = m['wheels']
        fl, fr = axle(w['FL'], w['FR'])
        rl, rr = axle(w['RL'], w['RR'])
        cls = m['cls'].rsplit('.', 1)[1]                       # '/Game/.../BC_X.BC_X_C' -> 'BC_X_C'
        cells = ', '.join('{%.1f, %.1f, %.1f}' % p for p in (fl, fr, rl, rr))
        lines.append('    %s = {%s},' % (cls, cells))
    lines.append('}')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as fh:
        data = json.load(fh)
    text = build(data)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    print(text)
    print('->', os.path.normpath(OUT), len(data), 'cars')
