// Community content: what the app's COMMUNITY page lists and installs into the game (client acr_daily/community.py).
// Three categories, tracks, cars and skins; for now one track, ACR DAILY London (made with acr-stagegen,
// https://github.com/khanhonthetrack/acr-stagegen, built into the game with acr-extrastages).
//
// An item's files are a release on GitHub (khanhonthetrack/acr-daily, tagged with the item's id): manifest.json there says what
// the package is (its version, the ACR build it was built for, its zip's size and SHA-256, the files the zip puts into
// the game's Paks\~mods) and the app fetches it first, so a new build of the stage needs only a new upload, no deploy.
// The ACR build matters: acr-extrastages' menu registry is built against one build of the game, and a stale registry
// hides the game's own rows after a patch, so the app installs a package only on its build and takes it out again
// when the game is updated (until a package for the new build is up).
//
// A community stage is driven like the game's own (its stage ids join the game's for routes and DRIVE), but never
// enters the dailies' pool on its own: only a time trial (or a daily) the admin puts on it (python admin.py
// tt-schedule / schedule), whose stage then says which item it needs (`requires`).
//
// API: GET /api/community -> {categories: [{id, name, items: [...]}]}

const REPO = 'https://github.com/khanhonthetrack/acr-daily';

export const COMMUNITY = [
  {
    id: 'tracks',
    name: 'TRACKS',
    items: [
      {
        id: 'acrdaily-london',
        kind: 'track',
        name: 'ACR DAILY London',
        subtitle: 'Westminster · 5.1 km · tarmac · city',
        description: 'A closed-road city stage through London\'s West End: Marylebone, Fitzrovia, Soho, round '
          + 'Trafalgar Square and down Whitehall to the finish in Parliament Square under the Elizabeth Tower. '
          + 'Barriers on both kerbs, crowds, two chicanes. Made from open map data with acr-stagegen.',
        author: 'ACR DAILY',
        location: 'London',                      // the location row acr-extrastages adds to the game's menu
        stages: [
          // the game's ids of its stage variants (acr-extrastages: AcrXs<id> + the variant)
          { stageId: 'AcrXsLn02r0FullForward', name: 'Westminster' },
        ],
        // its release (acr-stagegen scripts/package-stage.ps1 uploads these): the card's picture and the manifest
        image: `${REPO}/releases/download/acrdaily-london/card.jpg`,
        manifest: `${REPO}/releases/download/acrdaily-london/manifest.json`,
        credits: 'Map data (c) OpenStreetMap contributors (ODbL) and Overture Maps; heights: Environment Agency '
          + 'LIDAR (OGL) and Copernicus; trees: "Trees & Bushes pack" by Painkiller5555 (CC-BY 3.0); people: '
          + '"Geo Nodes crowd scene" by mbelinkie (CC0). Full list: CREDITS.txt in the package.',
      },
    ],
  },
  { id: 'cars', name: 'CARS', items: [] },
  { id: 'skins', name: 'SKINS', items: [] },
];

const ITEMS = COMMUNITY.flatMap((c) => c.items);

/** Every community stage id (as the game spells it). */
export const COMMUNITY_STAGE_IDS = ITEMS.flatMap((it) => (it.stages || []).map((s) => s.stageId));

/** The item a stage id belongs to (case-insensitive: the save's case varies), or null. */
export function itemOfStage(stageId) {
  const id = String(stageId || '').toLowerCase();
  return ITEMS.find((it) => (it.stages || []).some((s) => s.stageId.toLowerCase() === id)) || null;
}

/** The menu names of the community stages: {stageId: name}. */
export const COMMUNITY_MENU_NAMES = Object.fromEntries(ITEMS.flatMap((it) => (it.stages || []).map((s) => [s.stageId, s.name])));

/** GET /api/community: the categories with their items; image addresses absolute (siteUrl: the website). */
export function catalog(siteUrl = '') {
  return {
    categories: COMMUNITY.map((c) => ({
      id: c.id,
      name: c.name,
      items: c.items.map((it) => ({ ...it, image: it.image && it.image.startsWith('/') ? siteUrl + it.image : it.image })),
    })),
  };
}
