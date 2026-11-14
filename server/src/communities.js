// The home page's community spotlight (src/site.js, under the two dailies): rally communities that race on ACR Daily.
// Each: its name, a picture (src/communityimages.js, served at /community/<key>.webp; w x h its size), its Discord
// invite (the picture links there), its league on ACR Daily (optional) and a line about it (translated: N_).
// Another community: one more entry here, and its picture in communityimages.js.
import { N_ } from './i18n.js';

export const COMMUNITIES = [
  { key: 'exr', name: 'EXR Rally', w: 720, h: 480, discord: 'https://discord.gg/YdVBQsEvkZ', league: '6cakcdzn',
    about: N_('The community behind the EXR Rally Championship: a new country every week, its stages and weather kept secret until the round closes.') },
];

export const communityImage = (key) => `/community/${key}.webp`;
