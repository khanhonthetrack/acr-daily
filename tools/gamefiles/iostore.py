"""Extract files from Assetto Corsa Rally's IoStore containers (unencrypted, Oodle) with the ooz helper."""
import struct, glob, os, subprocess, sys
D = os.path.join(os.environ.get('ACR_GAME_DIR', r'E:\SteamLibrary\steamapps\common\Assetto Corsa Rally'), 'acr', 'Content', 'Paks')
OOZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ooz', 'target', 'release', 'ooz.exe')
def fstr(b, o):
    n = struct.unpack_from('<i', b, o)[0]; o += 4
    if n < 0:
        return b[o:o - 2 * n].decode('utf-16-le').rstrip('\x00'), o - 2 * n
    return b[o:o + n].decode('latin-1').rstrip('\x00'), o + n
class Toc:
    def __init__(self, path):
        b = open(path, 'rb').read()
        self.path = path
        hs, ec, cbc, cbs, cmc, cml, self.cbsize, dis = struct.unpack_from('<8I', b, 20)
        flags = b[80]; seeds = struct.unpack_from('<I', b, 84)[0]; nophash = struct.unpack_from('<I', b, 96)[0]
        o = hs
        self.ids = [b[o + 12 * i:o + 12 * i + 12] for i in range(ec)]; o += ec * 12
        self.ol = []
        for i in range(ec):
            e = b[o + 10 * i:o + 10 * i + 10]
            self.ol.append((int.from_bytes(e[0:5], 'big'), int.from_bytes(e[5:10], 'big')))
        o += ec * 10 + seeds * 4 + nophash * 4
        self.blocks = []
        for i in range(cbc):
            e = b[o + cbs * i:o + cbs * i + 12]
            self.blocks.append((int.from_bytes(e[0:5], 'little'), int.from_bytes(e[5:8], 'little'),
                                int.from_bytes(e[8:11], 'little'), e[11]))
        o += cbc * cbs
        self.methods = [b[o + i * cml:o + (i + 1) * cml].split(b'\0')[0].decode() for i in range(cmc)]
        o += cmc * cml
        self.files = {}
        if flags & 8 and dis:
            di = b[o:o + dis]; p = 0
            mount, p = fstr(di, p)
            nd = struct.unpack_from('<I', di, p)[0]; p += 4
            dirs = [struct.unpack_from('<4I', di, p + 16 * i) for i in range(nd)]; p += 16 * nd
            nf = struct.unpack_from('<I', di, p)[0]; p += 4
            fl = [struct.unpack_from('<3I', di, p + 12 * i) for i in range(nf)]; p += 12 * nf
            ns = struct.unpack_from('<I', di, p)[0]; p += 4
            st = []
            for _ in range(ns):
                s, p = fstr(di, p); st.append(s)
            N = 0xffffffff
            def walk(d, prefix):
                name, child, sib, ff = dirs[d]
                path = prefix + (st[name] + '/' if name != N else '')
                f = ff
                while f != N:
                    self.files[(path + st[fl[f][0]]).replace('../../../', '')] = fl[f][2]; f = fl[f][1]
                c = child
                while c != N:
                    walk(c, path); c = dirs[c][2]
            walk(0, mount)
    def extract_index(self, idx, out):
        off, ln = self.ol[idx]
        first, last = off // self.cbsize, (off + ln - 1) // self.cbsize
        lines = ['%d %d %d %d' % (bo, cs, us, m) for bo, cs, us, m in self.blocks[first:last + 1]]
        ucas = self.path[:-5] + '.ucas'
        subprocess.run([OOZ, ucas, out], input='\n'.join(lines).encode(), check=True)
        data = open(out, 'rb').read()
        skip = off - first * self.cbsize
        data = data[skip:skip + ln]
        open(out, 'wb').write(data)
        return data
_tocs = None
def tocs():
    global _tocs
    if _tocs is None:
        _tocs = [Toc(p) for p in sorted(glob.glob(D + r'\*.utoc'))]
    return _tocs
def find(sub):
    return [(t, f, i) for t in tocs() for f, i in t.files.items() if sub in f]
if __name__ == '__main__':
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    for sub in sys.argv[2:]:
        for t, f, i in find(sub):
            out = os.path.join(outdir, os.path.basename(f))
            data = t.extract_index(i, out)
            print(len(data), f)
