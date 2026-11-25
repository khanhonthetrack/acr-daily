// Community content: what the app's COMMUNITY page lists and installs into the game (client acr_daily/community.py).
// Two categories, tracks and cars. Every item says who made it (`author`) and everyone it owes (`credits`: its makers,
// its tools, its data), shown on its card.
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
// `off`: taken off the list for now (no app is offered it), but still known by its stages (their names, old results).
//
// API: GET /api/community -> {categories: [{id, name, items: [...]}]}

const REPO = 'https://github.com/khanhonthetrack/acr-daily';

// Sando Rally's Chile BioBio (sandorally.com/original-stages): its registration.json in the download names the rows.
const SANDO_CHILE_BIOBIO = {
  id: 'sando-chile-biobio',
  kind: 'track',
  off: true,                                   // (off the list for now: the user, 19 Nov 2026, the game's 0.7 update)
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
  surface: 'Gravel',                           // (a time trial's stage line: where, and on what)
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
    pack: 'ChileBioBio',                       // (his manager's name for it in its state: the installed version, UPDATE)
  },
  terms: 'Free for personal play. Downloaded only from sandorally.com; not to be sold, changed or repacked. Not '
    + 'affiliated with Supernova Games Studios, KUNOS Simulazioni or 505 Games.',
  credits: 'By Diego Sandoval & Sando Rally. Map data (c) OpenStreetMap contributors (ODbL); elevation: Copernicus '
    + 'GLO-30 ((c) DLR, Airbus), SRTM (USGS); land cover (c) ESA WorldCover 2021 (CC BY 4.0); textures CC0 from Poly '
    + 'Haven by Rob Tuytel, Charlotte Baglioni, Amal Kumar, Dario Barresi and Greg Zaal. Full notices in the download.',
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
  version: '1.6.3',
  // its files: its release's own zip ("Stage-Exporter-v1.6.3-Instalar.zip": from 1.6.2 only that one carries payload/bin,
  // its files for the game's 0.7, build 26756580: their mappings and a level migrator; GitHub's archive of the commit
  // doesn't), checked as a whole (zipSha256, GitHub's own digest of the asset) and file by file: payloadSha256 is the
  // SHA-256 of the lines "<path>\t<SHA-256 of the file>\n" of every file under payload/, sorted by path. From 1.5 its
  // pack is in Paks\~mods. Stages made before 1.6.2 must be made again on 0.7 (its notes).
  commit: 'df8d9230cbfc3e18a6003cb67d6b1f8ed0f3f5dc',
  url: 'https://github.com/Faviogames/Stage-Exporter/releases/download/v1.6.3/Stage-Exporter-v1.6.3-Instalar.zip',
  zipSha256: 'a04e496019d36ec3bbd537609157cb301bc880972513db268cf6b6b7fef380bf',
  files: 83,
  payloadSha256: '2c9d2efb53e65cb3cae28d85d7521e26dd465fe70a1bb7bc3db76f8e5a2754a6',
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
// each country's photo on its stages' cards (the app's own: client photos/, from 0.1.5.54; the user, 19 Nov 2026: "each
// stage of WRCG should have a banner from that country"). Greece's and Sweden's are the rallies' (livigno: Rally Sweden).
const WRCG_PHOTO = { es: 'spain', fr: 'corsica', gr: 'greece', it: 'italy', ke: 'kenya', mx: 'mexico',
  panzerplatte: 'germany', pt: 'portugal', se: 'livigno' };
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

// who made a WRC Generations stage possible: the game's makers, and the tools that convert it
const WRCG_CREDITS = 'Stage from WRC Generations by KT Racing (Nacon), made from your own copy. Converted by Stage '
  + 'Exporter (Albert Palahi) and Sando Rally\'s Stage Export Tool (Diego Sandoval), with retoc (Truman Kilen and '
  + 'Archengius) and UAssetAPI (atenfyr).';

