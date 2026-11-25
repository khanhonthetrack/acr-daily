"""Every stage's pacenotes from the game's own files -> server/src/pacenotes.js (the COPILOT daily's notes book).

The game keeps a stage variant's notes in a DataTable, Data/Pacenote/Tables/DT_Pacenote<Stage><Variant> (row struct
PacenoteSplineEntry, from the game's .usmap: SplineDistanceM float, LengthM float, TokenList {Tokens: [FName]},
LinkToNext bool, Description str, SavedLocation vector). Cooked as a zen package with unversioned properties: each
row is a header of fragments (skip / has zeroes / last / values), a zero mask, then the values that aren't zero.

    set ACR_GAME_DIR=D:\\SteamLibrary\\steamapps\\common\\Assetto Corsa Rally
    python pacenotes.py ext ..\\..\\server\\src\\pacenotes.js

Each stage: its notes in order, [metres from the first note, the note's length in metres, 'Token Token ...']; the words
the co-driver reads are made from the tokens by the server (src/copilot.js noteText) and the app.
"""
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iostore  # noqa: E402
import zen  # noqa: E402


class Reader:
    def __init__(self, b, o, names):
        self.b, self.o, self.names = b, o, names

    def u(self, f):
        v = struct.unpack_from('<' + f, self.b, self.o)
        self.o += struct.calcsize(f)
        return v[0]

    def name(self):
        i, n = self.u('I'), self.u('I')
        s = self.names[i] if i < len(self.names) else '?%d' % i
        return s + ('_%d' % (n - 1) if n else '')

    def fstr(self):
        n = self.u('i')
        if n < 0:
            s = self.b[self.o:self.o - 2 * n].decode('utf-16-le')
            self.o += -2 * n
        else:
            s = self.b[self.o:self.o + n].decode('latin-1')
            self.o += n
        return s.rstrip('\x00')

    def header(self):
        """An unversioned property header -> [(schema index, is zero)] for the values present."""
        frags = []
        while True:
            h = self.u('H')
            frags.append((h & 0x7f, (h >> 7) & 1, h >> 9))
            if (h >> 8) & 1:
                break
        nz = sum(num for _s, z, num in frags if z)
        mask = 0
        if nz:
            if nz <= 8:
                mask = self.u('B')
            elif nz <= 16:
                mask = self.u('H')
            else:
                for w in range((nz + 31) // 32):
                    mask |= self.u('I') << (32 * w)
        out, idx, zi = [], 0, 0
        for skip, zeros, num in frags:
            idx += skip
            for _ in range(num):
                z = False
                if zeros:
                    z = bool(mask >> zi & 1)
                    zi += 1
                out.append((idx, z))
                idx += 1
        return out


def _row(r):
    e = {'at': 0.0, 'len': 0.0, 'tokens': []}
    for idx, z in r.header():
        if idx == 0:
            e['at'] = 0.0 if z else r.u('f')
        elif idx == 1:
            e['len'] = 0.0 if z else r.u('f')
        elif idx == 2:
            if not z:
                for j, zz in r.header():
                    if j == 0 and not zz:
                        e['tokens'] = [r.name() for _ in range(r.u('i'))]
        elif idx == 3:
            e['link'] = False if z else bool(r.u('B'))
        elif idx == 4:
            e['desc'] = '' if z else r.fstr()
        elif idx == 5:
            if not z:
                r.o += 24                   # (SavedLocation: three doubles)
        else:
            raise ValueError('unknown field %d at %d' % (idx, r.o))
    return e


def read_table(b):
    """A pacenote DataTable's bytes -> its rows [{'at', 'len', 'tokens', ...}] in order. Raises ValueError."""
    p = zen.parse(b)
    ex = [e for e in p['exports'] if e['name'].startswith('DT_')][0]
    r = Reader(b, p['header_size'] + ex['serial'], p['names'])
    for idx, z in r.header():                  # the DataTable's own: RowStruct (a package index)
        if not z:
            if idx != 0:
                raise ValueError('unexpected DataTable field %d' % idx)
            r.u('i')
    if r.u('i'):                               # (an object guid)
        r.o += 16
    rows = []
    for _ in range(r.u('i')):
        r.name()
        rows.append(_row(r))
    if r.o != p['header_size'] + ex['serial'] + ex['size']:
        raise ValueError('the table did not end where its export does')
    return rows


def variant_key(name):
    """'BolleneCut2Forward' / 'HafrenNorthReverseCut2' / 'SaverneShort1Forward' / 'FredriksbergCu1Reverse' ->
    ('bollene', 2, 'forward'): the stage, its cut (0: the full one; Cut and Short alike), its way."""
    m = re.match(r'^([A-Z][a-z]+(?:North|South)?)(.*)$', name)
    if not m:
        return None
    stage, rest = m.group(1).lower(), m.group(2)
    way = 'forward' if 'Forward' in rest else 'reverse' if 'Reverse' in rest else None
    n = re.search(r'(?:Cut|Cu|Short)(\d)', rest)
    if way is None:
        return None
    return stage, int(n.group(1)) if n else 0, way


def stage_ids(stages_js):
    """The game's stage ids from server/src/stages.js (MENU_NAMES' keys) -> {variant_key: id}."""
    text = open(stages_js, encoding='utf-8').read()
    out = {}
    for sid in re.findall(r'^\s+([A-Z][A-Za-z]+S\d[A-Za-z0-9]+):', text, re.M):
        k = variant_key(re.sub(r'^[A-Z][a-z]+(?:Carlo)?S\d', '', sid))
        if k:
            out[k] = sid
    return out


def main(outdir, out_js):
    os.makedirs(outdir, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    ids = stage_ids(os.path.join(here, '..', '..', 'server', 'src', 'stages.js'))
    found, missing = {}, []
    for t, f, i in iostore.find('Data/Pacenote/Tables/DT_Pacenote'):
        if not f.endswith('.uasset') or '/TestPacenoteTables/' in f:
            continue
        name = os.path.basename(f)[len('DT_Pacenote'):-len('.uasset')]
        k = variant_key(name)
        sid = ids.get(k) if k else None
        if not sid:
            missing.append(name)
            continue
        rows = read_table(t.extract_index(i, os.path.join(outdir, os.path.basename(f))))
        first = rows[0]['at'] if rows else 0.0
        found[sid] = [[round(e['at'] - first), round(e['len']), ' '.join(e['tokens'])] for e in rows]
    body = json.dumps(dict(sorted(found.items())), separators=(',', ':'), ensure_ascii=False)
    with open(out_js, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('// The game\'s own pacenotes for each stage, by its stage id (tools/gamefiles/pacenotes.py made this file;\n'
                 '// make it again after a game update). Each note: [metres from the stage\'s first note, its length in\n'
                 '// metres, its tokens]. src/copilot.js puts them into words.\n')
        fh.write('export const PACENOTES = ' + body + ';\n')
    print('%d stages written to %s; no stage id for: %s' % (len(found), out_js, ', '.join(missing) or 'none'))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
