// The flags: ISO 3166-1 alpha-2 (plus the UK's nations) -> their names, for the flag next to a driver's name.
// A driver picks their own flag on their page (POST /api/me/country, src/drivers.js); nothing in the game sets it.

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
/** Every flag on offer, by name: [[code, name], ...] (the picker on a driver's own page, src/driverpages.js). */
export const COUNTRIES = Object.entries(NAMES).sort((a, b) => a[1].localeCompare(b[1]));

/** Is this a flag a driver can pick? */
export const isCountry = (code) => Object.prototype.hasOwnProperty.call(NAMES, code);

export const countryName = (code) => NAMES[code] || null;
