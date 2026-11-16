// Community content: what the app's COMMUNITY page lists and installs into the game (client acr_daily/community.py).
// Two categories, tracks and cars; for now one track, ACR DAILY London (made with acr-stagegen,
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
// Stages from other tools (the test builds only, `testOnly`: a public app isn't sent them), installed their own way
// (the item's `install`, client community.py):
//   'manager'  Sando Rally's original stages (sandorally.com, Diego Sandoval): free for personal play, downloaded only
//              from sandorally.com and never repacked, installed only with Sando's own Stage Manager (it builds the
//              game's stage list from the player's own game files). The app downloads the official zip (`download`: its
//              address, size and SHA-256 as sandorally.com publishes them), unpacks it and opens the manager.
//   'link'     stages a tool makes on the player's PC: Stage-Exporter (Faviogames) converts WRC Generations' stages
//              from the player's own copy of that game. Only a link: nothing is downloaded from here, and no pack of
//              converted WRC Generations stages is offered (they are that game's, for its owners to make themselves).
// `group`: the tool that puts an item's stages into the game's one stage list. Only one tool's stages show at a time
// (each writes the whole list), so the app warns when stages of two groups are in the game.
// `stages`: the game's ids of their variants (the stage list's rows), which the app finds in the game's packages, and
// which join the game's own for routes; like London's, they never enter the dailies' pool on their own.
//
// API: GET /api/community -> {categories: [{id, name, items: [...]}]}

const REPO = 'https://github.com/khanhonthetrack/acr-daily';

// Sando Rally's Chile BioBio (sandorally.com/original-stages): its registration.json in the download names the rows.
const SANDO_CHILE_BIOBIO = {
  id: 'sando-chile-biobio',
  kind: 'track',
  testOnly: true,
  group: 'sando',
  install: 'manager',
  managerName: "Sando Rally's Stage Manager",
  tool: "Sando Rally's Stage Manager",
  name: 'Chile BioBio',
  subtitle: 'Sando Rally · 8.7 km, and 8.6 km reversed · gravel · Chile · Free Practice',
  description: 'Two original gravel stages on one road near La Cumbre and Laraquete in Arauco, Chile, driven both '
    + 'ways. Rebuilt from public map and elevation data. Sando Rally\'s Stage Manager installs it: ACR Daily downloads '
    + 'it from sandorally.com and opens the manager for you. Free Practice only.',
  author: 'Sando Rally',
  location: 'Chile',
  freePracticeOnly: true,
  stages: [
    { stageId: 'SandoChlBioFull', name: 'Chile BioBio' },
    { stageId: 'SandoChlBioRevFull', name: 'Chile BioBio Reverse' },
  ],
  page: 'https://sandorally.com/original-stages',
  download: {
    version: '0.4.2',
    acrBuild: '25170642',
    url: 'https://dl.sandorally.com/chile-biobio/1aa8be953497/Sando-Rally-Chile-BioBio-0.4.2.zip',
    name: 'Sando-Rally-Chile-BioBio-0.4.2.zip',
    size: 4319139566,
    sha256: '1aa8be9534975e5f1fa3fb74ce9dad84f272339d66c4f084fe7f9a8555dc5f93',
    manager: 'Sando-Rally-Original-Stage-Manager.exe',
  },
  terms: 'Free for personal play. Downloaded only from sandorally.com; not to be sold, changed or repacked. Not '
    + 'affiliated with Supernova Games Studios, KUNOS Simulazioni or 505 Games.',
  credits: 'By Diego Sandoval & Sando Rally. Map data (c) OpenStreetMap contributors (ODbL); elevation: Copernicus '
    + 'GLO-30, SRTM; land cover (c) ESA WorldCover 2021 (CC BY 4.0); textures CC0 (Poly Haven). Full notices in the download.',
};

