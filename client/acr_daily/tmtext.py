"""Trackmania-style formatting of team tags and names, as the server reads it (server src/tmtext.js, the same rules):
$RGB a colour (3 hex digits), $o bold, $i italic, $w wide, $n narrow, $t capitals, $s shadow, $g back to the normal
colour, $z everything back, $$ a dollar sign; links ($l[...], $h[...]) and any other code are dropped. A colour too dark
for the dark window is lightened."""
import re

_HEX3 = re.compile(r'[0-9a-fA-F]{3}$')


def _lift(h):
    """'#RRGGBB' of a 3-digit colour, lightened when too dark to read on black."""
    v = [int(c, 16) * 17 for c in h]
    lum = (0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]) / 255
    if lum < 0.3:
        k = (0.3 - lum) / (1 - lum)
        v = [int(c + (255 - c) * k + 0.5) for c in v]   # (rounds .5 up, like the server's Math.round)
    return '#' + ''.join('%02X' % c for c in v)


def spans(raw):
    """The styled pieces: [{'t', 'c', 'b', 'i', 'w', 'n', 'u', 's'}] (c: '#RRGGBB' or None; the rest 0 / 1)."""
    out, buf, s = [], '', str(raw or '')
    st = dict(c=None, b=0, i=0, w=0, n=0, u=0, s=0)

    def push():
        nonlocal buf
        if buf:
            out.append(dict(st, t=buf))
        buf = ''
    k = 0
    while k < len(s):
        ch = s[k]
        if ch != '$':
            buf += ch
            k += 1
            continue
        if k + 1 >= len(s):
            break
        x = s[k + 1]
        if x == '$':
            buf += '$'
            k += 2
            continue
        push()
        hexs = s[k + 1:k + 4]
        if len(hexs) == 3 and _HEX3.match(hexs):
            st['c'] = _lift(hexs)
            k += 4
            continue
        k += 1
        c = x.lower()
        if c == 'o':
            st['b'] = 1
        elif c == 'i':
            st['i'] = 1
        elif c == 'w':
            st['w'], st['n'] = 1, 0
        elif c == 'n':
            st['n'], st['w'] = 1, 0
        elif c == 't':
            st['u'] = 1
        elif c == 's':
            st['s'] = 1
        elif c == 'g':
            st['c'] = None
        elif c == 'z':
            st = dict(c=None, b=0, i=0, w=0, n=0, u=0, s=0)
        elif c in ('l', 'h') and k + 1 < len(s) and s[k + 1] == '[':
            e = s.find(']', k + 1)
            k = len(s) if e < 0 else e
        k += 1
    push()
    return out


def plain(raw):
    """What a formatted text reads as (capitals applied)."""
    return ''.join(x['t'].upper() if x['u'] else x['t'] for x in spans(raw))
