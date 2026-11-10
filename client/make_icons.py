"""Draws the app's icons, acr_daily/icons/<name>-<px>.png: white on transparent (icons.py tints them as they are shown),
at each size the window may want (the screen's scale: 18 px at 100 %, 27 at 150 %, 36 at 200 %; the home page's big
ones 48, 72, 96).

The drawings are Lucide's (https://lucide.dev, ISC licence: acr_daily/icons/LICENSE-lucide.txt) and the Discord mark
(Discord's own, for a link to the ACR Daily Discord, as on the website: server/src/site.js DISCORD_MARK).
Run it again only to change the icons; the PNGs are kept in the repository, so a build needs none of this:
  npm pack lucide-static@0.460.0 && tar xzf lucide-static-0.460.0.tgz     (the drawings, into ./package)
  pip install cairosvg                                                    (needs the cairo library)
  python make_icons.py path/to/package
"""
import os
import re
import sys

import cairosvg

# the app's name for each icon -> Lucide's
LUCIDE = {
    'home': 'house', 'back': 'chevron-left', 'inbox': 'mail', 'shop': 'shopping-cart', 'settings': 'settings',
    'help': 'circle-help', 'quit': 'power', 'user': 'user', 'live': 'radio', 'dailies': 'flag', 'tt': 'timer',
    'leagues': 'users', 'h2h': 'swords', 'cups': 'trophy', 'trophy': 'trophy', 'medal': 'medal', 'wrench': 'wrench',
    'calendar': 'calendar-days', 'map': 'map', 'gauge': 'gauge', 'play': 'play', 'check': 'check', 'globe': 'globe',
}
DISCORD = ('M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495'
           '-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 '
           '0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 '
           '1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-'
           '.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743'
           '.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077'
           '.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076'
           '.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-'
           '13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189'
           ' 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419'
           ' 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z')
SIZES = (18, 27, 36, 48, 72, 96)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'acr_daily', 'icons')


def lucide_svg(package, name):
    """A Lucide drawing, white (its strokes are currentColor)."""
    with open(os.path.join(package, 'icons', name + '.svg'), encoding='utf-8') as f:
        svg = f.read()
    svg = re.sub(r'<!--.*?-->', '', svg, flags=re.S)
    return svg.replace('currentColor', '#FFFFFF')


def main(package):
    os.makedirs(OUT, exist_ok=True)
    drawings = {name: lucide_svg(package, lu) for name, lu in LUCIDE.items()}
    drawings['discord'] = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
                           '<path fill="#FFFFFF" d="%s"/></svg>' % DISCORD)
    for name, svg in sorted(drawings.items()):
        for px in SIZES:
            cairosvg.svg2png(bytestring=svg.encode(), write_to=os.path.join(OUT, '%s-%d.png' % (name, px)),
                             output_width=px, output_height=px)
    with open(os.path.join(package, 'LICENSE'), encoding='utf-8') as f:
        lic = f.read()
    with open(os.path.join(OUT, 'LICENSE-lucide.txt'), 'w', encoding='utf-8') as f:
        f.write('The icons in this folder (all but discord-*.png) are drawings of Lucide (https://lucide.dev), %s,\n'
                'under its licence:\n\n%s' % ('lucide-static 0.460.0', lic))
    print('%d icons x %d sizes in %s' % (len(drawings), len(SIZES), OUT))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'package')