// WRC Generations' stages, made on the player's PC from their own copy of that game by an add-on to the Sando Rally Stage
// Export Tool 0.3.7. Both add-ons run its pipeline, so a stage has the same id whichever made it:
//   Stage-Exporter (github.com/Faviogames/Stage-Exporter, payload/custom/data/stage_builds: variant_row): all 25;
//   Stage Studio, Albert Palahi's (shared on his Patreon; payload/custom/data/allowed_stages.json): the 13 marked S,
//   with its enhancements (crowds, roadside vegetation, replay cameras, ACR-style finishes, night lights...).
const WRCG_STAGES = [
  ['WrcgBeES1Full', 'ZonneBeke'], ['WrcgBeSS1Full', 'Dikkebus'], ['WrcgBeSS2Full', 'Kemmelberg'],
  ['WrcgEsSS1Full', 'Riudecanyes', 'S'], ['WrcgEsSS1RFull', 'Riudecanyes reverse', 'S'], ['WrcgEsSS4Full', 'Savallà', 'S'],
  ['WrcgEsSS4RFull', 'Savallà reverse', 'S'], ['WrcgFrSS1Full', 'Pietrosella', 'S'],
  ['WrcgFrSS1RFull', 'Pietrosella reverse', 'S'], ['WrcgGrSS3Full', 'Paleohori', 'S'], ['WrcgItSS1Full', 'Ronde', 'S'],
  ['WrcgItSS1RFull', 'Ronde reverse', 'S'],
  ['WrcgKeES1Full', 'Ntulele'], ['WrcgKeES1RFull', 'Ntulele reverse'], ['WrcgKeSS1Full', 'Ngema'],
  ['WrcgKeSS1RFull', 'Ngema reverse'], ['WrcgKeSS2Full', 'Seyabei'], ['WrcgKeSS2RFull', 'Seyabei reverse'],
  ['WrcgMxES1Full', 'El Chocolate'], ['WrcgMxSS1Full', 'Media Luna'], ['WrcgMxSS2Full', 'Ibarrilla'],
  ['WrcgDePanzerplatteFull', 'Arena Panzerplatte', 'S'], ['WrcgPtSS4Full', 'Arganil', 'S'],
  ['WrcgSeSS3Full', 'Sävar', 'S'], ['WrcgSeSS4Full', 'Brattby', 'S'],
];

// the tools that make them (the card's GET IT: one picked, its page opens)
const WRCG_TOOLS = [
  { id: 'stage-studio', name: 'Stage Studio', author: 'Albert Palahi',
    stages: WRCG_STAGES.filter((s) => s[2] === 'S').length,
    page: 'https://www.patreon.com/AlbertPalahi/posts/wrc-generations-175220013' },
  { id: 'stage-exporter', name: 'Stage-Exporter', author: 'Faviogames', stages: WRCG_STAGES.length,
    page: 'https://github.com/Faviogames/Stage-Exporter' },
];

const WRCG_STAGE_TOOLS = {
  id: 'wrcg-stages',
  kind: 'track',
  testOnly: true,
  group: 'wrcg',
  install: 'link',
  tool: WRCG_TOOLS.map((t) => t.name).join(' / '),   // (what takes its stages out: the app's warning names it)
  tools: WRCG_TOOLS,
  name: 'WRC Generations stages',
  subtitle: 'Stage Studio or Stage-Exporter · up to 25 stages in 10 countries · tarmac, gravel and snow',
  description: 'Stages from your own copy of WRC Generations, converted on your PC by an add-on to the Sando Rally '
    + 'Stage Export Tool 0.3.7: Albert Palahi\'s Stage Studio (13 stages, with crowds, roadside vegetation, replay '
    + 'cameras and ACR-style finishes) or Faviogames\' Stage-Exporter (25 stages). You need WRC Generations and the '
    + 'export tool; nothing is downloaded from here. Use one of them: the game shows one tool\'s stages at a time. '
    + 'In the game they are under the country, as Imported Spain (Stage Studio) or [MOD] Spain (Stage-Exporter).',
  author: 'Albert Palahi, Faviogames, Sando Rally',
  stages: WRCG_STAGES.map(([stageId, name, studio]) => ({
    stageId, name, tools: studio ? ['stage-studio', 'stage-exporter'] : ['stage-exporter'] })),
  page: WRCG_TOOLS[0].page,                          // (a test build from before `tools`: one page)
  terms: 'Converted from your own WRC Generations, for your own play: don\'t share the stages you export. WRC '
    + 'Generations and its stages belong to their owners.',
};

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
    photo: 'london',          // the app's own copy of its picture (client photos/london.jpg), shown until the image is in
        manifest: `${REPO}/releases/download/acrdaily-london/manifest.json`,
        group: 'acrdaily',                       // (acr-extrastages' stage list)
        tool: 'ACR Daily',                       // (what takes its stages out: the app's warning names it)
        credits: 'Map data (c) OpenStreetMap contributors (ODbL) and Overture Maps; heights: Environment Agency '
          + 'LIDAR (OGL) and Copernicus; trees: "Trees & Bushes pack" by Painkiller5555 (CC-BY 3.0); people: '
          + '"Geo Nodes crowd scene" by mbelinkie (CC0). Full list: CREDITS.txt in the package.',
      },
      SANDO_CHILE_BIOBIO,
      WRCG_STAGE_TOOLS,
    ],
  },
  { id: 'cars', name: 'CARS', items: [] },
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

/** GET /api/community: the categories with their items; image addresses absolute (siteUrl: the website). An item
 *  `testOnly` goes only to a test build (test: the app asking is one, a four-part version: src/voids.js testBuild). */
export function catalog(siteUrl = '', { test = false } = {}) {
  return {
    categories: COMMUNITY.map((c) => ({
      id: c.id,
      name: c.name,
      items: c.items.filter((it) => test || !it.testOnly)
        .map((it) => ({ ...it, image: it.image && it.image.startsWith('/') ? siteUrl + it.image : it.image })),
    })),
  };
}