function wrcgItem([slug, stageId, name, surface]) {
  const country = WRCG_COUNTRY[slug.split('_')[0]];
  return {
    id: `wrcg-${slug.replace(/_/g, '-')}`,
    kind: 'track',
    photo: WRCG_PHOTO[slug.split('_')[0]],
    // (test builds only: on the game's 0.7 Stage Exporter 1.6.3 can't make a stage on a PC that never made one before
    // the update: Sando's core takes a template from a test level 0.7 removed, DA_oval_cutscene_authoringBakedData;
    // tried 20 Nov 2026)
    testOnly: true,
    group: 'wrcg',
    install: 'export',                         // (made on the player's PC: the app runs `exporter` for `slug`)
    exporter: STAGE_EXPORTER.id,
    slug,
    tool: STAGE_EXPORTER.name,                 // (what takes its stages out: the app's warning names it)
    name,
    location: country,                         // (a time trial's stage line: where, and on what)
    surface: surface[0].toUpperCase() + surface.slice(1),
    subtitle: `WRC Generations · ${country} · ${surface}`,
    description: 'Made on your PC from your own copy of WRC Generations by Stage Exporter, Albert Palahi\'s add-on to '
      + 'Sando Rally\'s Stage Export Tool. In the game it is under [MOD] and its country, in Free Practice and Rally '
      + 'Weekend.',
    author: 'Albert Palahi, Sando Rally',
    stages: [{ stageId, name }],
    terms: 'Made from your own WRC Generations, for your own play: never share the stages it makes. WRC Generations and '
      + 'its stages belong to their owners.',
    credits: WRCG_CREDITS,
  };
}

const WRCG_ITEMS = WRCG_STAGES.map(wrcgItem);

// Oxmod's Thierache stages (patreon.com/cw/oxmod; the user, 25 Nov 2026: "Integrate the following stages to the
// community tracks, make sure all stages can live together (give credit to Oxmod)"). All rights reserved, no
// redistribution: the app downloads each zip from Oxmod's own Patreon post on the player's PC (its file link) and checks
// it against the SHA-256 below (his SHA256SUMS.txt and the zip's own), and nothing of it is hosted here. From each zip
// the app takes only the stage's own containers (not his installer, nor the program it starts with Windows, nor
// Chemin des Erables' two packs that replace the game's own grass, kerb and sand surfaces and its crowds' reaction for
// every stage: dailies and ranked rallies are driven on the game's own), and the set's stage list in the version for
// what is installed (S1 alone, Chemin alone, both), packed again under a name of its own (its own is London's:
// community.py place_registry).
const OXMOD_ZIP_SUMS = {
  'menu/S1_seule/zz_acrxs_registry_P.pak': '75e7144577253917f6da7312ef5e585b12fb728226a22b0938323751a6b555cd',
  'menu/S1_seule/zz_acrxs_registry_P.ucas': '56c69427f5c9c8d9c54e989b15db4c090e7b64bda9e958e1c41425fcd0091e44',
  'menu/S1_seule/zz_acrxs_registry_P.utoc': '66caf217946ad8453a111d397a1182e5e29280cc06b7bdcaf90930d191bbe225',
  'menu/Chemin_seul/zz_acrxs_registry_P.pak': '75e7144577253917f6da7312ef5e585b12fb728226a22b0938323751a6b555cd',
  'menu/Chemin_seul/zz_acrxs_registry_P.ucas': 'cd3805ec2b5676d7f1f8eadfda46ebba8076b21769d227179e5dadd26a89d664',
  'menu/Chemin_seul/zz_acrxs_registry_P.utoc': 'b81622431798edde4f08e6132ee065a4978287662a7492a7ee4dac6282935605',
  'menu/S1_et_Chemin/zz_acrxs_registry_P.pak': '75e7144577253917f6da7312ef5e585b12fb728226a22b0938323751a6b555cd',
  'menu/S1_et_Chemin/zz_acrxs_registry_P.ucas': 'f6c7e1bbfa82119250b18f828befadce1dda5eac683a66ccf7748a9de435b0e1',
  'menu/S1_et_Chemin/zz_acrxs_registry_P.utoc': '6d109498b0da92a383f03105e32ea6dc4a9a921621f076e1db4e450d356b0717',
};
const OXMOD_REGISTRY = {
  name: 'zz_acrxs_oxmod_registry_P', group: 'oxmod',
  variants: { 'oxmod-thierache-s1': 'menu/S1_seule/zz_acrxs_registry_P', 'oxmod-chemin-erables': 'menu/Chemin_seul/zz_acrxs_registry_P',
    'oxmod-chemin-erables+oxmod-thierache-s1': 'menu/S1_et_Chemin/zz_acrxs_registry_P' },
  sha256: OXMOD_ZIP_SUMS,
  tools: STAGE_EXPORTER.base.download,           // (retoc packs it: Sando's tool, unless his tools are on the PC already)
  // its Rally Weekend (none in his list: Free Practice only): three calendars of Thierache added to it on the PC, keyed
  // as the app names an AcrXs stage's (rallyweekend.location_preset: AcrXsThi04FullForward -> AcrXsThiWeekendShort)
  calendars: { location: 'Thierache', key: 'AcrXsThi', name: 'Thiérache', text: 'Stages by Oxmod (patreon.com/cw/oxmod).' },
};
const oxFile = (name, size, sha256) => ({ name, from: `~mods/${name}`, size, sha256 });
const OXMOD_PAK = '75e7144577253917f6da7312ef5e585b12fb728226a22b0938323751a6b555cd';
const OXMOD_CREDITS = 'By Oxmod (patreon.com/cw/oxmod), downloaded from his Patreon. Built with ACR Extra Stages '
  + '(cherrymcgerry). Geographic data (c) IGN, Licence Ouverte 2.0. The host level, trees and the crowds are the game\'s '
  + 'own, from your copy of it.';
