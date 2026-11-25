"""The series' and special events' images into the website (server/src/seriesimages.js, as WebP in base64): run from
the repository's root, python tools/series_logos/to_webp.py <key> [<key>...] (from tools/series_logos/<key>.png,
<key>-logo.png and, when there is one, <key>-banner.png)."""
import base64
import io
import os
import re
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '..', 'server', 'src', 'seriesimages.js')


def webp(path, size=None, q=82):
    im = Image.open(path).convert('RGBA')
    if size:
        im = im.resize(size, Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, 'WEBP', quality=q, method=6)
    return base64.b64encode(b.getvalue()).decode()


def main(keys):
    s = open(OUT, encoding='utf-8').read()
    add = {}
    for key in keys:
        add[key] = webp(os.path.join(HERE, key + '.png'), (480, 270))
        add[key + '-logo'] = webp(os.path.join(HERE, key + '-logo.png'))
        if os.path.isfile(os.path.join(HERE, key + '-banner.png')):
            add[key + '-banner'] = webp(os.path.join(HERE, key + '-banner.png'), None, 80)
    for k in add:
        s = re.sub(r'\n"%s": "[^"]*",?' % re.escape(k), '', s)
    i = s.rstrip().rfind('};')
    body = s[:i].rstrip()
    if not body.endswith(','):
        body += ','
    body += '\n' + ',\n'.join('"%s": "%s"' % kv for kv in add.items()) + '\n'
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(body + s[i:])
    print({k: len(v) for k, v in add.items()})


if __name__ == '__main__':
    main(sys.argv[1:])
