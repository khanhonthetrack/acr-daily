// Country names as the game shows them (English) -> ISO 3166-1 alpha-2, for the flag next to a driver's name.
// The app sends the nationality from the player's in-game driver profile.

const NAMES = {
  af: 'Afghanistan', al: 'Albania', dz: 'Algeria', ad: 'Andorra', ao: 'Angola', ar: 'Argentina', am: 'Armenia',
  au: 'Australia', at: 'Austria', az: 'Azerbaijan', bs: 'Bahamas', bh: 'Bahrain', bd: 'Bangladesh', by: 'Belarus',
  be: 'Belgium', bz: 'Belize', bj: 'Benin', bt: 'Bhutan', bo: 'Bolivia', ba: 'Bosnia and Herzegovina', bw: 'Botswana',
  br: 'Brazil', bn: 'Brunei', bg: 'Bulgaria', bf: 'Burkina Faso', bi: 'Burundi', kh: 'Cambodia', cm: 'Cameroon',
  ca: 'Canada', cv: 'Cape Verde', cf: 'Central African Republic', td: 'Chad', cl: 'Chile', cn: 'China',
  co: 'Colombia', km: 'Comoros', cg: 'Congo', cd: 'DR Congo', cr: 'Costa Rica', ci: "Côte d'Ivoire", hr: 'Croatia',
  cu: 'Cuba', cy: 'Cyprus', cz: 'Czech Republic', dk: 'Denmark', dj: 'Djibouti', dm: 'Dominica',
  do: 'Dominican Republic', ec: 'Ecuador', eg: 'Egypt', sv: 'El Salvador', gq: 'Equatorial Guinea', er: 'Eritrea',
  ee: 'Estonia', sz: 'Eswatini', et: 'Ethiopia', fj: 'Fiji', fi: 'Finland', fr: 'France', ga: 'Gabon', gm: 'Gambia',
  ge: 'Georgia', de: 'Germany', gh: 'Ghana', gr: 'Greece', gt: 'Guatemala', gn: 'Guinea', gy: 'Guyana', ht: 'Haiti',
  hn: 'Honduras', hk: 'Hong Kong', hu: 'Hungary', is: 'Iceland', in: 'India', id: 'Indonesia', ir: 'Iran', iq: 'Iraq',
  ie: 'Ireland', il: 'Israel', it: 'Italy', jm: 'Jamaica', jp: 'Japan', jo: 'Jordan', kz: 'Kazakhstan', ke: 'Kenya',
  kr: 'South Korea', kp: 'North Korea', xk: 'Kosovo', kw: 'Kuwait', kg: 'Kyrgyzstan', la: 'Laos', lv: 'Latvia',
  lb: 'Lebanon', ls: 'Lesotho', lr: 'Liberia', ly: 'Libya', li: 'Liechtenstein', lt: 'Lithuania', lu: 'Luxembourg',
  mo: 'Macau', mg: 'Madagascar', mw: 'Malawi', my: 'Malaysia', mv: 'Maldives', ml: 'Mali', mt: 'Malta',
  mr: 'Mauritania', mu: 'Mauritius', mx: 'Mexico', md: 'Moldova', mc: 'Monaco', mn: 'Mongolia', me: 'Montenegro',
  ma: 'Morocco', mz: 'Mozambique', mm: 'Myanmar', na: 'Namibia', np: 'Nepal', nl: 'Netherlands', nz: 'New Zealand',
  ni: 'Nicaragua', ne: 'Niger', ng: 'Nigeria', mk: 'North Macedonia', no: 'Norway', om: 'Oman', pk: 'Pakistan',
  ps: 'Palestine', pa: 'Panama', pg: 'Papua New Guinea', py: 'Paraguay', pe: 'Peru', ph: 'Philippines', pl: 'Poland',
  pt: 'Portugal', pr: 'Puerto Rico', qa: 'Qatar', ro: 'Romania', ru: 'Russia', rw: 'Rwanda', sm: 'San Marino',
  sa: 'Saudi Arabia', sn: 'Senegal', rs: 'Serbia', sc: 'Seychelles', sl: 'Sierra Leone', sg: 'Singapore',
  sk: 'Slovakia', si: 'Slovenia', so: 'Somalia', za: 'South Africa', ss: 'South Sudan', es: 'Spain', lk: 'Sri Lanka',
  sd: 'Sudan', sr: 'Suriname', se: 'Sweden', ch: 'Switzerland', sy: 'Syria', tw: 'Taiwan', tj: 'Tajikistan',
  tz: 'Tanzania', th: 'Thailand', tg: 'Togo', tt: 'Trinidad and Tobago', tn: 'Tunisia', tr: 'Turkey',
  tm: 'Turkmenistan', ug: 'Uganda', ua: 'Ukraine', ae: 'United Arab Emirates', gb: 'United Kingdom',
  us: 'United States', uy: 'Uruguay', uz: 'Uzbekistan', ve: 'Venezuela', vn: 'Vietnam', ye: 'Yemen', zm: 'Zambia',
  zw: 'Zimbabwe', 'gb-eng': 'England', 'gb-sct': 'Scotland', 'gb-wls': 'Wales', 'gb-nir': 'Northern Ireland',
};
const ALIASES = {
  'great britain': 'gb', uk: 'gb', britain: 'gb', usa: 'us', 'united states of america': 'us', 'america': 'us',
  czechia: 'cz', 'korea': 'kr', 'republic of korea': 'kr', 'viet nam': 'vn', holland: 'nl', 'the netherlands': 'nl',
  'ivory coast': 'ci', 'russian federation': 'ru', 'uae': 'ae', 'turkiye': 'tr', 'türkiye': 'tr', 'macedonia': 'mk',
  'swaziland': 'sz', 'burma': 'mm', 'democratic republic of the congo': 'cd', 'republic of the congo': 'cg',
  'bosnia': 'ba', 'cabo verde': 'cv',
};

const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z ]/g, '').trim();
const BY_NAME = Object.fromEntries(Object.entries(NAMES).map(([code, name]) => [norm(name), code]));

/** 'Vietnam' -> 'vn' (null when unknown). */
export function countryCode(name) {
  const n = norm(name);
  if (!n) return null;
  return BY_NAME[n] || ALIASES[n] || null;
}

export const countryName = (code) => NAMES[code] || null;