const OXMOD_TERMS = '(c) 2026 Oxmod, all rights reserved: downloaded only from his Patreon, never shared or repacked. '
  + 'Unofficial mod, not affiliated with Kunos Simulazioni, Supernova Games Studios or 505 Games.';
const OXMOD_ITEMS = [
  {
    id: 'oxmod-thierache-s1',
    kind: 'track',
    minApp: '0.2.2',                            // (the first app that takes a zip from its author's link and its list)
    name: 'Thiérache · Le Bois du Mont',
    subtitle: 'Oxmod · S1 Braye-en-Thiérache - Harcigny · 6.8 km · tarmac · France',
    description: 'A tarmac stage in the Thiérache, in the Aisne: bocage, hedges, brick villages and crests one after '
      + 'another, after a stage of the Rallye régional de Vervins. INSTALL downloads it from Oxmod\'s Patreon and puts '
      + 'it in your game, beside the other stages.',
    author: 'Oxmod',
    location: 'Thiérache',
    surface: 'Tarmac',
    stages: [{ stageId: 'AcrXsThi04FullForward', name: 'Braye-en-Thiérache - Harcigny' }],      // (the game's menu: S1)
    photo: 'thierache',
    group: 'oxmod',
    tool: 'ACR Daily',
    terms: OXMOD_TERMS,
    credits: OXMOD_CREDITS,
    support: { name: 'Patreon', url: 'https://www.patreon.com/cw/oxmod' },
    package: {
      version: '3.4', acrBuild: '26756580',
      zip: { name: 'Thierache_S1_v3.4.zip', size: 797312565, sha256: 'c050abd1e756bc0c8021467719f050399dd5bc8df7f0cc0fc95ce512dfdd21ac',
        url: 'https://www.patreon.com/file?h=175683992&m=790343161', page: 'https://www.patreon.com/posts/175683992' },
      files: [oxFile('zz_acrxs_s_acrxsthi04_P.pak', 347, OXMOD_PAK),
        oxFile('zz_acrxs_s_acrxsthi04_P.ucas', 2038943664, '0639676305dbb3b6b7034e377624dc4c6d78fde6906443305c43bd8b86a3b000'),
        oxFile('zz_acrxs_s_acrxsthi04_P.utoc', 484557, 'b39943e057214f8a608f2fcdb06cdcc2db3c7bb0e91907949a3047836d47d917')],
      registry: OXMOD_REGISTRY,
    },
  },
  {
    id: 'oxmod-chemin-erables',
    kind: 'track',
    minApp: '0.2.2',
    name: 'Thiérache · Chemin des Érables',
    subtitle: 'Oxmod · 2.7 km · gravel · France · with and without ruts',
    description: 'A short gravel test stage on a forest track under autumn maples: puddles, a ford, crowds and smoke. '
      + 'Two versions in the game\'s menu, with ruts and without. INSTALL downloads it from Oxmod\'s Patreon and puts '
      + 'it in your game, beside the other stages.',
    author: 'Oxmod',
    location: 'Thiérache',
    surface: 'Gravel',
    stages: [{ stageId: 'AcrXsThi05FullForward', name: 'Chemin des Érables (avec ornières)' },
      { stageId: 'AcrXsThi06FullForward', name: 'Chemin des Érables (sans ornières)' }],
    photo: 'chemin-erables',
    group: 'oxmod',
    tool: 'ACR Daily',
    terms: OXMOD_TERMS,
    credits: OXMOD_CREDITS,
    support: { name: 'Patreon', url: 'https://www.patreon.com/cw/oxmod' },
    package: {
      version: '1.2', acrBuild: '26756580',
      zip: { name: 'Chemin_des_Erables_v1.2.zip', size: 384850694, sha256: '8fb6b4542a6aa2aab0f2020ccc28b7d7e29e11a81f29554577ca4c922d2b0bbb',
        url: 'https://www.patreon.com/file?h=176009113&m=788813231', page: 'https://www.patreon.com/posts/176009113' },
      files: [oxFile('zz_acrxs_s_acrxsthi05_P.pak', 347, OXMOD_PAK),
        oxFile('zz_acrxs_s_acrxsthi05_P.ucas', 441855576, 'cb86787f47acc11ee5328590378d70d7c2643f2a7f3d08bb222b3cca536366ed'),
        oxFile('zz_acrxs_s_acrxsthi05_P.utoc', 107652, 'eea425e7bf070c5d447e2f16ebbbd76c87a6b3553e161bebdb92292c61422b86'),
        oxFile('zz_acrxs_s_acrxsthi06_P.pak', 347, OXMOD_PAK),
        oxFile('zz_acrxs_s_acrxsthi06_P.ucas', 441855576, 'b9ce54cd6a8db38172f9edc5de8791f26b5c3d8eb4ccacec4b37b5db69505345'),
        oxFile('zz_acrxs_s_acrxsthi06_P.utoc', 107652, 'c13fa181f03970e579037d325fca7434de297ff2bf4c59a9286e896bac1809fa')],
      registry: OXMOD_REGISTRY,
    },
  },
];

