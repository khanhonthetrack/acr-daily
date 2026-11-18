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

// WRC Generations' stages, made on the player's PC from their own copy of that game: INSTALL has the app run Stage
// Exporter (Albert Palahi's add-on to Sando Rally's Stage Export Tool 0.3.7, published on GitHub by Faviogames) for that
// one stage, and REMOVE takes it out again. Sando no longer offers his tool (sandorally.com/stage-export-tool-discontinued:
// he took it down so as not to be part of people sharing exported stages): the app uses a copy already on the player's
// PC, else downloads the Internet Archive's copy of his file (base.download, checked byte for byte), and nothing it
// makes leaves that PC.
export const STAGE_EXPORTER = {
  id: 'stage-exporter',
  name: 'Stage Exporter',
  author: 'Albert Palahi',
  version: '1.5.0',
  // its files: GitHub's archive of the repository at that commit ("Release Stage Exporter 1.5"), checked file by file:
  // payloadSha256 is the SHA-256 of the lines "<path>\t<SHA-256 of the file>\n" of every file under payload/, sorted by
  // path. From 1.5 its pack is in Paks\~mods (1.0.0's in Paks: 1.5 moves it there on its next run).
  commit: 'eece82fbec51b8e0f186d7f9661e714dc30b4632',
  url: 'https://codeload.github.com/Faviogames/Stage-Exporter/zip/eece82fbec51b8e0f186d7f9661e714dc30b4632',
  files: 69,
  payloadSha256: '8692d35941243b17c701af0c3dea0d95cb4b0cd6eccb84427339383e5639eb91',
  page: 'https://github.com/Faviogames/Stage-Exporter',
  base: { name: 'Sando Rally Stage Export Tool', version: '0.3.7', author: 'Sando Rally',
    page: 'https://sandorally.com/stage-export-tool-discontinued',
    // (without it on the player's PC: the Internet Archive's copy of sandorally.com's own zip, 4 Nov 2026; `id_` = the
    // file as it was served, byte for byte)
    download: {
      name: 'Sando-Rally-Stage-Export-Tool-0.3.7.zip',
      url: 'https://web.archive.org/web/20261104103223id_/https://sandorally.com/downloads/Sando-Rally-Stage-Export-Tool-0.3.7.zip',
      size: 84427633,
      sha256: '2b54bcc50e5fe308782684254d56227108120cee30171e33bfcf79f55dc446ce',
    } },
  minutes: 40,                                 // (making one stage, as its guide says: "40 minutes or more")
};

// its stages: every one it can make (custom/data/allowed_stages.json and stage_builds: slug, variant_row, stage_name,
// acr_surface), less Belgium's three (ZonneBeke, Dikkebus, Kemmelberg: Sando's tool stops on a road piece turned in their
// one level, BE_YPRES; tried 2026-11-17)
const WRCG_COUNTRY = { es: 'Spain', fr: 'Corsica', gr: 'Greece', it: 'Italy', ke: 'Kenya', mx: 'Mexico',
  panzerplatte: 'Germany', pt: 'Portugal', se: 'Sweden' };
const WRCG_STAGES = [
  ['es_ss1', 'WrcgEsSS1Full', 'Riudecanyes', 'tarmac'], ['es_ss1r', 'WrcgEsSS1RFull', 'Riudecanyes reverse', 'tarmac'],
  ['es_ss4', 'WrcgEsSS4Full', 'Savallà', 'tarmac'], ['es_ss4r', 'WrcgEsSS4RFull', 'Savallà reverse', 'tarmac'],
  ['fr_ss1', 'WrcgFrSS1Full', 'Pietrosella', 'tarmac'], ['fr_ss1r', 'WrcgFrSS1RFull', 'Pietrosella reverse', 'tarmac'],
  ['gr_ss3', 'WrcgGrSS3Full', 'Paleohori', 'gravel'],
  ['it_ss1', 'WrcgItSS1Full', 'Ronde', 'tarmac'], ['it_ss1r', 'WrcgItSS1RFull', 'Ronde reverse', 'tarmac'],
  ['ke_es1', 'WrcgKeES1Full', 'Ntulele', 'gravel'], ['ke_es1r', 'WrcgKeES1RFull', 'Ntulele reverse', 'gravel'],
  ['ke_ss1', 'WrcgKeSS1Full', 'Ngema', 'gravel'], ['ke_ss1r', 'WrcgKeSS1RFull', 'Ngema reverse', 'gravel'],
  ['ke_ss2', 'WrcgKeSS2Full', 'Seyabei', 'gravel'], ['ke_ss2r', 'WrcgKeSS2RFull', 'Seyabei reverse', 'gravel'],
  ['mx_es1', 'WrcgMxES1Full', 'El Chocolate', 'gravel'], ['mx_ss1', 'WrcgMxSS1Full', 'Media Luna', 'gravel'],
  ['mx_ss2', 'WrcgMxSS2Full', 'Ibarrilla', 'gravel'],
  ['panzerplatte', 'WrcgDePanzerplatteFull', 'Arena Panzerplatte', 'tarmac'], ['pt_ss4', 'WrcgPtSS4Full', 'Arganil', 'gravel'],
  ['se_ss3', 'WrcgSeSS3Full', 'Sävar', 'snow'], ['se_ss4', 'WrcgSeSS4Full', 'Brattby', 'snow'],
];

