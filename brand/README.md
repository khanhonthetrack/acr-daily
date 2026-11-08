# ACR Daily logo

A, C and R step down beside a red D that is also a rally car diving nose-first: the D's straight side is the
car's floor with the two wheels, its counter is the side window, speed lines trail behind. Letters are Barlow
Condensed Black Italic (SIL Open Font License), converted to outlines.

| File | Use |
| --- | --- |
| `acr-daily-logo.svg` | the logo on black or dark grounds (red car, white letters) |
| `acr-daily-logo-black.svg` | one colour, on ACR red or white |
| `acr-daily-logo-white.svg` | one colour, on photos and video |
| `acr-daily-icon.svg` | app icon, 48 px and up |
| `acr-daily-icon-small.svg` | app icon and favicon, 32 px and below (no speed lines) |

Colours: ACR red `#E30613` (as in the Assetto Corsa Rally logo), white `#F4F4F5`, black `#0A0A0B`.

The same drawing is in `server/src/logo.js` (website header and favicon) and `client/make_icon.py` (the app's
`icon.ico` and header `logo-*.png`); change all three together.

## Facebook page (`facebook/`)

| File | Use |
| --- | --- |
| `acr-daily-facebook-cover.png` | cover photo, 1640 x 624. Phones show the middle 16:9 (x 265 to 1375), so the logo and words stay in it. |
| `acr-daily-facebook-profile.png` | profile picture, 1080 x 1080. Facebook crops it to a circle, and the logo fits inside it. |
| `*.svg` | the same drawings (the cover's words need Barlow Condensed installed) |
| `make_facebook.mjs` | draws them all: `node brand/facebook/make_facebook.mjs` (needs Playwright with Chromium) |

The background is a night stage: mountain ridges with pines and a hairpin road with a long-exposure light trail
in ACR red. The script draws all of it from code, using a fixed seed so every run gives the same picture. No
photo or outside image is used, so there is nothing to license apart from the logo and the fonts (OFL). The
script downloads the fonts from Google Fonts the first time it runs and keeps them in `facebook/.fonts`, which
is not committed.