export const COMMUNITY = [
  {
    id: 'tracks',
    name: 'TRACKS',
    items: [
      {
        id: 'acrdaily-london',
        kind: 'track',
        name: 'London',                          // (the user, 19 Nov 2026: "call it just London")
        subtitle: 'Westminster, both ways · 5.1 km · tarmac · city',
        description: 'Closed-road city stages through London\'s West End: Marylebone, Fitzrovia, Soho, round '
          + 'Trafalgar Square and down Whitehall to the finish in Parliament Square under the Elizabeth Tower, '
          + 'and the same streets the other way. Barriers on both kerbs, crowds, two chicanes, the Service Park on '
          + 'Horse Guards Parade. Made from open map data, built on your PC from your own copy of the game.',
        author: 'ACR DAILY',
        location: 'London',                      // the location row the track adds to the game's menu
        surface: 'Tarmac',
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
        credits: 'By ACR DAILY, built with ACR Extra Stages (cherrymcgerry) and retoc (Truman Kilen and Archengius). '
          + 'Map data (c) OpenStreetMap contributors (ODbL) via Overture Maps; land cover: ESA WorldCover (CC BY '
          + '4.0); heights: Copernicus and Environment Agency (OGL). The trees, crowds, marshals, barrier frames, cars, '
          + 'gantries and the Service Park are the game\'s own, from your copy of it. Full list: CREDITS.txt in the '
          + 'package.',
      },
      {
        id: 'hattori-lousa',
        kind: 'track',
        minApp: '0.1.6',                         // (the first public app that builds an author's kit and takes a zip
                                                 // from its page: Hattori Rally's installer, from his Patreon)
        name: 'Lousã',
        subtitle: 'Hattori Rally · 6.7 km · gravel · Portugal',
        description: 'A Rally de Portugal gravel stage in the Serra da Lousã, made from Portugal\'s lidar terrain. '
          + 'Hattori Rally\'s installer is free on his Patreon: INSTALL opens his post, download the zip there and '
          + 'the app does the rest. Built on your PC from your own copy of the game: about 10 minutes, and about '
          + '20 GB free on the game\'s drive while it builds.',
        author: 'Hattori Rally',
        location: 'Portugal',
        surface: 'Gravel',
        stages: [{ stageId: 'AcrXsPtLousaFullForward', name: 'Lousã' }],
        // its release: the card's picture and the manifest (a package its author's kit builds on the player's PC:
        // the app's community.py build_kit)
        image: `${REPO}/releases/download/hattori-lousa/card.jpg`,
        manifest: `${REPO}/releases/download/hattori-lousa/manifest.json`,
        group: 'lousa',                          // (its own stage list: the stage switch shows it or London)
        tool: 'ACR Daily',
        terms: 'Free for offline single-player play. Share the download, never the stage files it builds in your game. '
          + 'Not affiliated with Kunos Simulazioni, Supernova Games Studios or 505 Games.',
        // (as its own CREDITS.md, version 0.2: the stage, its tools, its data, and the game's own parts)
        credits: 'By Hattori Rally (on Patreon: patreon.com/FilipeFerreira), downloaded from his Patreon. Built with '
          + 'ACR Extra Stages and acr-rewind (cherrymcgerry), CUE4Parse (FabianFG) and retoc (Truman Kilen and '
          + 'Archengius). Terrain: Direção-Geral do Território, Portugal (CC BY 4.0); route after rally-maps.com. The '
          + 'host level, trees, rocks, road and ground are the game\'s own, from your copy of it. Full list: CREDITS.md '
          + 'in the download.',
        // its author's own page for it: a link on its card
        // (its zip comes from there too: the manifest's zip `page`, the post with his installer for the game's 0.7)
        support: { name: 'Patreon', url: 'https://www.patreon.com/FilipeFerreira/posts/rally-de-lousa-0-175817665' },
      },
      ...OXMOD_ITEMS,
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
 *  `testOnly` goes only to a test build (test: the app asking is one, a four-part version: src/voids.js testBuild);
 *  an item with `minApp` only to a test build or an app of that version or newer (app: its version, null when
 *  unknown); `tools` (the stage makers an item's `exporter` names) go with the items that need them. An item `off`
 *  goes to no app. */
export function catalog(siteUrl = '', { test = false, app = null } = {}) {
  const newEnough = (it) => !it.minApp || test || (app != null && !olderThan(app, it.minApp));
  const out = {
    categories: COMMUNITY.map((c) => ({
      id: c.id,
      name: c.name,
      items: c.items.filter((it) => !it.off && (test || !it.testOnly) && newEnough(it))
        .map(({ minApp, ...it }) => ({ ...it, image: it.image && it.image.startsWith('/') ? siteUrl + it.image : it.image })),
    })),
  };
  if (out.categories.some((c) => c.items.some((it) => it.exporter === STAGE_EXPORTER.id))) {
    out.tools = { [STAGE_EXPORTER.id]: STAGE_EXPORTER };           // (what an `exporter` item's INSTALL runs)
  }
  return out;
}

/** Version a older than b ("0.1.5" < "0.1.6" < "0.1.6.1"): numbers part by part, a missing part 0. */
function olderThan(a, b) {
  const pa = String(a).split('.').map(Number), pb = String(b).split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) < (pb[i] || 0);
  }
  return false;
}