function wrcgItem([slug, stageId, name, surface]) {
  const country = WRCG_COUNTRY[slug.split('_')[0]];
  return {
    id: `wrcg-${slug.replace(/_/g, '-')}`,
    kind: 'track',
    testOnly: true,
    group: 'wrcg',
    install: 'export',                         // (made on the player's PC: the app runs `exporter` for `slug`)
    exporter: STAGE_EXPORTER.id,
    slug,
    tool: STAGE_EXPORTER.name,                 // (what takes its stages out: the app's warning names it)
    name,
    subtitle: `WRC Generations · ${country} · ${surface}`,
    description: 'Made on your PC from your own copy of WRC Generations by Stage Exporter, Albert Palahi\'s add-on to '
      + 'Sando Rally\'s Stage Export Tool. In the game it is under [MOD] and its country.',
    author: 'Albert Palahi, Sando Rally',
    stages: [{ stageId, name }],
    terms: 'Made from your own WRC Generations, for your own play: never share the stages it makes. WRC Generations and '
      + 'its stages belong to their owners.',
  };
}

const WRCG_ITEMS = WRCG_STAGES.map(wrcgItem);

export const COMMUNITY = [
  {
    id: 'tracks',
    name: 'TRACKS',
    items: [
      {
        id: 'acrdaily-london',
        kind: 'track',
        name: 'ACR DAILY London',
        subtitle: 'Westminster, both ways · 5.1 km · tarmac · city',
        description: 'Closed-road city stages through London\'s West End: Marylebone, Fitzrovia, Soho, round '
          + 'Trafalgar Square and down Whitehall to the finish in Parliament Square under the Elizabeth Tower, '
          + 'and the same streets the other way. Barriers on both kerbs, crowds, two chicanes, the Service Park on '
          + 'Horse Guards Parade. Made from open map data, built on your PC from your own copy of the game.',
        author: 'ACR DAILY',
        location: 'London',                      // the location row the track adds to the game's menu
        stages: [
          // the game's ids of its stages (AcrXs<id> + the variant): Marylebone - Whitehall and the same streets the
          // other way, Whitehall - Marylebone
          { stageId: 'AcrXsLn02r0FullForward', name: 'Westminster' },
          { stageId: 'AcrXsLn02r1FullForward', name: 'Westminster Reverse' },
        ],
        // its release: the card's picture and the manifest (from version 8 a package built on the player's PC: the
        // app's community.py assemble)
        image: `${REPO}/releases/download/acrdaily-london/card.jpg`,
    photo: 'london',          // the app's own copy of its picture (client photos/london.jpg), shown until the image is in
        manifest: `${REPO}/releases/download/acrdaily-london/manifest.json`,
        group: 'acrdaily',                       // (its stage list)
        tool: 'ACR Daily',                       // (what takes its stages out: the app's warning names it)
        credits: 'Map data (c) OpenStreetMap contributors (ODbL) via Overture Maps; land cover: ESA WorldCover (CC BY '
          + '4.0); heights: Copernicus and Environment Agency (OGL). The trees, crowds, marshals, barrier frames, cars, '
          + 'gantries and the Service Park are the game\'s own, from your copy of it. Full list: CREDITS.txt in the '
          + 'package.',
      },
      {
        id: 'hattori-lousa',
        kind: 'track',
        testOnly: true,
        name: 'Lousã',
        subtitle: 'Hattori Rally · 6.7 km · gravel · Portugal',
        description: 'A Rally de Portugal gravel stage in the Serra da Lousã, made from Portugal\'s lidar terrain. '
          + 'Built on your PC from your own copy of the game: about 10 minutes, and about 20 GB free on the game\'s '
          + 'drive while it builds.',
        author: 'Hattori Rally',
        location: 'Portugal',
        stages: [{ stageId: 'AcrXsPtLousaFullForward', name: 'Lousã' }],
        // its release: the card's picture and the manifest (a package its author's kit builds on the player's PC:
        // the app's community.py build_kit)
        image: `${REPO}/releases/download/hattori-lousa/card.jpg`,
        manifest: `${REPO}/releases/download/hattori-lousa/manifest.json`,
        group: 'lousa',                          // (its own stage list: the stage switch shows it or London)
        tool: 'ACR Daily',
        terms: 'Free for offline single-player play. Share the download, never the stage files it builds in your game. '
          + 'Not affiliated with Kunos Simulazioni, Supernova Games Studios or 505 Games.',
        credits: 'By Hattori Rally. Terrain: Direção-Geral do Território, Portugal (CC BY 4.0). Full list: CREDITS.md '
          + 'in the package.',
      },
      SANDO_CHILE_BIOBIO,
      ...WRCG_ITEMS,
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
 *  `testOnly` goes only to a test build (test: the app asking is one, a four-part version: src/voids.js testBuild),
 *  and so do `tools` (the stage makers an item's `exporter` names). */
export function catalog(siteUrl = '', { test = false } = {}) {
  const out = {
    categories: COMMUNITY.map((c) => ({
      id: c.id,
      name: c.name,
      items: c.items.filter((it) => test || !it.testOnly)
        .map((it) => ({ ...it, image: it.image && it.image.startsWith('/') ? siteUrl + it.image : it.image })),
    })),
  };
  if (test) out.tools = { [STAGE_EXPORTER.id]: STAGE_EXPORTER };   // (what an `exporter` item's INSTALL runs)
  return out;
}
