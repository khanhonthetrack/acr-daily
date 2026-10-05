// Each stage as the game's menu names it, by the game's stage id (routes.stage_id). From the game's string table
// (Data/Localization/ContentTexts/ST_Track, TRACK_<STAGE>_<VARIANT>) and its DT_TracksVariants, which pairs each id
// with its key (tools/gamefiles). The telemetry reports a shorter name ("Monte Carlo La Bollène"), so challenges
// carry both: track (the game's telemetry name), stageName (its short part) and menuName (this).

export const MENU_NAMES = {
  // Alsace: Vallée de Munster
  AlsaceS2MunsterFullReverse: 'Vallée de Munster Descente',
  AlsaceS2MunsterFullForward: 'Vallée de Munster Montée',
  AlsaceS2MunsterShort1Reverse: 'Forêt de Munster',
  AlsaceS2MunsterShort1Forward: 'Luttenbach près Munster',
  AlsaceS2MunsterShort2Reverse: 'Col du petit Ballon',
  AlsaceS2MunsterShort2Forward: 'Sommet de Munster',
  // Alsace: Saverne
  AlsaceS4SaverneFullReverse: 'Steigenbach',
  AlsaceS4SaverneFullForward: 'Forêt de Saverne',
  AlsaceS4SaverneShort1Forward: 'Obersteigen',
  AlsaceS4SaverneShort1Reverse: 'La traversée de La Mossig',
  // Greece: Elatia
  GreeceS3ElatiaFullForward: 'Elatia - Zeli',
  GreeceS3ElatiaFullReverse: 'Zeli - Elatia',
  GreeceS3ElatiaCut1Forward: 'Elatia',
  GreeceS3ElatiaCut1Reverse: 'Elatia Reverse',
  GreeceS3ElatiaCut2Forward: 'Zeli',
  GreeceS3ElatiaCut2Reverse: 'Zeli Reverse',
  // Greece: Loutraki
  GreeceS4LoutrakiFullForward: 'Loutraki - Aghii Theodori',
  GreeceS4LoutrakiFullReverse: 'Aghii Theodori - Loutraki',
  GreeceS4LoutrakiCut1Forward: 'New Loutraki',
  GreeceS4LoutrakiCut1Reverse: 'New Loutraki Reverse',
  GreeceS4LoutrakiCut2Forward: 'Aghii Theodori',
  GreeceS4LoutrakiCut2Reverse: 'Aghii Theodori Reverse',
  // Monte Carlo: Col de Turini
  MonteCarloS1BolleneFullForward: 'La Bollène-Vésubie - Peïra Cava',
  MonteCarloS1BolleneFullReverse: 'Peïra Cava - La Bollène-Vésubie',
  MonteCarloS1BolleneCut1Forward: 'La Bollène-Vésubie - Turini',
  MonteCarloS1BolleneCut1Reverse: 'Turini - La Bollène-Vésubie',
  MonteCarloS1BolleneCut2Forward: 'Turini - Peïra Cava',
  MonteCarloS1BolleneCut2Reverse: 'Peïra Cava - Turini',
  MonteCarloS1BolleneCut3Forward: "Pra d'Alart",
  MonteCarloS1BolleneCut3Reverse: 'Sommet de Turini',
  // Monte Carlo: Sisteron
  MonteCarloS2SisteronFullForward: 'Sisteron - St. Geniez',
  MonteCarloS2SisteronFullReverse: 'St. Geniez - Sisteron',
  MonteCarloS2SisteronCut1Forward: 'Sisteron - Mézien',
  MonteCarloS2SisteronCut1Reverse: 'Mézien - Sisteron',
  MonteCarloS2SisteronCut2Forward: 'Mézien - St. Geniez',
  MonteCarloS2SisteronCut2Reverse: 'St. Geniez - Mézien',
  // Wales: Hafren North (the game's ids spell it "Weles")
  WelesS3HafrenNorthFullForward: 'Cwmbiga - Afon Biga',
  WelesS3HafrenNorthFullReverse: 'Afon Biga - Cwmbiga',
  WelesS3HafrenNorthCut1Forward: 'Cwmbiga - Fedw Fain',
  WelesS3HafrenNorthCut1Reverse: 'Fedw Fain - Cwmbiga',
  WelesS3HafrenNorthCut2Forward: 'Banc Gwyn - Afon Biga',
  WelesS3HafrenNorthCut2Reverse: 'Afon Biga - Banc Gwyn',
  // Wales: Hafren South
  WelesS4HafrenSouthFullForward: 'Afon Bidno - Severn',
  WelesS4HafrenSouthFullReverse: 'Severn - Afon Bidno',
};

/** The menu name of a stage id, or null for ids not in the table. */
export const menuName = (stageId) => MENU_NAMES[stageId] || null;
